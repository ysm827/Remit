"""实际操作与工作流时间记录的失败、取消和历史边界。"""

import asyncio
import sqlite3
from unittest.mock import AsyncMock

import pytest

from app.core.workflow_checkpoint import WorkflowCheckpoint
from app.schemas.request import Problem
from app.services import call_ledger, work_timing
from app.services.async_io import WorkCancelled, run_blocking


@pytest.fixture
def task(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "project/work_dir/timing"
    root.mkdir(parents=True)
    return root


def test_operation_status_and_unfinished_are_not_zero(task):
    with work_timing.measure("timing", "computation"):
        sum(range(10000))
    with pytest.raises(ValueError):
        with work_timing.measure("timing", "latex"):
            raise ValueError("private content must not be stored")
    with pytest.raises(WorkCancelled):
        with work_timing.measure("timing", "conversion"):
            raise WorkCancelled()
    work_timing.Span("timing", "writing").start()
    groups = work_timing.summary(task)["categories"]
    assert groups["computation"]["work_seconds"] > 0
    assert groups["latex"]["failed"] == 1
    assert groups["conversion"]["cancelled"] == 1
    assert groups["writing"]["unfinished"] == 1
    assert groups["writing"]["work_seconds"] is None
    assert call_ledger.summary(task)["attempts"] == 0
    assert "status" not in call_ledger.summary(task)
    assert b"private content" not in (task / ".calls.sqlite3").read_bytes()


def test_measurement_failure_does_not_repeat_or_fail_operation(task, monkeypatch):
    def locked(_):
        raise sqlite3.OperationalError("locked")

    monkeypatch.setattr(work_timing.Span, "_save", locked)
    count = []
    with work_timing.measure("timing", "computation"):
        count.append(1)
    assert count == [1]


def test_thread_context_and_cancelled_async_span(task):
    @work_timing.timed_sync("conversion")
    def convert():
        return 7

    async def run():
        with call_ledger.scope("timing", run_id="a" * 32, stage_id="paper:assemble"):
            assert await run_blocking(convert) == 7
        ready = asyncio.Event()

        async def waiting():
            async with work_timing.ameasure("timing", "queue"):
                ready.set()
                await asyncio.Event().wait()

        job = asyncio.create_task(waiting())
        await asyncio.wait_for(ready.wait(), 2)
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job

    asyncio.run(run())
    with sqlite3.connect(task / ".calls.sqlite3") as db:
        row = db.execute(
            "SELECT run_id,stage_id FROM work_spans WHERE category='conversion'"
        ).fetchone()
    assert row == ("a" * 32, "paper:assemble")
    assert work_timing.summary(task)["categories"]["queue"]["cancelled"] == 1


def test_checkpoint_separates_human_wait_and_restart_unknown_time(task, monkeypatch):
    stamp = ["2026-10-03T00:00:00+00:00"]
    cp = WorkflowCheckpoint(task)
    monkeypatch.setattr(cp, "_now", lambda: stamp[0])
    (task / ".calls.sqlite3").touch()
    state = cp.initialize(Problem(task_id="timing", ques_all="fixture"))
    assert ".calls.sqlite3" not in state["protected_input_files"]
    state["execution_id"] = "a" * 32
    stamp[0] = "2026-10-03T00:00:01+00:00"
    cp.start_node(state, "solve:ques1")
    stamp[0] = "2026-10-03T00:00:05+00:00"
    cp.complete_node(state, "solve:ques1")
    pending = cp.request_approval(state, "solve:ques1", summary="review")
    stamp[0] = "2026-10-03T00:00:25+00:00"
    cp.approve(state, pending["checkpoint_id"])
    stamp[0] = "2026-10-03T00:00:30+00:00"
    cp.mark_status("completed")
    result = work_timing.workflow_summary(task)
    assert result["node_work_seconds"] == 4
    assert result["closed_human_wait_seconds"] == 20
    assert result["first_question_completed_seconds"] == 5
    assert result["modeling_wall_seconds"] == 30
    state = cp.load()
    state["execution_id"] = "b" * 32
    stamp[0] = "2026-10-03T00:00:40+00:00"
    cp.start_node(state, "solve:ques2")
    state["execution_id"] = "c" * 32
    stamp[0] = "2026-10-03T00:01:20+00:00"
    cp.start_node(state, "solve:ques2")
    assert state["node_timings"][-2]["finished_at"] is None
    assert state["node_timings"][-2]["status"] == "interrupted_end_unknown"
    result = work_timing.workflow_summary(task)
    assert result["node_work_seconds"] == 4 and result["measured_node_runs"] == 1
    assert result["modeling_wall_seconds"] is None


def test_python_lock_release_and_cancelled_waiter_preserve_owner(task):
    from app.tools.local_interpreter import LocalCodeInterpreter
    from app.tools.notebook_serializer import NotebookSerializer

    interpreter = LocalCodeInterpreter(
        "timing", str(task), NotebookSerializer(str(task))
    )
    interpreter._execute_code_locked = AsyncMock(return_value=("ok", False, ""))

    async def run():
        assert await interpreter.execute_code("1") == ("ok", False, "")
        assert not interpreter._execution_lock.locked()
        # 已有锁被占用时取消只结束本次排队，不能释放其他持有者的锁。
        await interpreter._execution_lock.acquire()
        job = asyncio.create_task(interpreter.execute_code("2"))
        await asyncio.sleep(0.02)
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job
        assert interpreter._execution_lock.locked()
        interpreter._execution_lock.release()

    asyncio.run(run())
    interpreter._execute_code_locked.assert_awaited_once()


def test_team_snapshot_keeps_timing_on_same_checkpoint(task, monkeypatch):
    from app.services import team_state
    from app.services.writing_workspace import write_json

    first = {
        "status": "running",
        "created_at": "2026-10-03T00:00:00+00:00",
        "current_node": "solve:ques1",
    }
    second = {
        **first,
        "status": "completed",
        "completed_at": "2026-10-03T00:00:30+00:00",
    }
    write_json(task / "workflow_state.json", first)
    original = work_timing.summary

    def advance_checkpoint(root, **kwargs):
        write_json(task / "workflow_state.json", second)
        return original(root, **kwargs)

    monkeypatch.setattr(work_timing, "summary", advance_checkpoint)
    observed = team_state.snapshot(task)
    assert observed["status"] == "running"
    assert observed["timing"]["workflow"]["modeling_wall_seconds"] is None
    following = team_state.snapshot(task)
    assert following["status"] == "completed"
    assert following["timing"]["workflow"]["modeling_wall_seconds"] == 30


def test_empty_supplied_checkpoint_does_not_reread_newer_file(task):
    from app.services.writing_workspace import write_json

    write_json(
        task / "workflow_state.json",
        {
            "status": "completed",
            "created_at": "2026-10-03T00:00:00+00:00",
            "completed_at": "2026-10-03T00:00:30+00:00",
        },
    )
    assert (
        work_timing.summary(task, state={})["workflow"]["modeling_wall_seconds"] is None
    )
    assert work_timing.summary(task)["workflow"]["modeling_wall_seconds"] == 30
