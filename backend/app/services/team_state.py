"""项目共享状态：检查点是执行事实，SQLite 保存对话、分工与逐步事件。"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.utils.common_utils import get_work_dir
from app.utils.file_types import input_filenames

ROLES = {
    "coordinator": "协调者",
    "modeler": "建模手",
    "coder": "代码手",
    "writer": "论文手",
}
AGENTS = {
    "CoordinatorAgent": "coordinator",
    "ModelerAgent": "modeler",
    "CoderAgent": "coder",
    "WriterAgent": "writer",
}
compiling_tasks: set[str] = set()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def database(root: Path):
    """每次操作独立事务，线程与并行角色共享同一日志。"""
    connection = sqlite3.connect(root / ".team.sqlite3", timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, event_key TEXT UNIQUE,
                at TEXT NOT NULL, role TEXT NOT NULL, kind TEXT NOT NULL,
                content TEXT NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS commands (
                id TEXT PRIMARY KEY, content TEXT NOT NULL, status TEXT NOT NULL,
                result TEXT NOT NULL DEFAULT '{}');
            CREATE TABLE IF NOT EXISTS directives (
                id TEXT PRIMARY KEY, role TEXT NOT NULL, content TEXT NOT NULL,
                at TEXT NOT NULL, seen TEXT NOT NULL DEFAULT '[]');
            CREATE TABLE IF NOT EXISTS queued_directives (
                id TEXT PRIMARY KEY, role TEXT NOT NULL, content TEXT NOT NULL,
                node TEXT NOT NULL, released INTEGER NOT NULL DEFAULT 0);
        """)
        with connection:
            yield connection
    finally:
        connection.close()


def record(
    root: Path,
    role: str,
    kind: str,
    content: str,
    data: dict | None = None,
    *,
    key: str | None = None,
    at: str | None = None,
) -> None:
    """追加不可变事件；重放旧消息按稳定键去重。"""
    with database(root) as db:
        if kind == "activity":
            # Streaming heartbeats describe the same ongoing action, not new work.
            # Compare inside the transaction, without changing existing event IDs.
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT role,kind,content,data FROM events ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            if previous and (
                previous["role"],
                previous["kind"],
                previous["content"],
            ) == (role, kind, content):
                old = json.loads(previous["data"])
                if all(
                    old.get(field) == (data or {}).get(field)
                    for field in ("category", "detail")
                ):
                    return
        db.execute(
            "INSERT OR IGNORE INTO events(event_key,at,role,kind,content,data) VALUES(?,?,?,?,?,?)",
            (
                key or uuid4().hex,
                at or now(),
                role,
                kind,
                content,
                json.dumps(data or {}, ensure_ascii=False, default=str),
            ),
        )


def record_message(task_id: str, message: dict, *, scope: str = "modeling") -> None:
    """统一收集 Agent、工具、进度和论文事件，不改变建模任务状态。"""
    try:
        root = Path(get_work_dir(task_id))
    except (ValueError, FileNotFoundError):
        return
    kind = str(message.get("msg_type", "system"))
    role = AGENTS.get(
        message.get("agent_type"), "writer" if scope == "writing" else "coordinator"
    )
    if kind == "user":
        role = "user"
    elif kind == "tool":
        role = "coder" if message.get("tool_name") == "execute_code" else "coordinator"
    content = str(
        message.get("content")
        or message.get("summary")
        or message.get("tool_name")
        or "进度更新"
    )
    if kind == "activity":
        for candidate, label in ROLES.items():
            if label in content:
                role = candidate
    identity = f"{scope}:{message.get('id')}:{message.get('created_at')}"
    record(
        root, role, kind, content, message, key=identity, at=message.get("created_at")
    )


def events(root: Path, after: int = 0, limit: int = 200) -> list[dict]:
    with database(root) as db:
        rows = db.execute(
            "SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT ?", (after, limit)
        ).fetchall()
    return [{**dict(row), "data": json.loads(row["data"])} for row in rows]


