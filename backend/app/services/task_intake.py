"""Create task inputs without coupling file-system work to FastAPI routes."""

import re
from pathlib import Path
from shutil import copy2, copyfileobj
from tempfile import TemporaryDirectory

from fastapi import UploadFile
from app.config.setting import settings
from app.services.async_io import run_blocking


_EXAMPLE_ROOT = Path(__file__).resolve().parents[1] / "example"
_EXAMPLE_CATALOG = {
    "urban-cooling": "urban_cooling",
}


def seed_example(example_id: str, destination: Path) -> str:
    """Copy a project-owned example into a workspace and return its question."""
    try:
        source_dir = _EXAMPLE_ROOT / _EXAMPLE_CATALOG[example_id]
    except KeyError as error:
        raise ValueError(f"未知的内置示例：{example_id}") from error

    question_path = source_dir / "questions.txt"
    question = question_path.read_text(encoding="utf-8")
    for candidate in source_dir.iterdir():
        if candidate.is_file() and candidate != question_path:
            copy2(candidate, destination / candidate.name)
    return question


_UPLOAD_CHUNK_BYTES = 1024 * 1024
_RESERVED_NAMES = {
    "workflow_state.json",
    "all.zip",
    "pilot_results.json",
    "final_citations.json",
}
_DEVICE_NAME = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", re.I)


class UploadLimitError(ValueError):
    """附件超出服务端资源限制。"""


def _upload_names(files: list[UploadFile], destination: Path) -> list[str]:
    """写入前验证整批名称，避免同名覆盖和不同平台路径解析差异。"""
    if len(files) > settings.UPLOAD_MAX_FILES:
        raise UploadLimitError(f"附件数量不能超过 {settings.UPLOAD_MAX_FILES}")
    existing = {path.name.casefold() for path in destination.iterdir()}
    names: list[str] = []
    for upload in files:
        name = upload.filename or ""
        folded = name.casefold()
        if (
            not name
            or name.startswith(".")
            or name.endswith((".", " "))
            or any(char in name for char in '/\\:<>"|?*')
            or any(ord(char) < 32 for char in name)
            or _DEVICE_NAME.match(name)
            or len(name.encode("utf-8")) > 240
            or folded in _RESERVED_NAMES
            or folded.endswith("_quality_report.json")
        ):
            raise ValueError(f"不安全或保留的上传文件名：{name!r}")
        if folded in existing:
            raise ValueError(f"附件名称重复或已存在：{name}")
        existing.add(folded)
        names.append(name)
    return names


def _commit_uploads(staging: Path, destination: Path, names: list[str]) -> None:
    """全部校验通过才提交；独占创建避免覆盖已有文件，失败时回滚本批。"""
    created: list[Path] = []
    try:
        for name in names:
            target = destination / name
            with target.open("xb") as output:
                created.append(target)
                with (staging / name).open("rb") as source:
                    copyfileobj(source, output, _UPLOAD_CHUNK_BYTES)
    except BaseException:
        for target in created:
            target.unlink(missing_ok=True)
        raise


async def persist_uploads(files: list[UploadFile], destination: Path) -> list[str]:
    """按块暂存附件，在大小和整批名称均有效后一次提交。"""
    names = _upload_names(files, destination)
    total = 0
    saved: list[str] = []
    with TemporaryDirectory(prefix=".upload-", dir=destination) as temporary:
        staging = Path(temporary)
        for upload, name in zip(files, names, strict=True):
            size = 0
            with (staging / name).open("wb") as output:
                while chunk := await upload.read(_UPLOAD_CHUNK_BYTES):
                    size += len(chunk)
                    total += len(chunk)
                    if (
                        size > settings.UPLOAD_MAX_FILE_BYTES
                        or total > settings.UPLOAD_MAX_TOTAL_BYTES
                    ):
                        raise UploadLimitError("附件超过单文件或总大小限制")
                    await run_blocking(output.write, chunk)
            if size:
                saved.append(name)
        # 提交线程不应因请求取消而在临时目录清理之后继续读取。
        await run_blocking(_commit_uploads, staging, destination, saved)
    return saved
