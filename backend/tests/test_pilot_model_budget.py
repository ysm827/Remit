"""Composite pilot budget and existing reservations survive technical recovery."""

import json
import sqlite3

import pytest

from app.config.setting import settings
from app.core.llm.errors import ModelStageBudgetExceeded
from app.services import call_ledger, task_failure


@pytest.mark.parametrize(
    "node,planned,expected_units",
    [
        ("pilot", ["ques1", "ques2", "ques3", "ques4"], 4),
        ("pilot", ["ques1"], 1),
        ("pilot", [], 1),
        ("solve:ques1", ["ques1", "ques2", "ques3", "ques4"], 1),
    ],
)
def test_only_matching_multi_question_pilot_scales_budget(
    monkeypatch, node, planned, expected_units
):
    monkeypatch.setattr(settings, "LLM_STAGE_CALL_LIMIT", 24)
    monkeypatch.setattr(settings, "LLM_STAGE_API_SECONDS", 900)
    state = {
        "current_node": node,
        "questions": {f"ques{i}": "q" for i in range(1, 5)},
        "pilot_plan": {"questions": dict.fromkeys(planned, {})},
    }
    assert call_ledger.model_stage_limits(state) == (
        24 * expected_units,
        900 * expected_units,
    )


def test_old_pilot_usage_is_charged_to_expanded_budget_and_still_exhausts(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "LLM_STAGE_CALL_LIMIT", 24)
    monkeypatch.setattr(settings, "LLM_STAGE_API_SECONDS", 900)
    root = tmp_path / "project/work_dir/test"
    root.mkdir(parents=True)
    state = {
        "current_node": "pilot",
        "questions": {"ques1": "q1", "ques2": "q2"},
        "execution_id": "a" * 32,
        "completed_nodes": ["solve:eda"],
    }
    path = root / "workflow_state.json"
    path.write_text(json.dumps(state))
    assert call_ledger.reserve("test", "CoderAgent:pilot:ques1", "c1", "a1") == 900
    with sqlite3.connect(root / ".calls.sqlite3") as db:
        db.execute("CREATE TABLE calls (attempt_id TEXT, elapsed_seconds REAL)")
        db.execute("INSERT INTO calls VALUES ('a1', 900.01)")
    with pytest.raises(ModelStageBudgetExceeded):
        call_ledger.reserve("test", "CoderAgent:pilot:ques2", "c2", "a2")
    state["pilot_plan"] = {"questions": {"ques1": {}, "ques2": {}}}
    path.write_text(json.dumps(state))
    assert call_ledger.reserve(
        "test", "CoderAgent:pilot:ques2", "c2", "a2"
    ) == pytest.approx(899.99)
    with sqlite3.connect(root / ".calls.sqlite3") as db:
        assert (
            db.execute("SELECT count(distinct stage_key) FROM reservations").fetchone()[
                0
            ]
            == 1
        )
        db.execute("INSERT INTO calls VALUES ('a2', 900)")
    for _ in range(2):
        with pytest.raises(ModelStageBudgetExceeded) as caught:
            call_ledger.reserve("test", "CoderAgent:pilot:ques2", "c3", "a3")
        failure = task_failure.describe(caught.value, root, retrying=False, attempts=0)
        assert failure["code"] == "MODEL_STAGE_BUDGET"
        assert failure["attempts_used"] == 2
        assert failure["run_id"] == "a" * 32
        assert "1800.0/1800.0" in failure["reason"]
        assert not failure["retryable"]
    with sqlite3.connect(root / ".calls.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM reservations").fetchone()[0] == 2


def test_composite_call_limit_remains_finite(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "LLM_STAGE_CALL_LIMIT", 1)
    root = tmp_path / "project/work_dir/test"
    root.mkdir(parents=True)
    (root / "workflow_state.json").write_text(
        json.dumps(
            {
                "current_node": "pilot",
                "questions": {"ques1": "q1", "ques2": "q2"},
                "pilot_plan": {"questions": {"ques1": {}, "ques2": {}}},
            }
        )
    )
    for i in range(2):
        call_ledger.reserve("test", "CoderAgent", str(i), str(i))
    with pytest.raises(ModelStageBudgetExceeded, match="2/2"):
        call_ledger.reserve("test", "CoderAgent", "3", "3")