def directive(root: Path, role: str, content: str, command_id: str) -> None:
    with database(root) as db:
        db.execute(
            "INSERT OR IGNORE INTO directives(id,role,content,at) VALUES(?,?,?,?)",
            (command_id, role, content, now()),
        )
    record(
        root,
        "coordinator",
        "dispatch",
        f"交给{ROLES.get(role, '全体角色')}：{content}",
        {"target": role},
        key=f"dispatch:{command_id}",
    )


def queue_directive(
    root: Path, role: str, content: str, command_id: str, node: str
) -> None:
    """把要求留到指定步骤成功完成后，当前步骤的重试不能提前读取。"""
    with database(root) as db:
        db.execute(
            "INSERT OR IGNORE INTO queued_directives(id,role,content,node) VALUES(?,?,?,?)",
            (command_id, role, content, node),
        )
    record(
        root,
        "coordinator",
        "queued",
        "已排队，当前步骤完成后应用：" + content,
        {"node": node},
        key="queued:" + command_id,
    )
    activate_directives(root, read_json(root / "workflow_state.json"))


def activate_directives(root: Path, state: dict) -> None:
    """在完成检查点时原子发布要求；幂等支持服务重启。"""
    completed = set(state.get("completed_nodes", []))
    released = []
    with database(root) as db:
        db.execute("BEGIN IMMEDIATE")
        for item in db.execute(
            "SELECT * FROM queued_directives WHERE released=0"
        ).fetchall():
            if item["node"] not in completed:
                continue
            db.execute(
                "INSERT OR IGNORE INTO directives(id,role,content,at) VALUES(?,?,?,?)",
                (item["id"], item["role"], item["content"], now()),
            )
            db.execute(
                "UPDATE queued_directives SET released=1 WHERE id=?", (item["id"],)
            )
            released.append(dict(item))
    for item in released:
        record(
            root,
            "coordinator",
            "dispatch",
            "排队要求已生效：" + item["content"],
            {"target": item["role"]},
            key="dispatch:" + item["id"],
        )


def read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def owner(node: str) -> str:
    if node.startswith(("write:", "finalize")):
        return "writer"
    if node.startswith(("solve:", "pilot")):
        return "coder"
    return "modeler" if node in {"modeler", "analysis"} else "coordinator"


