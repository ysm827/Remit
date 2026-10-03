"""取消安全的阻塞 I/O 边界。"""

import asyncio
from contextvars import ContextVar
from threading import Event
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")
blocking_cancel: ContextVar[Event | None] = ContextVar("blocking_cancel", default=None)


class WorkCancelled(RuntimeError):
    """工作线程已响应取消，并完成自己的资源清理。"""


def check_cancelled() -> None:
    signal = blocking_cancel.get()
    if signal is not None and signal.is_set():
        raise WorkCancelled("操作已停止")


async def run_cancellable(
    function: Callable[..., T], *args, cancel_event: Event | None = None
) -> T:
    """通知协作线程停止；真正退出后才传播取消或释放外层锁。"""
    signal = cancel_event if cancel_event is not None else Event()
    token = blocking_cancel.set(signal)
    try:
        worker = asyncio.create_task(asyncio.to_thread(function, *args))
    finally:
        blocking_cancel.reset(token)
    return await _wait_worker(worker, signal)


async def run_blocking(function: Callable[..., T], *args) -> T:
    """等待工作线程结束后才传播取消，避免线程仍使用已关闭资源。"""
    worker = asyncio.create_task(asyncio.to_thread(function, *args))
    return await _wait_worker(worker)


async def _wait_worker(worker: asyncio.Task[T], signal: Event | None = None) -> T:
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(worker)
            break
        except asyncio.CancelledError:
            cancelled = True
            if signal is not None:
                signal.set()
            if worker.cancelled():
                raise
        except Exception as exc:
            if cancelled and (signal is None or isinstance(exc, WorkCancelled)):
                raise asyncio.CancelledError from exc
            raise
    if cancelled:
        raise asyncio.CancelledError
    return result
