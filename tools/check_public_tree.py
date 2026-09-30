"""Check the tracked release tree without reading local credentials or user data."""

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    names = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=ROOT
    ).decode().split("\0")
    errors = []
    for name in filter(None, names):
        path = ROOT / name
        parts = path.relative_to(ROOT).parts
        local_only = (
            name.startswith((".agents/", ".claude/", ".cursor/", ".firecrawl/",
                             "docs/monitoring/", "docs/screenshots/"))
            or any(p in {"node_modules", ".venv", "__pycache__", "logs"} for p in parts)
            or (path.name.startswith(".env") and path.name != ".env.example")
            or (name.startswith("backend/project/") and name != "backend/project/work_dir/.gitkeep")
            or path.suffix in {".log", ".sqlite3", ".db", ".rdb", ".pyc", ".pid"}
        )
        if local_only:
            errors.append(f"Local-only file: {name}")
        data = path.read_bytes()
        if len(data) > 50 * 1024 * 1024:
            errors.append(f"Unexpected large file: {name}")
        if re.search(rb"gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-[A-Za-z0-9_-]{32,}", data):
            errors.append(f"Possible credential: {name}")
        if re.search(rb"-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----", data):
            errors.append(f"Private key: {name}")
    skill_root = ROOT / "backend/app/competition_skills"
    lock = json.loads((skill_root / "sources.lock.json").read_text(encoding="utf-8"))
    for entry in lock["files"]:
        p = skill_root / entry["path"]
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != entry["sha256"]:
            errors.append(f"Missing or changed upstream source: {entry['path']}")
    library = json.loads((skill_root / "writing/library.json").read_text(encoding="utf-8"))
    if library.get("cards"):
        errors.append("Personal paper cards must not be included in the public tree")
    for error in errors:
        print(error)
    if not errors:
        print(f"Public tree check passed: {sum(bool(n) for n in names)} tracked files")
    return bool(errors)


if __name__ == "__main__":
    sys.exit(main())
