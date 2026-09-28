"""取消安全的阻塞 I/O 边界。"""

import asyncio
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


async def run_blocking(function: Callable[..., T], *args) -> T:
    """等待工作线程结束后才传播取消，避免线程仍使用已关闭资源。"""
    worker = asyncio.create_task(asyncio.to_thread(function, *args))
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(worker)
            break
        except asyncio.CancelledError:
            cancelled = True
            if worker.cancelled():
                raise
            # 重复取消同样不能取消线程对应的 Task 或提前释放外层锁。
        except Exception as exc:
            if cancelled:
                raise asyncio.CancelledError from exc
            raise
    if cancelled:
        raise asyncio.CancelledError
    return result
