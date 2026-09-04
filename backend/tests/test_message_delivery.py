"""WebSocket 历史重放和真实 Redis 广播/故障补偿行为测试。"""

import asyncio
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from starlette.websockets import WebSocketState

from app.routers import ws_router
from app.schemas.response import ApprovalMessage, SystemMessage, UserMessage
from app.services.redis_manager import RedisManager
from app.services.ws_manager import WebSocketManager


@pytest.fixture
def isolated_redis(tmp_path):
    bundled = Path(__file__).resolve().parents[2] / "tools/redis/redis-server.exe"
    executable = (
        str(bundled) if sys.platform == "win32" else shutil.which("redis-server")
    )
    if not executable or not Path(executable).is_file():
        pytest.skip("当前环境未安装 Redis 测试运行文件")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    process = subprocess.Popen(
        [
            executable,
            "--bind",
            "127.0.0.1",
            "--port",
            str(port),
            "--save",
            "",
            "--appendonly",
            "no",
        ],
        cwd=tmp_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail("隔离 Redis 启动失败")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            pytest.fail("隔离 Redis 启动超时")
        yield f"redis://127.0.0.1:{port}/0"
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)


class SocketProbe:
    def __init__(self, after=0):
        self.query_params = {"after": str(after)}
        self.client_state = WebSocketState.CONNECTED
        self.application_state = WebSocketState.CONNECTED
        self.messages = asyncio.Queue()
        self.disconnected = asyncio.Event()

    async def accept(self):
        pass

    async def send_json(self, payload):
        await self.messages.put(payload)

    async def receive(self):
        await self.disconnected.wait()
        return {"type": "websocket.disconnect", "code": 1000}


def test_real_redis_replay_live_delivery_and_missing_broadcast(
    isolated_redis, tmp_path, monkeypatch
):
    async def scenario():
        manager = RedisManager(tmp_path / "history")
        manager.redis_url = isolated_redis
        monkeypatch.setattr(ws_router, "redis_manager", manager)
        sockets = WebSocketManager()
        monkeypatch.setattr(ws_router, "ws_manager", sockets)
        first = UserMessage(content="synthetic task")
        await manager.publish_message("task", first)
        approval = ApprovalMessage(checkpoint_id="approval-1", node_id="analysis")
        await manager.publish_message("task", approval)
        ws = SocketProbe(after=first.sequence)
        endpoint = asyncio.create_task(ws_router.websocket_endpoint(ws, "task"))
        try:
            replay = await asyncio.wait_for(ws.messages.get(), 3)
            assert replay["id"] == approval.id
            assert replay["task_status"] == "awaiting_approval"
            running = SystemMessage(content="new wording", task_status="running")
            await manager.publish_message("task", running)
            live = await asyncio.wait_for(ws.messages.get(), 3)
            assert live["id"] == running.id
            assert live["sequence"] > replay["sequence"]
            # 模拟已落盘但广播丢失：活动连接应从持久化补偿恢复终态。
            finished = SystemMessage(
                content="different wording", task_status="completed"
            )
            await manager._save_message_to_file("task", finished)
            recovered = await asyncio.wait_for(ws.messages.get(), 3)
            assert recovered["id"] == finished.id
            assert recovered["task_status"] == "completed"
            assert ws.messages.empty()
        finally:
            ws.disconnected.set()
            await asyncio.wait_for(endpoint, 3)
            assert sockets.active_connections == []
            await manager.close()

    asyncio.run(scenario())


def test_subscription_failure_still_replays_durable_approval(tmp_path, monkeypatch):
    async def scenario():
        manager = RedisManager(tmp_path / "offline")
        manager.redis_url = "redis://127.0.0.1:1/0"
        await manager._save_message_to_file(
            "task", ApprovalMessage(checkpoint_id="offline")
        )
        monkeypatch.setattr(ws_router, "redis_manager", manager)
        sockets = WebSocketManager()
        monkeypatch.setattr(ws_router, "ws_manager", sockets)
        ws = SocketProbe()
        endpoint = asyncio.create_task(ws_router.websocket_endpoint(ws, "task"))
        try:
            payload = await asyncio.wait_for(ws.messages.get(), 3)
            assert payload["checkpoint_id"] == "offline"
        finally:
            ws.disconnected.set()
            await asyncio.wait_for(endpoint, 3)
            assert not sockets.active_connections
            await manager.close()

    asyncio.run(scenario())
