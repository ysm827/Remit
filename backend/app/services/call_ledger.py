"""模型调用尝试账本：不存储请求内容、地址或密钥，未知用量不记为零。"""

import sqlite3
import json
import hashlib
import re
from contextlib import closing, contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import uuid4

CallPurpose = Literal[
    "normal_work",
    "structure_repair",
    "code_repair",
    "context_summary",
    "paper_revision",
]
_scope: ContextVar[dict] = ContextVar("call_ledger_scope", default={})
_PURPOSES = {
    "normal_work",
    "structure_repair",
    "code_repair",
    "context_summary",
    "paper_revision",
    "transport_retry",
}
_EXTRA_COLUMNS = {
    "run_id": "TEXT",
    "stage_id": "TEXT",
    "question_id": "TEXT",
    "purpose": "TEXT",
    "logical_purpose": "TEXT",
    "request_index": "INTEGER",
    "is_fallback": "INTEGER",
    "retry_wait_seconds": "REAL",
    "finished_at": "TEXT",
}


def active_task_id() -> str | None:
    """让无 task_id 参数的转换工具使用显式作用域，不根据路径猜项目。"""
    return _scope.get().get("task_id")


@contextmanager
def scope(task_id: str, **metadata):
    """异步子任务各自继承调用上下文，退出时恢复，避免并行章节互相串账。"""
    previous = _scope.get()
    values = previous if previous.get("task_id") == task_id else {}
    token = _scope.set({**values, **metadata, "task_id": task_id})
    try:
        yield
    finally:
        _scope.reset(token)


def context(task_id: str, sub_title: str | None = None, agent_name: str = "") -> dict:
    """在逻辑调用开始时冻结可核实的标识；旧项目缺失标识时保留空值。"""
    from app.utils.common_utils import get_work_dir
    from app.services.writing_workspace import read_json

    state = {}
    if task_id:
        try:
            state = read_json(Path(get_work_dir(task_id)) / "workflow_state.json")
        except (OSError, ValueError):
            pass
    current = _scope.get()
    if not isinstance(state, dict):
        state = {}
    current = current if current.get("task_id") == task_id else {}
    stage = current.get("stage_id", state.get("current_node"))
    if "Writer" in agent_name and sub_title and not current.get("stage_id"):
        stage = f"write:{sub_title}"
    # 只保存已知节点标识，不把用户自定义标题或章节内容带入诊断包。
    pattern = r"(?:solve:|write:)?(?:ques\d+|eda|sensitivity_analysis|firstPage|RepeatQues|analysisQues|modelAssumption|symbol|judge)|preflight|coordinator|research|analysis|modeler|pilot|finalize|sync_writing|paper:(?:proposal|compile|assemble)"
    stage = stage if isinstance(stage, str) and re.fullmatch(pattern, stage) else None
    section = re.match(r"^(ques\d+)(?:$|-)", sub_title or "")
    question = section.group(1) if section else None
    if not question and stage:
        match = re.search(r"(?:^|:)ques(\d+)$", stage)
        question = f"ques{match.group(1)}" if match else None
    run_id = current.get("run_id", state.get("execution_id"))
    return {
        "run_id": run_id
        if isinstance(run_id, str) and re.fullmatch(r"[0-9a-f]{32}", run_id)
        else None,
        "stage_id": stage,
        "question_id": question,
        "logical_purpose": current.get("purpose")
        if current.get("purpose") in _PURPOSES
        else "normal_work",
    }


def _ensure_calls(db: sqlite3.Connection) -> None:
    # 在同一写事务内迁移，两个并行章节不会同时添加同名列。
    db.execute("BEGIN IMMEDIATE")
    db.execute("""CREATE TABLE IF NOT EXISTS calls (
        attempt_id TEXT PRIMARY KEY, call_id TEXT, role TEXT, model TEXT,
        status TEXT, started_at TEXT, elapsed_seconds REAL,
        prompt_tokens INTEGER, completion_tokens INTEGER, cost REAL, currency TEXT,
        error_code TEXT)""")
    columns = {row[1] for row in db.execute("PRAGMA table_info(calls)")}
    for name, kind in _EXTRA_COLUMNS.items():
        if name not in columns:
            db.execute(f"ALTER TABLE calls ADD COLUMN {name} {kind}")


