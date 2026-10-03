"""Coder tool policy reaches each provider without changing other callers."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.llm.providers.anthropic import AnthropicProvider
from app.core.llm.providers.openai_chat import OpenAIChatProvider
from app.core.llm.providers.openai_responses import OpenAIResponsesProvider
from app.core.llm.types import StandardResponse


class SerialToolRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_serial_policy_is_opt_in_and_only_sent_with_tools(self):
        tool = {
            "type": "function",
            "function": {
                "name": "execute_code",
                "description": "Execute one step",
                "parameters": {
                    "type": "object",
                    "properties": {"code": {"type": "string"}},
                },
            },
        }
        for provider_type, module in [
            (OpenAIChatProvider, "openai_chat"),
            (OpenAIResponsesProvider, "openai_responses"),
            (AnthropicProvider, "anthropic"),
        ]:
            for serial, tools in [(False, [tool]), (None, [tool]), (False, None)]:
                with self.subTest(
                    provider=module, serial=serial, has_tools=bool(tools)
                ):
                    client = MagicMock()
                    client.close = AsyncMock()
                    create = AsyncMock(return_value=MagicMock(stop_reason="end_turn"))
                    client.responses.create = create
                    client.chat.completions.create = create
                    client.messages.create = create
                    provider = provider_type()
                    if isinstance(provider, OpenAIResponsesProvider):
                        provider._use_non_streaming = True
                    constructor = (
                        "AsyncAnthropic" if module == "anthropic" else "AsyncOpenAI"
                    )
                    with (
                        patch(
                            f"app.core.llm.providers.{module}.{constructor}",
                            return_value=client,
                        ),
                        patch.object(
                            provider,
                            "_normalize",
                            return_value=StandardResponse(content="ok"),
                        ),
                    ):
                        await provider.call(
                            messages=[],
                            model="test",
                            api_key="test",
                            tools=tools,
                            tool_choice="auto",
                            parallel_tool_calls=serial,
                        )
                    payload = create.call_args.kwargs
                    if module == "anthropic":
                        value = payload.get("tool_choice", {}).get(
                            "disable_parallel_tool_use"
                        )
                        self.assertIs(
                            value, True if tools and serial is False else None
                        )
                    else:
                        self.assertIs(
                            payload.get("parallel_tool_calls"),
                            False if tools and serial is False else None,
                        )
