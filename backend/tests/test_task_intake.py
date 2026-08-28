from pathlib import Path

import pytest

from app.services.task_intake import seed_example


def test_seed_example_copies_only_catalogued_project_example(tmp_path: Path) -> None:
    question = seed_example("urban-cooling", tmp_path)

    assert "社区降温设施配置" in question
    assert (tmp_path / "segments.csv").is_file()
    assert not (tmp_path / "questions.txt").exists()


def test_seed_example_rejects_unknown_or_path_like_identifier(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="未知的内置示例"):
        seed_example("../configuration", tmp_path)