def record(task_id: str, entry: dict) -> None:
    """用调用及尝试编号幂等更新；失败不可触发模型重新调用。"""
    if not task_id:
        return
    from app.utils.common_utils import get_work_dir

    root = Path(get_work_dir(task_id))
    with closing(sqlite3.connect(root / ".calls.sqlite3", timeout=3)) as db:
        _ensure_calls(db)
        values = {**dict.fromkeys(_EXTRA_COLUMNS), **entry}
        columns = [
            "attempt_id",
            "call_id",
            "role",
            "model",
            "status",
            "started_at",
            "elapsed_seconds",
            "prompt_tokens",
            "completion_tokens",
            "cost",
            "currency",
            "error_code",
            *_EXTRA_COLUMNS,
        ]
        db.execute(
            f"INSERT INTO calls ({','.join(columns)}) VALUES ({','.join(':' + c for c in columns)}) "
            f"ON CONFLICT(attempt_id) DO UPDATE SET {','.join(c + '=excluded.' + c for c in columns if c != 'attempt_id')} "
            "WHERE excluded.status != 'started_outcome_unknown' OR calls.status = 'started_outcome_unknown'",
            values,
        )
        db.commit()


def model_stage_limits(state: dict) -> tuple[int, float]:
    """Pilot includes separate experiments for each approved question.

    Keep one durable ledger key and all prior usage. Only a matching, saved
    pilot plan expands the composite stage's allowance; ordinary nodes and
    incomplete/mismatched plans retain the configured single-stage limits.
    """
    from app.config.setting import settings

    units = 1
    if state.get("current_node") == "pilot":
        expected = {
            key
            for key in (state.get("questions") or {})
            if re.fullmatch(r"ques\d+", key)
        }
        planned = (state.get("pilot_plan") or {}).get("questions") or {}
        if expected and set(planned) == expected:
            units = len(expected)
    return settings.LLM_STAGE_CALL_LIMIT * units, settings.LLM_STAGE_API_SECONDS * units


def reserve(task_id: str, purpose: str, call_id: str, attempt_id: str) -> float | None:
    """在实际调用前原子预占阶段预算；重启与技术恢复不能重置次数。"""
    if not task_id:
        return
    from app.utils.common_utils import get_work_dir
    from app.services.writing_workspace import read_json
    from app.core.llm.errors import ModelStageBudgetExceeded

    try:
        root = Path(get_work_dir(task_id))
    except FileNotFoundError:
        return
    state = read_json(root / "workflow_state.json")
    paper = (
        read_json(root / "paper/input.json")
        if purpose.startswith("WriterAgent")
        else {}
    )
    identity = {
        "node": state.get("current_node") or purpose,
        "revisions": state.get("revision_counts") or {},
        "paper": paper.get("revision"),
    }
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    call_limit, seconds_limit = model_stage_limits(state)
    with closing(sqlite3.connect(root / ".calls.sqlite3", timeout=3)) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS reservations (attempt_id TEXT PRIMARY KEY, call_id TEXT, stage_key TEXT)"
        )
        db.execute("BEGIN IMMEDIATE")
        used = db.execute(
            "SELECT COUNT(*) FROM reservations WHERE stage_key=?", (key,)
        ).fetchone()[0]
        elapsed = 0.0
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='calls'").fetchone():
            elapsed = db.execute(
                "SELECT COALESCE(SUM(c.elapsed_seconds),0) FROM calls c JOIN reservations r ON c.attempt_id=r.attempt_id WHERE r.stage_key=?",
                (key,),
            ).fetchone()[0]
        remaining = seconds_limit - elapsed
        if used >= call_limit or remaining <= 0:
            raise ModelStageBudgetExceeded(
                used_calls=used,
                call_limit=call_limit,
                elapsed_seconds=elapsed,
                seconds_limit=seconds_limit,
            )
        db.execute(
            "INSERT OR IGNORE INTO reservations VALUES(?,?,?)",
            (attempt_id, call_id, key),
        )
        db.commit()
        return remaining


class ExecutionBudgetExceeded(RuntimeError):
    """A durable execution reservation cannot be granted for this stage."""

    def __init__(self, used: int, limit: int):
        self.used, self.limit = used, limit
        super().__init__(
            f"本阶段累计代码执行额度已用完（已预占 {used}/{limit} 次）；"
            "已保存成果保留。普通恢复不会重置额度，请检查现有结果，"
            "按需退回修改或调整 MAX_CODE_EXECUTIONS_PER_STAGE。"
        )


class ExecutionBudgetUnavailable(RuntimeError):
    """Cannot safely read or reserve the execution budget; no code may run."""


class ExecutionBudgetConflict(RuntimeError):
    """The reviewed budget no longer matches the task or a prior request."""


@contextmanager
def _execution_database(root: Path):
    try:
        with closing(sqlite3.connect(root / ".calls.sqlite3", timeout=3)) as db:
            yield db
    except (OSError, sqlite3.Error) as exc:
        raise ExecutionBudgetUnavailable(
            "代码执行额度账本不可用，已保留成果并停止执行"
        ) from exc


