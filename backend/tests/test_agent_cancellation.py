"""取消必须等待模型请求和监听协程退出，不能留下后台付费调用。"""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.core.agents.agent import Agent


class AgentCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_event_and_outer_cancellation_wait_for_provider_cleanup(self):
        for cancel_outer in (False, True):
            with self.subTest(cancel_outer=cancel_outer):
                started = asyncio.Event()
                cleaned = asyncio.Event()
                cancel_event = asyncio.Event()

                async def provider_chat(**_kwargs):
                    started.set()
                    try:
                        await asyncio.Event().wait()
                    finally:
                        # 请求释放连接也可能需要异步清理，返回停止前必须等完。
                        await asyncio.sleep(0)
                        cleaned.set()

                model = SimpleNamespace(chat=provider_chat)
                agent = Agent("cancel-probe", model, cancel_event=cancel_event)
                tasks_before = asyncio.all_tasks()
                outer = asyncio.create_task(agent._chat(history=[]))
                await started.wait()
                cancel_event.set()
                if cancel_outer:
                    outer.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await outer
                self.assertTrue(cleaned.is_set())
                self.assertEqual(asyncio.all_tasks(), tasks_before)

    async def test_timeout_cancels_provider_and_listener(self):
        cleaned = asyncio.Event()

        async def provider_chat(**_kwargs):
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

        agent = Agent(
            "timeout-probe",
            SimpleNamespace(chat=provider_chat),
            cancel_event=asyncio.Event(),
        )
        tasks_before = asyncio.all_tasks()
        with self.assertRaises(TimeoutError):
            await asyncio.wait_for(agent._chat(history=[]), timeout=0.01)
        self.assertTrue(cleaned.is_set())
        self.assertEqual(asyncio.all_tasks(), tasks_before)

    async def test_repeated_cancellation_does_not_interrupt_provider_cleanup(self):
        started = asyncio.Event()
        cleaning = asyncio.Event()
        release_cleanup = asyncio.Event()
        cleaned = asyncio.Event()

        async def provider_chat(**_kwargs):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaning.set()
                await release_cleanup.wait()
                cleaned.set()

        agent = Agent(
            "repeated-stop",
            SimpleNamespace(chat=provider_chat),
            cancel_event=asyncio.Event(),
        )
        task = asyncio.create_task(agent._chat(history=[]))
        await started.wait()
        task.cancel()
        await cleaning.wait()
        task.cancel()
        await asyncio.sleep(0)
        try:
            self.assertFalse(task.done())
        finally:
            release_cleanup.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(cleaned.is_set())

    async def test_completed_and_failed_requests_leave_no_listener(self):
        for error in (None, RuntimeError("provider offline")):
            with self.subTest(error=error):
                chat = AsyncMock(return_value="response", side_effect=error)
                agent = Agent(
                    "finished-probe",
                    SimpleNamespace(chat=chat),
                    cancel_event=asyncio.Event(),
                )
                tasks_before = asyncio.all_tasks()
                if error:
                    with self.assertRaisesRegex(RuntimeError, "provider offline"):
                        await agent._chat(history=[])
                else:
                    self.assertEqual(await agent._chat(history=[]), "response")
                self.assertEqual(asyncio.all_tasks(), tasks_before)

    async def test_already_cancelled_agent_does_not_start_a_request(self):
        cancel_event = asyncio.Event()
        cancel_event.set()
        chat = AsyncMock()
        agent = Agent(
            "already-stopped", SimpleNamespace(chat=chat), cancel_event=cancel_event
        )
        with self.assertRaises(asyncio.CancelledError):
            await agent._chat(history=[])
        chat.assert_not_called()
