import hashlib

import pytest

from app.services.writer_evidence import source_excerpt


def test_actual_table_precedes_summary_and_clips_only_complete_rows(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    values = {"summary.json": '{"old_gap":0}', "gap_detail.csv": "k,gap\n2,2\n3,3\n" * 1000}
    hashes = {}
    for name, text in values.items():
        (assets / name).write_text(text, encoding="utf-8")
        hashes[name] = hashlib.sha256((assets / name).read_bytes()).hexdigest()
    entry = {"artifacts": list(values), "paper_ready_images": ["gap.png"]}
    result = source_excerpt(tmp_path, entry, hashes, budget=6000)
    import json
    data = json.loads(result.split("\n")[-1])
    assert data["sources"][0]["file"] == "gap_detail.csv"
    assert data["sources"][0]["incomplete"]
    assert data["sources"][0]["content"].splitlines()[-1] in {"k,gap", "2,2", "3,3"}
    assert data["omitted_files"] == ["summary.json"]


def test_snapshot_mutation_missing_file_and_escape_fail_closed(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "gap.csv").write_text("k,gap\n2,2", encoding="utf-8")
    with pytest.raises(ValueError, match="版本已变化"):
        source_excerpt(tmp_path, {"artifacts": ["gap.csv"]}, {"gap.csv": "old"})
    for name in ("missing.csv", "../outside.csv"):
        with pytest.raises(ValueError, match="缺失或路径越界"):
            source_excerpt(tmp_path, {"artifacts": [name]}, {name: "old"})
