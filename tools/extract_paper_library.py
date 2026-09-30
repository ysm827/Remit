"""Extract user-supplied exemplars locally for a traceable writing-skill library.

Usage: backend/.venv/Scripts/python tools/extract_paper_library.py --root PATH
       [--root PATH ...] --output LOCAL_DIRECTORY
No model calls, source edits, or network requests are made.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import fitz


MARKERS = {
    "abstract": r"摘\s*要|Summary\s+Sheet|Abstract",
    "assumptions": r"模型假设|基本假设|Assumptions",
    "notation": r"符号说明|符号定义|Notations?",
    "validation": r"模型检验|有效性检验|误差分析|Validation",
    "sensitivity": r"灵敏度|敏感性|Sensitivity",
    "robustness": r"稳健性|鲁棒性|Robustness",
    "limitations": r"模型评价|模型优缺点|模型的优缺点|局限|Weaknesses|Limitations",
    "references": r"参考文献|References",
    "appendix": r"附\s*录|Appendix",
}


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def classify(path: str) -> str:
    if "研究生" in path or "华为杯" in path:
        return "gmcm"
    if "华数杯" in path:
        return "huashu"
    if "国赛" in path:
        return "cumcm"
    if "美赛" in path or re.search(r"\b(?:MCM|ICM)\b", path, re.I):
        return "mcm-icm"
    return "unclassified"


def extract(roots: list[Path], output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    papers: dict[str, dict] = {}
    failures = []
    file_count = 0
    for root in roots:
        if not root.is_dir():
            raise ValueError(f"Missing corpus directory: {root}")
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() != ".pdf":
                continue
            file_count += 1
            relative = root.name + "/" + path.relative_to(root).as_posix()
            sha = digest(path)
            if sha in papers:
                papers[sha]["sources"].append(relative)
                continue
            try:
                with fitz.open(path) as doc:
                    pages = [page.get_text(sort=True) for page in doc]
                found = {
                    key: [
                        i + 1
                        for i, text in enumerate(pages)
                        if re.search(pattern, text, re.I)
                    ]
                    for key, pattern in MARKERS.items()
                }
                headings = []
                for number, text in enumerate(pages, 1):
                    for line in text.splitlines():
                        line = line.strip()
                        if 3 <= len(line) <= 65 and re.match(
                            r"^(?:[一二三四五六七八九十]+[、．.]|\d+(?:\.\d+){0,3}\s+)\S",
                            line,
                        ):
                            headings.append({"page": number, "text": line})
                record = {
                    "id": sha[:16],
                    "sha256": sha,
                    "sources": [relative],
                    "competition": classify(relative),
                    "pages": len(pages),
                    "text_characters": sum(len(text.strip()) for text in pages),
                    "empty_text_pages": [
                        i + 1 for i, text in enumerate(pages) if len(text.strip()) < 40
                    ],
                    "marker_pages": found,
                    "headings": headings[:180],
                }
                papers[sha] = record
                (output / f"{sha[:16]}.json").write_text(
                    json.dumps(
                        {"metadata": record, "pages": pages},
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            except Exception as exc:
                failures.append({"source": relative, "error": str(exc)})
    manifest = {
        "schema_version": 1,
        "source_files": file_count,
        "unique_papers": len(papers),
        "papers": list(papers.values()),
        "failures": failures,
        "note": "Marker matches locate passages; they do not prove methodological quality or official contest requirements.",
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = extract(args.root, args.output)
    print(
        json.dumps(
            {k: result[k] for k in ["source_files", "unique_papers", "failures"]},
            ensure_ascii=False,
        )
    )
