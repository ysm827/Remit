"""Create task inputs without coupling file-system work to FastAPI routes."""

from pathlib import Path
from shutil import copy2

from fastapi import UploadFile


def seed_example(source_dir: Path, destination: Path) -> str:
    """Copy one bundled example into a fresh workspace and return its question."""
    question_path = source_dir / "questions.txt"
    question = question_path.read_text(encoding="utf-8")
    for candidate in source_dir.iterdir():
        if candidate.is_file() and candidate != question_path:
            copy2(candidate, destination / candidate.name)
    return question


async def persist_uploads(files: list[UploadFile], destination: Path) -> list[str]:
    """Store non-empty uploads and reject names that escape the workspace."""
    saved: list[str] = []
    for upload in files:
        raw_name = upload.filename or ""
        safe_name = Path(raw_name).name
        if not safe_name or safe_name != raw_name:
            raise ValueError(f"不安全的上传文件名：{raw_name!r}")
        payload = await upload.read()
        if not payload:
            continue
        (destination / safe_name).write_bytes(payload)
        saved.append(safe_name)
    return saved
