"""SQLite 追加式消息档案：事务落盘、历史游标与旧 JSON 的无损迁移。"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from collections.abc import Iterator

from app.services.task_state import message_task_status, message_title
from app.utils.common_utils import ensure_safe_task_id
from app.utils.log_util import logger


class MessageArchive:
    """把阻塞存储操作集中到可由后台线程调用的持久化边界。"""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.path = directory / "messages.sqlite3"
        self._lock = RLock()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self.directory.mkdir(parents=True, exist_ok=True)
        with self._lock:
            connection = sqlite3.connect(self.path, timeout=10)
            try:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.executescript("""
                    CREATE TABLE IF NOT EXISTS task_events (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id TEXT NOT NULL,
                        payload TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS task_events_cursor
                        ON task_events(task_id, sequence);
                    CREATE TABLE IF NOT EXISTS task_index (
                        task_id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        title_priority INTEGER NOT NULL DEFAULT 0,
                        status TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        message_count INTEGER NOT NULL DEFAULT 0
                    );
                    CREATE TABLE IF NOT EXISTS legacy_imports (
                        task_id TEXT PRIMARY KEY
                    );
                """)
                with connection:
                    connection.execute("BEGIN IMMEDIATE")
                    yield connection
            finally:
                connection.close()

    @staticmethod
    def _append(connection: sqlite3.Connection, task_id: str, payload: dict) -> int:
        payload = dict(payload)
        payload.pop("sequence", None)
        status = message_task_status(payload)
        if status:
            payload["task_status"] = status
        cursor = connection.execute(
            "INSERT INTO task_events(task_id, payload) VALUES (?, ?)",
            (task_id, json.dumps(payload, ensure_ascii=False)),
        )
        title, priority = message_title(payload)
        connection.execute(
            """INSERT INTO task_index(task_id, title, title_priority, status, updated_at, message_count)
               VALUES (?, ?, ?, ?, ?, 1)
               ON CONFLICT(task_id) DO UPDATE SET
                 title = CASE WHEN excluded.title_priority > task_index.title_priority
                              THEN excluded.title ELSE task_index.title END,
                 title_priority = MAX(task_index.title_priority, excluded.title_priority),
                 status = COALESCE(?, task_index.status),
                 updated_at = excluded.updated_at,
                 message_count = task_index.message_count + 1""",
            (
                task_id,
                title or task_id,
                priority,
                status or "running",
                str(
                    payload.get("created_at") or datetime.now(timezone.utc).isoformat()
                ),
                status,
            ),
        )
        return int(cursor.lastrowid)

    def _migrate(self, connection: sqlite3.Connection, task_id: str) -> None:
        """同事务导入一次旧文件；保留原文件，删除任务后也不重新导入。"""
        if connection.execute(
            "SELECT 1 FROM legacy_imports WHERE task_id = ?", (task_id,)
        ).fetchone():
            return
        legacy = self.directory / f"{task_id}.json"
        if legacy.resolve().parent != self.directory.resolve():
            raise ValueError("消息档案越出存储目录")
        if legacy.is_file():
            payload = json.loads(legacy.read_text(encoding="utf-8-sig"))
            if not isinstance(payload, list) or not all(
                isinstance(item, dict) for item in payload
            ):
                raise ValueError(f"任务 {task_id} 的旧消息档案格式不正确")
            for message in payload:
                self._append(connection, task_id, message)
        connection.execute("INSERT INTO legacy_imports(task_id) VALUES (?)", (task_id,))

    def append(self, task_id: str, payload: dict) -> int:
        """原子追加一条事件并更新任务索引，返回持久化序号。"""
        safe_id = ensure_safe_task_id(task_id)
        with self._connection() as connection:
            self._migrate(connection, safe_id)
            return self._append(connection, safe_id, payload)

    def load(
        self, task_id: str, after: int = 0, limit: int | None = None
    ) -> list[dict]:
        """按游标顺序读取事件，分页时不扫描此前的完整历史。"""
        safe_id = ensure_safe_task_id(task_id)
        with self._connection() as connection:
            self._migrate(connection, safe_id)
            rows = connection.execute(
                "SELECT sequence, payload FROM task_events WHERE task_id = ? AND sequence > ? "
                "ORDER BY sequence LIMIT ?",
                (safe_id, max(0, after), limit if limit is not None else -1),
            ).fetchall()
        return [
            {**json.loads(payload), "sequence": sequence} for sequence, payload in rows
        ]

    def exists(self, task_id: str) -> bool:
        safe_id = ensure_safe_task_id(task_id)
        with self._connection() as connection:
            self._migrate(connection, safe_id)
            return (
                connection.execute(
                    "SELECT 1 FROM task_index WHERE task_id = ?", (safe_id,)
                ).fetchone()
                is not None
            )

    def summaries(self) -> list[dict]:
        """旧数据首次导入后，直接查询索引而无需解析所有任务历史。"""
        with self._connection() as connection:
            for legacy in self.directory.glob("*.json"):
                connection.execute("SAVEPOINT migrate_legacy")
                try:
                    self._migrate(connection, ensure_safe_task_id(legacy.stem))
                except (OSError, ValueError) as exc:
                    connection.execute("ROLLBACK TO migrate_legacy")
                    logger.warning(f"跳过无法导入的历史档案 {legacy.name}: {exc}")
                finally:
                    connection.execute("RELEASE migrate_legacy")
            rows = connection.execute(
                "SELECT task_id, title, updated_at, status, message_count FROM task_index "
                "ORDER BY updated_at DESC"
            ).fetchall()
        keys = ("task_id", "title", "updated_at", "status", "message_count")
        return [dict(zip(keys, row, strict=True)) for row in rows]

    def delete(self, task_id: str) -> bool:
        """删除事件与索引；导入标记保留以避免旧文件重新出现任务。"""
        safe_id = ensure_safe_task_id(task_id)
        with self._connection() as connection:
            # 删除不需要解析内容；损坏的旧档案也必须可以清理。
            connection.execute(
                "INSERT OR IGNORE INTO legacy_imports(task_id) VALUES (?)", (safe_id,)
            )
            removed = connection.execute(
                "DELETE FROM task_index WHERE task_id = ?", (safe_id,)
            ).rowcount
            connection.execute("DELETE FROM task_events WHERE task_id = ?", (safe_id,))
        return bool(removed) or (self.directory / f"{safe_id}.json").is_file()
