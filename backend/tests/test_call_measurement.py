"""旧账本迁移、并行计时与真实调用门面的用途记录。"""

import asyncio
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock

import pytest

from app.core.llm.llm import LLM
from app.core.llm.types import StandardResponse, Usage
from app.services import call_ledger, runtime_diagnostics


def entry(identifier, **values):
    return dict(
        attempt_id=identifier,
        call_id=identifier,
        role="test",
        model="fixture",
        status="completed",
        started_at="2026-10-03T00:00:00+00:00",
        elapsed_seconds=4,
        prompt_tokens=None,
        completion_tokens=None,
        cost=None,
        currency=None,
        error_code=None,
        **values,
    )


@pytest.fixture
def task(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "project/work_dir/fixture"
    root.mkdir(parents=True)
    monkeypatch.setattr("app.services.team_state.context_for", lambda *_: "")
    monkeypatch.setattr("app.services.competitions.context_for", lambda *_: "")
    monkeypatch.setattr("app.config.setting.settings.FALLBACK_MODEL", "")
    return root


def test_migration_preserves_old_rows_under_parallel_writers(task):
    legacy = entry("legacy")
    with sqlite3.connect(task / ".calls.sqlite3") as db:
        db.execute(
            "CREATE TABLE calls (attempt_id TEXT PRIMARY KEY, call_id TEXT, role TEXT, model TEXT, status TEXT, started_at TEXT, elapsed_seconds REAL, prompt_tokens INTEGER, completion_tokens INTEGER, cost REAL, currency TEXT, error_code TEXT)"
        )
        db.execute(
            "INSERT INTO calls VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", tuple(legacy.values())
        )
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(
            pool.map(
                lambda n: call_ledger.record(
                    "fixture", entry(str(n), purpose="normal_work")
                ),
                range(12),
            )
        )
    # 相同尝试再次保存不能新增一次调用。
    call_ledger.record("fixture", entry("0", purpose="normal_work"))
    with sqlite3.connect(task / ".calls.sqlite3") as db:
        db.row_factory = sqlite3.Row
        old = dict(
            db.execute("SELECT * FROM calls WHERE attempt_id='legacy'").fetchone()
        )
    assert all(old[k] == v for k, v in legacy.items())
    assert old["purpose"] is None and old["run_id"] is None
    result = call_ledger.summary(task)
    assert result["attempts"] == 13 and result["purpose_counts"] == {
        "unknown": 1,
        "normal_work": 12,
    }
    assert not result["metadata_complete"] and result["cost"] is None


def test_overlap_is_not_summed_as_wall_time_and_diagnostics_are_sanitized(task):
    call_ledger.record(
        "fixture",
        entry(
            "a",
            finished_at="2026-10-03T00:00:04+00:00",
            purpose="normal_work",
            retry_wait_seconds=1,
        ),
    )
    second = entry(
        "b",
        finished_at="2026-10-03T00:00:06+00:00",
        purpose="secret-canary",
        retry_wait_seconds=2,
    )
    second["started_at"] = "2026-10-03T00:00:02+00:00"
    call_ledger.record("fixture", second)
    result = runtime_diagnostics.diagnostic_preview(task)["model_calls"]
    assert result["request_work_seconds"] == 8
    assert result["request_active_seconds"] == 6
    assert result["observed_request_span_seconds"] == 6
    assert result["retry_wait_work_seconds"] == 3
    assert result["requests_with_intervals"] == 2
    assert result["requests_with_retry_wait"] == 2
    assert "secret-canary" not in json.dumps(result)


def test_late_started_write_cannot_erase_finished_usage(task):
    finished = entry("same", purpose="normal_work")
    finished.update(prompt_tokens=12, completion_tokens=4)
    call_ledger.record("fixture", finished)
    delayed = entry("same")
    delayed.update(status="started_outcome_unknown", elapsed_seconds=0)
    call_ledger.record("fixture", delayed)
    result = call_ledger.summary(task)
    assert result["attempts"] == 1 and result["prompt_tokens"] == 12
    assert result["usage_complete"]


def test_scope_isolated_for_parallel_questions_and_restored(task):
    async def run():
        async def one(n):
            with call_ledger.scope(
                "fixture",
                run_id=str(n) * 32,
                stage_id=f"write:ques{n}",
                purpose="paper_revision",
            ):
                await asyncio.sleep(0)
                return call_ledger.context("fixture"), call_ledger.context("other")

        return await asyncio.gather(one(1), one(2))

    result = asyncio.run(run())
    assert [a["question_id"] for a, b in result] == ["ques1", "ques2"]
    assert all(b["run_id"] is None for a, b in result)
    assert call_ledger.context("fixture")["run_id"] is None


def test_retry_keeps_logical_call_and_purpose_and_actual_wait(task, monkeypatch):
    actual_waits = []
    real_sleep = asyncio.sleep

    async def measured_sleep(delay):
        started = time.perf_counter()
        await real_sleep(delay + 0.02)
        actual_waits.append(time.perf_counter() - started)

    monkeypatch.setattr(asyncio, "sleep", measured_sleep)
    model = LLM(api_key="fixture", model="fixture", task_id="fixture")
    model.provider.call = AsyncMock(
        side_effect=[
            RuntimeError("temporary"),
            StandardResponse(content="ok", usage=Usage(3, 2, True)),
        ]
    )
    (task / "workflow_state.json").write_text(
        json.dumps({"execution_id": "a" * 32, "current_node": "solve:ques2"})
    )
    chat_started = time.perf_counter()
    asyncio.run(
        model.chat(
            publish=False, purpose="code_repair", max_retries=2, retry_delay=0.02
        )
    )
    chat_elapsed = time.perf_counter() - chat_started
    with sqlite3.connect(task / ".calls.sqlite3") as db:
        db.row_factory = sqlite3.Row
        rows = [
            dict(r) for r in db.execute("SELECT * FROM calls ORDER BY request_index")
        ]
    assert len(rows) == 2 and rows[0]["call_id"] == rows[1]["call_id"]
    assert [r["purpose"] for r in rows] == ["code_repair", "transport_retry"]
    assert {r["logical_purpose"] for r in rows} == {"code_repair"}
    assert {r["run_id"] for r in rows} == {"a" * 32}
    assert {r["question_id"] for r in rows} == {"ques2"}
    assert len(actual_waits) == 1
    # Windows timers can wake slightly before the requested delay. Compare the
    # ledger with the actual sleep, rather than treating the delay as a clock.
    assert rows[0]["retry_wait_seconds"] >= actual_waits[0] - 0.000001
    assert rows[0]["retry_wait_seconds"] <= chat_elapsed
    assert rows[0]["prompt_tokens"] is None and rows[1]["prompt_tokens"] == 3
    assert call_ledger.summary(task)["transport_retries"] == 1


def test_fallback_records_actual_model_and_keeps_call_id(task, monkeypatch):
    from app.config.setting import settings

    model = LLM(
        api_key="fixture",
        model="primary",
        task_id="fixture",
        api_type="openai-chat",
        base_url="https://fixture.invalid/v1",
    )
    model.capability_role = "coordinator"
    model.provider.call = AsyncMock(side_effect=RuntimeError("temporary"))
    fallback = type("Provider", (), {})()
    fallback.call = AsyncMock(return_value=StandardResponse(content="ok"))
    monkeypatch.setattr(settings, "FALLBACK_MODEL", "alternate")
    monkeypatch.setattr(settings, "FALLBACK_API_KEY", "fixture")
    monkeypatch.setattr(settings, "FALLBACK_BASE_URL", "https://fixture.invalid/v1")
    monkeypatch.setattr(settings, "FALLBACK_API_TYPE", "openai-chat")
    monkeypatch.setattr(settings, "FALLBACK_ENABLED", True)
    from app.services import model_capabilities as profiles, api_probe

    monkeypatch.setattr(profiles, "USER_CONFIG_PATH", task / ".env.user")
    config = profiles.fallback_config("coordinator")
    profiles.profile_path("fallback-coordinator").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "fingerprint": api_probe.capability_fingerprint(config),
                "connection": "supported",
                "text": "supported",
                "structured_output": "supported",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("app.core.llm.llm._resolve_provider", lambda _: fallback)
    asyncio.run(model.chat(publish=False, max_retries=1))
    with sqlite3.connect(task / ".calls.sqlite3") as db:
        rows = db.execute(
            "SELECT call_id, model, is_fallback, request_index FROM calls ORDER BY request_index"
        ).fetchall()
    assert rows[0][0] == rows[1][0]
    assert rows[0][1:] == ("primary", 0, 1)
    assert rows[1][1:] == ("alternate", 1, 2)


def test_cancel_during_backoff_records_partial_wait_without_new_attempt(
    task, monkeypatch
):
    original_sleep = asyncio.sleep
    model = LLM(api_key="fixture", model="fixture", task_id="fixture")
    model.provider.call = AsyncMock(side_effect=RuntimeError("temporary"))

    async def run():
        waiting = asyncio.Event()

        async def sleep(delay):
            if delay == 30:
                waiting.set()
            await original_sleep(delay)

        monkeypatch.setattr("app.core.llm.llm._retry_delay_seconds", lambda *_: 30)
        monkeypatch.setattr(asyncio, "sleep", sleep)
        job = asyncio.create_task(model.chat(publish=False, max_retries=2))
        await asyncio.wait_for(waiting.wait(), 2)
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job

    asyncio.run(run())
    model.provider.call.assert_awaited_once()
    result = call_ledger.summary(task)
    assert result["attempts"] == 1
    assert result["requests_with_retry_wait"] == 1
    assert 0 < result["retry_wait_work_seconds"] < 2