def snapshot(root: Path) -> dict:
    """所有角色与前端读取同一张表，状态来自真实执行检查点。"""
    from app.core.workflow_checkpoint import WorkflowCheckpoint
    from app.core.project_audit import evaluated_node_status, evaluate_pilot

    state = read_json(root / "workflow_state.json")
    meta = read_json(root / ".project.json")
    status = state.get("status", meta.get("status", "preparing"))
    pending = state.get("pending_approval")
    completed = state.get("completed_nodes", [])
    steps = []
    for node in WorkflowCheckpoint.node_order(state):
        node_status = (
            evaluated_node_status(state, node) if node in completed else "pending"
        )
        if pending and node == pending.get("node_id"):
            node_status = "awaiting_approval"
        elif node == state.get("current_node"):
            node_status = status
        steps.append(
            {
                "id": node,
                "label": WorkflowCheckpoint.node_label(node, state),
                "role": owner(node),
                "status": node_status,
                "issues": (
                    evaluate_pilot(state)
                    if node == "pilot"
                    else (state.get("node_outcomes", {}).get(node) or {})
                ).get("issues", []),
            }
        )
    writing = read_json(root / "paper" / "workspace.json").get("generation", {})
    compilation = read_json(root / "paper" / "compile.json")
    if root.name in compiling_tasks:
        compilation = {**compilation, "status": "running"}
    inputs = read_json(root / "paper" / "input.json")
    from app.services.call_ledger import summary as call_summary

    resolved_root = root.resolve()
    usage = call_summary(resolved_root)
    from app.services.work_timing import summary as work_summary

    timing = work_summary(resolved_root, state=state)
    failure = (
        read_json(root / ".runtime-failure.json")
        if status in {"failed", "stopped"}
        else None
    )
    if (
        status == "stopped"
        and failure
        and (
            failure.get("code") not in {"MODEL_STAGE_BUDGET", "EXECUTION_BUDGET"}
            or failure.get("run_id") != state.get("execution_id")
        )
    ):
        failure = None
    steps.extend(
        [
            {
                "id": "paper:generate",
                "label": writing.get("section") or "论文手撰写初稿",
                "role": "writer",
                "status": ("ready" if inputs else "blocked")
                if writing.get("status", "idle") == "idle"
                else writing["status"],
            },
            {
                "id": "paper:compile",
                "label": "论文 PDF 编译"
                if writing.get("file")
                else "当前源码预览（尚未生成论文）",
                "role": "writer",
                "status": compilation.get("status", "pending"),
            },
        ]
    )
    with database(root) as db:
        commands = [
            dict(row)
            for row in db.execute(
                "SELECT id,status FROM commands ORDER BY rowid DESC LIMIT 30"
            )
        ]
        directives = [
            {**dict(row), "seen": json.loads(row["seen"])}
            for row in db.execute("SELECT * FROM directives ORDER BY at DESC LIMIT 30")
        ]
        latest = db.execute("SELECT COALESCE(MAX(seq),0) FROM events").fetchone()[0]
    return {
        "task_id": root.name,
        "task_purpose": (state.get("problem") or meta.get("problem") or {}).get(
            "task_purpose", "modeling"
        ),
        "failure": failure,
        "usage": usage,
        "timing": timing,
        "preflight": meta.get("preflight") if not state else None,
        "archived": meta.get("archived", False),
        "status": status,
        "current_node": state.get("current_node"),
        "updated_at": state.get("updated_at"),
        "title": str(
            meta.get("title")
            or (state.get("questions") or {}).get("title")
            or (state.get("problem") or {}).get("ques_all")
            or root.name
        )[:100],
        "steps": steps,
        "pending_approval": pending,
        "directives": directives,
        "writing": writing,
        "inputs": inputs,
        "compilation": compilation,
        "sequence": latest,
        "commands": commands,
        "results": [
            {
                "key": key,
                "summary": value.get("execution_summary", {}),
                "artifacts": value.get("artifacts", []),
            }
            for key, value in (state.get("solution_results") or {}).items()
        ],
    }


def _context_results(results: list[dict]) -> list[dict]:
    """Keep verdicts and evidence; table rows remain in their source files."""
    compact = []
    for result in results:
        summary = result["summary"]
        if not isinstance(summary, dict):
            compact.append(result)
            continue
        summary = dict(summary)
        if (
            "run_summary" in summary
            and summary.get("content") == summary["run_summary"]
        ):
            summary.pop("content", None)
        previews = summary.get("table_previews")
        if isinstance(previews, list):
            # Copy each preview: the full checkpoint and UI still need its rows.
            summary["table_previews"] = [
                {
                    **{key: value for key, value in preview.items() if key != "rows"},
                    "rows_omitted": len(preview["rows"]),
                }
                if isinstance(preview, dict) and isinstance(preview.get("rows"), list)
                else preview
                for preview in previews
            ]
        compact.append(
            {
                **result,
                "summary": summary,
                "summary_source": {
                    "path": "workflow_state.json",
                    "result_key": result["key"],
                    "field": "execution_summary",
                },
            }
        )
    return compact


