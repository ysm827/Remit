"""Context handling at the real assistant/tool request boundary; no model calls."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.core.agents.agent import Agent, _message_tokens, _rough_tokens


def response(content="ok", used=0, calls=None):
    return SimpleNamespace(
        content=content,
        reasoning_content=None,
        tool_calls=calls or [],
        usage=SimpleNamespace(prompt_tokens=used),
    )


class ContextBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_usage_plus_response_and_pending_tool_boundary(self):
        a = Agent("test", SimpleNamespace(chat=AsyncMock(return_value=response())))
        a.compress_if_needed = AsyncMock()
        call = SimpleNamespace(
            id="c1", name="execute_code", arguments='{"code":"disp(1)"}'
        )
        await a.append_assistant_response(response(used=95000, calls=[call]))
        self.assertEqual(
            a.current_token_count, 95000 + _message_tokens(a.chat_history[-1])
        )
        a.compress_if_needed.assert_not_awaited()
        await a.append_chat_history(
            {"role": "tool", "tool_call_id": "c1", "content": "result"}
        )
        await a._chat(history=a.chat_history)
        a.compress_if_needed.assert_awaited_once()
        self.assertFalse(a._pending_tools())

    async def test_large_tool_output_is_archived_without_losing_error_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Agent("test", None)
            a.work_dir = tmp
            text = "HEAD\n" + "数据" * 20000 + "\nACTUAL ERROR AT END"
            await a.append_chat_history(
                {"role": "tool", "content": text, "tool_call_id": "a"}
            )
            archived = list((Path(tmp) / ".agent-context").glob("*.txt"))
            self.assertEqual(len(archived), 1)
            self.assertEqual(archived[0].read_text(encoding="utf-8"), text)
            self.assertLess(len(a.chat_history[-1]["content"]), 17000)
            self.assertIn("ACTUAL ERROR AT END", a.chat_history[-1]["content"])

    async def test_compression_rebinds_history_and_preserves_contract_and_tool_pair(
        self,
    ):
        model = SimpleNamespace(
            chat=AsyncMock(side_effect=[response("保留真实结论"), response("done", 42)])
        )
        a = Agent("test", model, context_window=4000)
        a.chat_history = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "DATA FILE LIST"},
            {"role": "user", "content": "APPROVED CONSTRAINTS"},
            {"role": "assistant", "content": "old" * 2000},
            {"role": "user", "content": "DO NOT CHANGE SAMPLING"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "a", "function": {"arguments": '{"code":"compute()"}'}}
                ],
            },
            {"role": "tool", "tool_call_id": "a", "content": "ERROR TAIL"},
        ]
        a.current_token_count = 10000
        await a._chat(history=a.chat_history)
        actual = model.chat.call_args.kwargs["history"]
        self.assertIs(actual, a.chat_history)
        self.assertIn("APPROVED CONSTRAINTS", json.dumps(actual))
        self.assertIn("DO NOT CHANGE SAMPLING", json.dumps(actual))
        self.assertFalse(a._orphan_tool_exists(0))
        self.assertEqual(a.current_token_count, 42)

    async def test_summary_failure_retains_user_contract(self):
        a = Agent(
            "test", SimpleNamespace(chat=AsyncMock(side_effect=RuntimeError("offline")))
        )
        a.chat_history = [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "contract"},
        ]
        a.chat_history.extend(
            {"role": "assistant", "content": str(i)} for i in range(8)
        )
        a.current_token_count = 200000
        await a.compress_if_needed()
        self.assertIn("contract", json.dumps(a.chat_history))

    async def test_oversized_pinned_contract_blocks_request_instead_of_dropping_it(
        self,
    ):
        model = SimpleNamespace(chat=AsyncMock())
        a = Agent("test", model, context_window=100)
        a.chat_history = [{"role": "user", "content": "数据" * 100}]
        a._recount_tokens()
        with self.assertRaisesRegex(ValueError, "超出上下文预算"):
            await a._chat(history=a.chat_history)
        model.chat.assert_not_awaited()

    async def test_changed_model_window_blocks_oversized_preserved_contract(self):
        model = SimpleNamespace(chat=AsyncMock(return_value=response()))
        a = Agent("test", model, context_window=4000)
        a.chat_history = [{"role": "user", "content": "约束" * 100}]
        a._recount_tokens()
        await a._chat(history=a.chat_history, max_tokens=20)
        model.chat.reset_mock()
        model.context_window = 100
        with self.assertRaisesRegex(ValueError, "超出上下文预算"):
            await a._chat(history=a.chat_history, max_tokens=20)
        self.assertEqual(a.context_window, 100)
        self.assertEqual(a.chat_history[0]["content"], "约束" * 100)
        model.chat.assert_not_awaited()

    def test_chinese_estimate_and_summary_include_tool_arguments_and_tail(self):
        self.assertEqual(_rough_tokens("汉" * 300), 300)
        snippet = Agent._summary_excerpt(
            {"role": "assistant", "tool_calls": [{"function": {"arguments": "CODE"}}]}
        )
        self.assertIn("CODE", snippet)
        self.assertIn(
            "error-tail",
            Agent._summary_excerpt(
                {"role": "tool", "content": "x" * 3000 + "error-tail"}
            ),
        )
