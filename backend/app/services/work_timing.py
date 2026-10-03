"""本地工作区的操作计时；与调用账本共用数据库，不保存输入或输出。"""

import asyncio
import sqlite3
import time
from contextlib import asynccontextmanager, closing, contextmanager
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from uuid import uuid4

from app.services.async_io import WorkCancelled, run_blocking
from app.services.call_ledger import context, active_task_id
from app.utils.log_util import logger

CATEGORIES = {"computation", "latex", "conversion", "writing", "queue"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Span:
    """开始先持久化；进程意外退出时保留未结束状态，不补造耗时。"""

    def __init__(self, task_id: str | None, category: str):
        self.task_id = task_id
        self.category = category
        self.status = "completed"
        self.root = None
        self.row = None
        self.started = None

    def start(self):
        if not self.task_id or self.category not in CATEGORIES:
            return
        from app.utils.common_utils import get_work_dir

        try:
            self.root = Path(get_work_dir(self.task_id))
            meta = context(self.task_id)
            self.row = {
                "span_id": uuid4().hex,
                "category": self.category,
                "run_id": meta["run_id"],
                "stage_id": meta["stage_id"],
                "question_id": meta["question_id"],
                "status": "started_outcome_unknown",
                "started_at": now(),
                "finished_at": None,
                "elapsed_seconds": None,
            }
            self.started = time.perf_counter()
            self._save()
        except (OSError, ValueError, sqlite3.Error):
            logger.warning("工作计时暂时不可写，原操作继续执行")

    def _save(self):
        if self.root is None or self.row is None:
            return
        with closing(sqlite3.connect(self.root / ".calls.sqlite3", timeout=3)) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS work_spans (
                span_id TEXT PRIMARY KEY, category TEXT, run_id TEXT, stage_id TEXT,
                question_id TEXT, status TEXT, started_at TEXT, finished_at TEXT,
                elapsed_seconds REAL)""")
            db.execute(
                """INSERT INTO work_spans VALUES (
                :span_id,:category,:run_id,:stage_id,:question_id,:status,:started_at,:finished_at,:elapsed_seconds)
                ON CONFLICT(span_id) DO UPDATE SET status=excluded.status,
                finished_at=excluded.finished_at,elapsed_seconds=excluded.elapsed_seconds
                WHERE excluded.status!='started_outcome_unknown'
                OR work_spans.status='started_outcome_unknown'""",
                self.row,
            )
            db.commit()

    def finish(self, status: str):
        if self.row is None or self.started is None:
            return
        self.row.update(
            status=status,
            finished_at=now(),
            elapsed_seconds=round(time.perf_counter() - self.started, 6),
        )
        try:
            self._save()
        except (OSError, ValueError, sqlite3.Error):
            logger.warning("工作计时结束记录暂时不可写，不重新执行原操作")


@contextmanager
def measure(task_id: str | None, category: str):
    span = Span(task_id, category)
    span.start()
    try:
        yield span
    except (asyncio.CancelledError, WorkCancelled):
        span.status = "cancelled"
        raise
    except BaseException:
        span.status = "failed"
        raise
    finally:
        span.finish(span.status)


@asynccontextmanager
async def ameasure(task_id: str | None, category: str):
    span = Span(task_id, category)
    try:
        # 等待持久化线程确实退出，避免取消后迟到的开始写入覆盖结束。
        await run_blocking(span.start)
        yield span
    except (asyncio.CancelledError, WorkCancelled):
        span.status = "cancelled"
        raise
    except BaseException:
        span.status = "failed"
        raise
    finally:
        await run_blocking(span.finish, span.status)


def timed_sync(category: str):
    """线程继承调用方上下文；无任务上下文的环境自检不写项目账本。"""

    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            with measure(active_task_id(), category) as span:
                result = function(*args, **kwargs)
                if getattr(result, "returncode", 0):
                    span.status = "failed"
                return result

        return wrapped

    return decorate


def summary(root: Path, *, state: dict | None = None) -> dict:
    """仅汇总明确结束的操作，未结束与历史未记录操作不冒充零耗时。"""
    path = root / ".calls.sqlite3"
    result = {
        "categories": {},
        "scope": "observed_operations_not_end_to_end",
        "workflow": workflow_summary(root, state=state),
    }
    if not path.is_file():
        return result
    try:
        with closing(
            sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        ) as db:
            if not db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='work_spans'"
            ).fetchone():
                return result
            # Group in one query so every category sees the same DB snapshot.
            categories = sorted(CATEGORIES)
            rows = db.execute(
                "SELECT category, COUNT(*), COUNT(elapsed_seconds), "
                "SUM(elapsed_seconds), SUM(status='failed'), SUM(status='cancelled') "
                f"FROM work_spans WHERE category IN ({','.join('?' for _ in categories)}) "
                "GROUP BY category ORDER BY category",
                categories,
            )
            for kind, count, ended, seconds, failed, cancelled in rows:
                result["categories"][kind] = {
                    "count": count,
                    "measured": ended,
                    "work_seconds": round(seconds, 6) if seconds is not None else None,
                    "unfinished": count - ended,
                    "failed": failed,
                    "cancelled": cancelled,
                }
    except (OSError, sqlite3.Error):
        result["status"] = "unavailable"
    return result


def _seconds(start, end):
    try:
        left, right = datetime.fromisoformat(start), datetime.fromisoformat(end)
        if left.tzinfo and right.tzinfo and right >= left:
            return round((right - left).total_seconds(), 6)
    except (TypeError, ValueError):
        pass
    return None


def workflow_summary(root: Path, *, state: dict | None = None) -> dict:
    """Use the caller's checkpoint when present, keeping one response consistent."""
    from app.services.writing_workspace import read_json

    if state is None:
        try:
            state = read_json(root / "workflow_state.json")
        except (OSError, ValueError):
            return {"status": "unavailable"}
    if not isinstance(state, dict):
        return {}
    nodes = state.get("node_timings") or []
    nodes = nodes if isinstance(nodes, list) else []
    measured = [
        _seconds(n.get("started_at"), n.get("finished_at"))
        for n in nodes
        if isinstance(n, dict)
    ]
    known = [value for value in measured if value is not None]
    waits = []
    for key in ("approval_history", "cancelled_approval_timings"):
        if isinstance(state.get(key), list):
            waits.extend(state[key])
    waits = [
        item
        for item in waits
        if isinstance(item, dict) and item.get("decision") != "auto_continue"
    ]
    seconds = [
        _seconds(item.get("requested_at"), item.get("decided_at")) for item in waits
    ]
    known_waits = [value for value in seconds if value is not None]
    pending = state.get("pending_approval") or {}
    pending = pending if isinstance(pending, dict) else {}
    return {
        "modeling_wall_seconds": _seconds(
            state.get("created_at"), state.get("completed_at")
        )
        if state.get("status") == "completed"
        else None,
        "first_question_completed_seconds": _seconds(
            state.get("created_at"), state.get("first_question_completed_at")
        ),
        "node_runs": len(measured),
        "measured_node_runs": len(known),
        "node_work_seconds": round(sum(known), 6) if known else None,
        "closed_human_waits": len(waits),
        "measured_human_waits": len(known_waits),
        "closed_human_wait_seconds": round(sum(known_waits), 6)
        if known_waits
        else None,
        "current_human_wait_seconds": _seconds(pending.get("requested_at"), now())
        if pending
        else None,
        "scope": "modeling_lifecycle_includes_pauses_and_review_not_paper_generation",
    }