def context_for(task_id: str, agent_name: str) -> str:
    """每次调用前刷新公共状态，并登记该角色已读取的指令。"""
    role = AGENTS.get(agent_name)
    if not task_id or role is None:
        return ""
    try:
        root = Path(get_work_dir(task_id))
    except (ValueError, FileNotFoundError):
        return ""
    activate_directives(root, read_json(root / "workflow_state.json"))
    state = snapshot(root)
    applicable = [item for item in state["directives"] if item["role"] in {role, "all"}]
    for item in applicable:
        if role not in item["seen"]:
            with database(root) as db:
                # 同一角色并行章节不得丢失其他角色的读取回执。
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT seen FROM directives WHERE id=?", (item["id"],)
                ).fetchone()
                seen = set(json.loads(row[0])) | {role}
                db.execute(
                    "UPDATE directives SET seen=? WHERE id=?",
                    (json.dumps(sorted(seen)), item["id"]),
                )
            record(
                root,
                role,
                "receipt",
                f"已读取协作要求：{item['content']}",
                key=f"receipt:{item['id']}:{role}",
            )
    attachments = input_filenames(root)
    brief = {
        "status": state["status"],
        "current_node": state["current_node"],
        "steps": state["steps"],
        "directives": [
            {"role": item["role"], "content": item["content"]}
            for item in reversed(state["directives"])
        ],
        "my_instructions": [item["content"] for item in reversed(applicable)],
        "results": _context_results(state["results"]),
        "attachment_files": sorted(attachments)[:200],
        "attachment_count": len(attachments),
        "attachment_manifest": ".remit-inputs.json",
    }
    return (
        "\n共享协作状态（执行事实；用户要求不得覆盖质量门禁或编造结果）：\n"
        # LLM.chat checks the complete request budget before contacting a provider.
        # A character slice here silently removed constraints and attachment refs.
        + json.dumps(brief, ensure_ascii=False, default=str, separators=(",", ":"))
    )


def checkpoint_event(root: Path, state: dict) -> None:
    """检查点改变时记录每个开始、完成、暂停和返修转移。"""
    activate_directives(root, state)
    data = {
        key: state.get(key)
        for key in (
            "status",
            "current_node",
            "completed_nodes",
            "node_outcomes",
            "pilot_skipped",
        )
    }
    pending = state.get("pending_approval") or {}
    data["checkpoint_id"] = pending.get("checkpoint_id")
    with database(root) as db:
        last = db.execute(
            "SELECT data FROM events WHERE kind='checkpoint' ORDER BY seq DESC LIMIT 1"
        ).fetchone()
    if last and json.loads(last[0]) == data:
        return
    from app.core.workflow_checkpoint import WorkflowCheckpoint

    node = state.get("current_node") or (state.get("completed_nodes") or [""])[-1]
    label = WorkflowCheckpoint.node_label(node, state) if node else "任务准备"
    phase = (
        "步骤完成"
        if not state.get("current_node") and state.get("completed_nodes")
        else "状态更新"
    )
    if phase == "步骤完成":
        from app.core.project_audit import evaluated_node_status

        outcome = evaluated_node_status(state, node)
        phase = {
            "skipped": "步骤已跳过，未验证",
            "warning": "步骤结束，仍需核验",
            "failed": "步骤失败",
        }.get(outcome, phase)
    record(root, owner(node), "checkpoint", f"{label} · {phase}", data)


def claim_command(root: Path, command_id: str, content: str) -> dict | None:
    with database(root) as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(
            "SELECT * FROM commands WHERE id=?", (command_id,)
        ).fetchone()
        if existing:
            if existing["content"] != content:
                raise ValueError("同一请求编号不能用于不同消息")
            return {"status": existing["status"], **json.loads(existing["result"])}
        db.execute(
            "INSERT INTO commands(id,content,status) VALUES(?,?,'running')",
            (command_id, content),
        )
    return None


def finish_command(root: Path, command_id: str, status: str, result: dict) -> None:
    with database(root) as db:
        db.execute(
            "UPDATE commands SET status=?,result=? WHERE id=?",
            (status, json.dumps(result, ensure_ascii=False), command_id),
        )
