"""为独立子流程提供任务局部的消息接收器，不修改共享全局发布器。"""

from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from app.schemas.response import Message

message_sink: ContextVar[Callable[[str, Message], Awaitable[None]] | None] = ContextVar(
    "message_sink", default=None
)