@dataclass(frozen=True)
class ExecutionBudget:
    """Freeze stage identity per run; reserve before execution, including failures.

    A crash after reservation may consume an unused slot. Do not refund unknown
    outcomes or infer historical execution counts from missing legacy records.
    """

    root: Path
    stage_key: str
    limit: int

    @staticmethod
    def _ensure_schema(db):
        db.execute(
            "CREATE TABLE IF NOT EXISTS execution_reservations ("
            "reservation_id TEXT PRIMARY KEY, stage_key TEXT, reserved_at TEXT)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS execution_stage_key "
            "ON execution_reservations(stage_key)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS execution_budget_grants ("
            "request_id TEXT PRIMARY KEY, stage_key TEXT, additional INTEGER, "
            "expected_used INTEGER, expected_limit INTEGER, approved_at TEXT, "
            "resume_scheduled INTEGER NOT NULL DEFAULT 0)"
        )
        if "resume_scheduled" not in {
            row[1] for row in db.execute("PRAGMA table_info(execution_budget_grants)")
        }:
            db.execute(
                "ALTER TABLE execution_budget_grants ADD COLUMN resume_scheduled INTEGER NOT NULL DEFAULT 0"
            )

    def _counts(self, db) -> tuple[int, int]:
        tables = {
            row[0]
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        used = (
            db.execute(
                "SELECT COUNT(*) FROM execution_reservations WHERE stage_key=?",
                (self.stage_key,),
            ).fetchone()[0]
            if "execution_reservations" in tables
            else 0
        )
        additional = (
            db.execute(
                "SELECT COALESCE(SUM(additional),0) FROM execution_budget_grants WHERE stage_key=?",
                (self.stage_key,),
            ).fetchone()[0]
            if "execution_budget_grants" in tables
            else 0
        )
        return used, self.limit + additional

    def snapshot(self) -> dict:
        used, limit = 0, self.limit
        if (self.root / ".calls.sqlite3").is_file():
            with _execution_database(self.root) as db:
                used, limit = self._counts(db)
        return {
            "stage_key": self.stage_key,
            "used": used,
            "limit": limit,
            "remaining": max(0, limit - used),
        }

    def extend(
        self,
        request_id: str,
        stage_key: str,
        expected_used: int,
        expected_limit: int,
        additional: int,
    ) -> None:
        if (
            stage_key != self.stage_key
            or type(additional) is not int
            or not 1 <= additional <= 48
        ):
            raise ExecutionBudgetConflict("阶段或追加次数无效，请重新查看当前额度")
        with _execution_database(self.root) as db:
            db.execute("BEGIN IMMEDIATE")
            self._ensure_schema(db)
            previous = db.execute(
                "SELECT stage_key,additional,expected_used,expected_limit FROM execution_budget_grants WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if previous:
                if previous != (stage_key, additional, expected_used, expected_limit):
                    raise ExecutionBudgetConflict(
                        "该确认请求已用于其他额度，请重新查看"
                    )
                return  # Lost HTTP responses cannot grant the same allowance twice.
            used, limit = self._counts(db)
            if (used, limit) != (expected_used, expected_limit) or used < limit:
                raise ExecutionBudgetConflict(
                    "执行额度已变化或尚未用完，请重新查看后确认"
                )
            db.execute(
                "INSERT INTO execution_budget_grants (request_id,stage_key,additional,expected_used,expected_limit,approved_at) VALUES(?,?,?,?,?,?)",
                (
                    request_id,
                    stage_key,
                    additional,
                    used,
                    limit,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            db.commit()

    def mark_resume_scheduled(self, request_id: str) -> bool:
        """An uncertain HTTP response must not schedule a finished action again.

        A crash after this marker can leave scheduling unknown. The user can
        review remaining allowance and explicitly resume without another grant.
        """
        with _execution_database(self.root) as db:
            db.execute("BEGIN IMMEDIATE")
            self._ensure_schema(db)
            changed = db.execute(
                "UPDATE execution_budget_grants SET resume_scheduled=1 "
                "WHERE request_id=? AND stage_key=? AND resume_scheduled=0",
                (request_id, self.stage_key),
            ).rowcount
            db.commit()
            return bool(changed)

    def remaining(self, *, reserve: bool = False) -> int:
        with _execution_database(self.root) as db:
            db.execute("BEGIN IMMEDIATE")
            self._ensure_schema(db)
            used, limit = self._counts(db)
            if used >= limit:
                raise ExecutionBudgetExceeded(used, limit)
            if reserve:
                db.execute(
                    "INSERT INTO execution_reservations VALUES(?,?,?)",
                    (
                        uuid4().hex,
                        self.stage_key,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                used += 1
            db.commit()
            return limit - used

    def reserve(self) -> int:
        return self.remaining(reserve=True)


def execution_budget(task_id: str, subtask_title: str) -> ExecutionBudget | None:
    """Reuse the task ledger, with epochs controlled by checkpoint invalidation."""
    from app.config.setting import settings
    from app.utils.common_utils import get_work_dir

    if not task_id:
        return None
    try:
        root = Path(get_work_dir(task_id)).resolve()
    except FileNotFoundError:
        return None  # Standalone interpreter probes have no registered workflow.
    checkpoint = root / "workflow_state.json"
    try:
        state = (
            json.loads(checkpoint.read_text(encoding="utf-8-sig"))
            if checkpoint.exists()
            else {}
        )
    except (OSError, ValueError) as exc:
        raise ExecutionBudgetUnavailable("执行预算无法读取任务检查点") from exc
    if not isinstance(state, dict):
        raise ExecutionBudgetUnavailable("执行预算无法读取任务检查点")
    stage = state.get("current_node") or subtask_title
    epochs = state.get("execution_budget_epochs", {})
    if not isinstance(stage, str) or not isinstance(epochs, dict):
        raise ExecutionBudgetUnavailable("执行预算阶段信息无效")
    epoch = epochs.get(stage, 0)
    if type(epoch) is not int or epoch < 0:
        raise ExecutionBudgetUnavailable("执行预算阶段版本无效")
    # User-supplied standalone titles are hashed, never stored as ledger text.
    key = hashlib.sha256(json.dumps([stage, epoch]).encode()).hexdigest()
    return ExecutionBudget(root, key, settings.MAX_CODE_EXECUTIONS_PER_STAGE)


def summary(root: Path) -> dict:
    """费用尚无可信价格来源时保持 null，不套用默认低价。"""
    path = root / ".calls.sqlite3"
    empty = {
        "attempts": 0,
        "prompt_tokens": None,
        "completion_tokens": None,
        "cost": None,
        "currency": None,
        "usage_complete": False,
    }
    if not path.is_file():
        return empty
    try:
        with closing(
            sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        ) as db:
            db.row_factory = sqlite3.Row
            if not db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='calls'"
            ).fetchone():
                return empty
            count, known, prompt, completion = db.execute(
                "SELECT COUNT(*), COUNT(prompt_tokens), SUM(prompt_tokens), SUM(completion_tokens) FROM calls"
            ).fetchone()
            rows = [dict(row) for row in db.execute("SELECT * FROM calls")]
    except sqlite3.Error:
        return {**empty, "status": "unavailable"}
    return {
        "attempts": count,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cost": None,
        "currency": None,
        "usage_complete": count > 0 and known == count,
        **_timing_summary(rows),
    }


def _timing_summary(rows: list[dict]) -> dict:
    """请求工作量与并行合并跨度分别统计；不是任务端到端耗时。"""
    intervals = []
    purposes: dict[str, int] = {}
    for row in rows:
        purpose = row.get("purpose") if row.get("purpose") in _PURPOSES else "unknown"
        purposes[purpose] = purposes.get(purpose, 0) + 1
        try:
            start = datetime.fromisoformat(row["started_at"])
            end = datetime.fromisoformat(row["finished_at"])
            if start.tzinfo and end.tzinfo and end >= start:
                intervals.append((start.timestamp(), end.timestamp()))
        except (KeyError, TypeError, ValueError):
            pass
    merged: list[list[float]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    waits = [
        row["retry_wait_seconds"]
        for row in rows
        if row.get("retry_wait_seconds") is not None
    ]
    elapsed = [
        row["elapsed_seconds"] for row in rows if row.get("elapsed_seconds") is not None
    ]
    return {
        "purpose_counts": purposes,
        "transport_retries": sum(
            row.get("purpose") == "transport_retry" for row in rows
        ),
        "fallback_requests": sum(bool(row.get("is_fallback")) for row in rows),
        "request_work_seconds": round(sum(elapsed), 6) if elapsed else None,
        "retry_wait_work_seconds": round(sum(waits), 6) if waits else None,
        "request_active_seconds": round(sum(end - start for start, end in merged), 6)
        if merged
        else None,
        "observed_request_span_seconds": round(merged[-1][1] - merged[0][0], 6)
        if merged
        else None,
        "timing_complete": bool(rows) and len(intervals) == len(rows),
        "requests_with_intervals": len(intervals),
        "requests_with_retry_wait": len(waits),
        "metadata_complete": bool(rows)
        and all(row.get("purpose") and row.get("run_id") for row in rows),
    }
