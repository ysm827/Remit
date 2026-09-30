"""Create task inputs without coupling file-system work to FastAPI routes."""

import json
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


def _upload_names(
    files: list[UploadFile], destination: Path, relative_paths: list[str] | None = None
) -> list[str]:
    """写入前验证整批名称，避免同名覆盖和不同平台路径解析差异。"""
    if len(files) > settings.UPLOAD_MAX_FILES:
        raise UploadLimitError(f"附件数量不能超过 {settings.UPLOAD_MAX_FILES}")
    if relative_paths is not None and len(relative_paths) != len(files):
        raise ValueError("附件路径数量与文件数量不一致")
    existing = {
        path.relative_to(destination).as_posix().casefold(): path.is_dir()
        for path in destination.rglob("*")
    }
    root = destination.resolve()
    names: list[str] = []
    for index, upload in enumerate(files):
        name = (
            relative_paths[index]
            if relative_paths is not None
            else upload.filename or ""
        )
        folded = name.casefold()
        parts = name.split("/")
        if (
            not name
            or (relative_paths is None and "/" in name)
            or len(parts) > 20
            or len(name.encode("utf-8")) > 1024
            or any(char in name for char in '\\:<>"|?*')
            or any(ord(char) < 32 for char in name)
            or any(
                not part
                or part.startswith(".")
                or part.endswith((".", " "))
                or _DEVICE_NAME.match(part)
                or len(part.encode("utf-8")) > 240
                for part in parts
            )
            or parts[0].casefold() in _RESERVED_NAMES | {"paper"}
            or parts[-1].casefold().endswith("_quality_report.json")
            or not (destination / name).resolve().is_relative_to(root)
            or any(
                (destination.joinpath(*parts[:i])).is_symlink()
                for i in range(1, len(parts) + 1)
            )
        ):
            raise ValueError(f"不安全或保留的上传文件名：{name!r}")
        if folded in existing:
            raise ValueError(f"附件名称重复或已存在：{name}")
        for i in range(1, len(parts)):
            parent = "/".join(parts[:i]).casefold()
            if parent in existing and not existing[parent]:
                raise ValueError(f"附件目录与文件冲突：{name}")
            existing[parent] = True
        existing[folded] = False
        names.append(name)
    return names


def _commit_uploads(staging: Path, destination: Path, names: list[str]) -> None:
    """全部校验通过才提交；独占创建避免覆盖已有文件，失败时回滚本批。"""
    created: list[Path] = []
    directories: list[Path] = []
    try:
        for name in names:
            target = destination / name
            missing = []
            parent = target.parent
            while parent != destination and not parent.exists():
                missing.append(parent)
                parent = parent.parent
            for directory in reversed(missing):
                directory.mkdir()
                directories.append(directory)
            with target.open("xb") as output:
                created.append(target)
                with (staging / name).open("rb") as source:
                    copyfileobj(source, output, _UPLOAD_CHUNK_BYTES)
    except BaseException:
        for target in created:
            target.unlink(missing_ok=True)
        for directory in reversed(directories):
            directory.rmdir()
        raise


async def persist_uploads(
    files: list[UploadFile], destination: Path, relative_paths: list[str] | None = None
) -> list[str]:
    """按块暂存附件，在大小和整批名称均有效后一次提交。"""
    names = _upload_names(files, destination, relative_paths)
    total = 0
    saved: list[str] = []
    with TemporaryDirectory(prefix=".upload-", dir=destination) as temporary:
        staging = Path(temporary)
        for upload, name in zip(files, names, strict=True):
            size = 0
            (staging / name).parent.mkdir(parents=True, exist_ok=True)
            with (staging / name).open("wb") as output:
                while chunk := await upload.read(_UPLOAD_CHUNK_BYTES):
                    size += len(chunk)
                    total += len(chunk)
                    if (
                        size > settings.UPLOAD_MAX_FILE_BYTES
                        or total > settings.UPLOAD_MAX_TOTAL_BYTES
                    ):
                        raise UploadLimitError(
                            f"附件超过大小限制：单文件最多 {settings.UPLOAD_MAX_FILE_BYTES / 1024 / 1024:g} MB，"
                            f"本次合计最多 {settings.UPLOAD_MAX_TOTAL_BYTES / 1024 / 1024:g} MB"
                        )
                    await run_blocking(output.write, chunk)
            if size or relative_paths is not None:
                saved.append(name)
        # 提交线程不应因请求取消而在临时目录清理之后继续读取。
        await run_blocking(_commit_uploads, staging, destination, saved)
    manifest = destination / ".remit-inputs.json"
    previous = (
        json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else []
    )
    manifest_temp = manifest.with_suffix(".json.tmp")
    manifest_temp.write_text(
        json.dumps(list(dict.fromkeys([*previous, *saved])), ensure_ascii=False),
        encoding="utf-8",
    )
    manifest_temp.replace(manifest)
    return saved


def parse_upload_paths(value: str | None) -> list[str] | None:
    """解析独立路径清单；multipart 文件名仍保持 basename 以兼容浏览器。"""
    if value is None:
        return None
    try:
        paths = json.loads(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("附件路径清单不是有效 JSON") from exc
    if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
        raise ValueError("附件路径清单必须为字符串数组")
    return paths
