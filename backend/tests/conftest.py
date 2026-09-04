"""单元测试隔离本机任务档案和 Redis，禁止污染正在使用的工作区。"""

import pytest

from app.services.message_archive import MessageArchive
from app.services.redis_manager import redis_manager
from app.routers import modeling_router


@pytest.fixture(autouse=True)
def isolated_message_archive(tmp_path, monkeypatch):
    """每个测试获得独立持久化位置，真实 Redis 集成使用自行创建的 manager。"""
    directory = tmp_path / "messages"
    monkeypatch.setattr(redis_manager, "messages_dir", directory)
    monkeypatch.setattr(redis_manager, "archive", MessageArchive(directory))
    monkeypatch.setattr(redis_manager, "redis_url", "redis://127.0.0.1:1/0")
    monkeypatch.setattr(redis_manager, "_client", None)
    monkeypatch.setattr(redis_manager, "_message_locks", {})
    monkeypatch.setattr(redis_manager, "_deleting_tasks", set())
    modeling_router._pending_cancellations.clear()
    modeling_router._scheduled_tasks.clear()
    modeling_router._active_tasks.clear()
    yield
    modeling_router._pending_cancellations.clear()
    modeling_router._scheduled_tasks.clear()
    modeling_router._active_tasks.clear()
