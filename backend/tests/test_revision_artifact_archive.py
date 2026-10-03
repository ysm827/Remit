import json

from app.core.workflow_checkpoint import WorkflowCheckpoint


def test_invalidated_results_leave_active_directory_but_remain_repairable(tmp_path):
    checkpoint = WorkflowCheckpoint(tmp_path)
    state = {"protected_input_files": ["input.csv"]}
    contents = {
        "solver.py": "print('previous implementation')\n",
        "ques1_quality_report.json": json.dumps({"status": "pass"}),
        "result.csv": "x,y\n1,2\n",
        "input.csv": "x\n1\n",
        "shared.csv": "upstream evidence",
    }
    for name, content in contents.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    checkpoint._purge_solution_artifacts(
        ["ques1"],
        state,
        {
            "ques1": {"artifacts": list(contents)},
            "eda": {"artifacts": ["shared.csv"]},
        },
    )
    backup = tmp_path / state["revision_artifact_backups"]["ques1"]["directory"]
    for name in ("solver.py", "ques1_quality_report.json", "result.csv"):
        assert not (tmp_path / name).exists()
        assert (backup / name).read_text(encoding="utf-8") == contents[name]
    assert (tmp_path / "input.csv").read_text(encoding="utf-8") == contents["input.csv"]
    assert (tmp_path / "shared.csv").read_text(encoding="utf-8") == contents[
        "shared.csv"
    ]
    # Repeated recovery must not discard the existing repair source pointer.
    previous = dict(state["revision_artifact_backups"])
    checkpoint._purge_solution_artifacts(["ques1"], state, {})
    assert state["revision_artifact_backups"] == previous


def test_revision_archive_does_not_move_external_or_historical_files(tmp_path):
    root = tmp_path / "task"
    root.mkdir()
    outside = tmp_path / "external.py"
    outside.write_text("external", encoding="utf-8")
    history = root / ".history/previous/solver.py"
    history.parent.mkdir(parents=True)
    history.write_text("previous", encoding="utf-8")
    state = {}
    WorkflowCheckpoint(root)._purge_solution_artifacts(
        ["ques1"],
        state,
        {"ques1": {"artifacts": ["../external.py", ".history/previous/solver.py"]}},
    )
    assert outside.read_text(encoding="utf-8") == "external"
    assert history.read_text(encoding="utf-8") == "previous"
    assert "revision_artifact_backups" not in state
