"""Role-specific probes must match runtime configuration and preserve unknowns."""

import asyncio
import base64
import hashlib
import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image, ImageColor

from app.core.llm.types import StandardResponse, Usage
from app.services import api_probe, model_capabilities as profiles

CONFIG = {
    "api_type": "openai-chat",
    "api_key": "private-canary",
    "base_url": "https://private.invalid",
    "model_id": "fixture",
}


def test_vision_challenge_answer_exists_only_in_pixels():
    content, expected, digest = api_probe.vision_challenge()
    assert expected["code"] not in content[0]["text"]
    raw = base64.b64decode(content[1]["image_url"]["url"].split(",", 1)[1])
    assert hashlib.sha256(raw).hexdigest() == digest
    with Image.open(io.BytesIO(raw)) as picture:
        assert len(set(expected["colors"])) == 6
        for index, color in enumerate(expected["colors"]):
            assert picture.getpixel((index * 100 + 50, 180)) == ImageColor.getrgb(color)


@pytest.mark.parametrize(
    "outcome", ["correct", "wrong", "limited", "unsupported", "truncated"]
)
def test_vision_result_and_transient_failure_are_distinct(monkeypatch, outcome):
    content, answer, digest = api_probe.vision_challenge()
    monkeypatch.setattr(
        api_probe, "vision_challenge", lambda: (content, answer, digest)
    )

    async def call(**kwargs):
        assert kwargs["max_tokens"] == 8192
        if isinstance(kwargs["messages"][0]["content"], str):
            return StandardResponse(
                content='```json\n{"ready":true}\n```', usage=Usage(10, 5, True)
            )
        assert kwargs["messages"][0]["content"] == content
        if outcome == "limited":
            raise RuntimeError("429 private-canary https://private.invalid")
        if outcome == "unsupported":
            raise RuntimeError("400 model does not support image input private-canary")
        return StandardResponse(
            content=json.dumps(answer if outcome == "correct" else {}),
            finish_reason="length" if outcome == "truncated" else "stop",
            usage=Usage(100, 20, True),
        )

    provider = SimpleNamespace(call=AsyncMock(side_effect=call))
    monkeypatch.setattr(api_probe, "provider_for", lambda _: provider)
    result = asyncio.run(
        api_probe.check_capabilities(CONFIG, needs_tools=False, needs_vision=True)
    )
    assert (
        result["connection"]
        == result["text"]
        == result["structured_output"]
        == "supported"
    )
    expected = {
        "correct": "supported",
        "wrong": "unsupported",
        "limited": "unknown",
        "unsupported": "unsupported",
        "truncated": "unknown",
    }
    assert result["vision"] == expected[outcome]
    assert result["calls"] == 2 and len(result["attempts"]) == 2
    assert result["attempts"][0]["prompt_tokens"] == 10
    assert "private-canary" not in json.dumps(
        result
    ) and "private.invalid" not in json.dumps(result)
    if outcome in {"limited", "truncated"}:
        assert result["errors"]["vision"]["status"] == "verification_failed"


def test_vision_profile_uses_factory_fallback_and_expires(tmp_path, monkeypatch):
    from app.config.setting import settings
    from app.core.llm.llm_factory import LLMFactory

    for field, value in {
        "API_TYPE": "openai-chat",
        "API_KEY": "fixture",
        "MODEL": "coordinator-fixture",
        "BASE_URL": "https://fixture.invalid",
    }.items():
        monkeypatch.setattr(settings, f"COORDINATOR_{field}", value)
        monkeypatch.setattr(settings, f"VISION_{field}", None)
    monkeypatch.setattr(profiles, "USER_CONFIG_PATH", tmp_path / ".env.user")
    config = profiles.role_config("vision")
    result = {
        "schema_version": 2,
        "fingerprint": api_probe.capability_fingerprint(config),
        "vision": "supported",
    }
    profiles.profile_path("vision").write_text(json.dumps(result), encoding="utf-8")
    model = LLMFactory("fixture").get_vision_llm()
    assert (
        model.model == config["model_id"] and model.max_tokens == config["max_tokens"]
    )
    assert model.capabilities["vision"] == "supported"
    monkeypatch.setattr(settings, "COORDINATOR_MODEL", "changed")
    assert profiles.load_profile("vision")["vision"] == "unknown"
    profiles.profile_path("vision").write_text("[]", encoding="utf-8")
    assert profiles.load_profile("vision")["vision"] == "unknown"


def test_roles_only_require_capabilities_used_by_their_workflow():
    assert profiles.requirements("coder")["parallel_tool_calls"] is False
    assert (
        profiles.requirements("writer")["structured_mode"]
        == "json_text_and_tool_arguments"
    )
    for role in ("coordinator", "modeler", "model_scout", "model_critic"):
        requirement = profiles.requirements(role)
        assert requirement["max_calls"] == 1 and not requirement["needs_vision"]
    assert profiles.requirements("vision")["max_calls"] == 2


def test_vision_rejection_only_blocks_image_requests(monkeypatch):
    from app.core.llm.llm import LLM
    from app.core.llm.errors import NonRetryableLLMError

    model = LLM(api_key="fixture", model="fixture", task_id="")
    model.capabilities = {"vision": "unsupported"}
    model.provider.call = AsyncMock(return_value=StandardResponse(content="text works"))
    content, _, _ = api_probe.vision_challenge()
    with pytest.raises(NonRetryableLLMError, match="识图"):
        asyncio.run(
            model.chat(history=[{"role": "user", "content": content}], publish=False)
        )
    model.provider.call.assert_not_awaited()
    assert (
        asyncio.run(
            model.chat(history=[{"role": "user", "content": "hello"}], publish=False)
        ).content
        == "text works"
    )


def test_same_role_duplicate_probe_is_rejected_and_lock_released(tmp_path, monkeypatch):
    import httpx
    from fastapi import FastAPI
    from app.routers import common_router as router

    monkeypatch.setattr(profiles, "role_config", lambda role: CONFIG)
    monkeypatch.setattr(profiles, "USER_CONFIG_PATH", tmp_path / ".env.user")
    router._capability_locks.clear()

    async def exercise():
        entered, release = asyncio.Event(), asyncio.Event()

        async def probe(config, **kwargs):
            assert kwargs["needs_vision"] and not kwargs["needs_tools"]
            entered.set()
            await release.wait()
            return {"vision": "supported"}

        monkeypatch.setattr(api_probe, "check_capabilities", probe)
        app = FastAPI()
        app.include_router(router.router)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            first = asyncio.create_task(
                client.post(
                    "/api/model-capabilities",
                    json={"role": "vision", "authorized": True},
                )
            )
            await asyncio.wait_for(entered.wait(), 2)
            try:
                second = await client.post(
                    "/api/model-capabilities",
                    json={"role": "vision", "authorized": True},
                )
                assert second.status_code == 409
            finally:
                release.set()
            assert (await first).status_code == 200
            assert not router._capability_locks["vision"].locked()

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "json_reply, expected",
    [('{"ready":true}', "supported"), ("plain prose", "unsupported")],
)
def test_writer_checks_both_json_text_and_tool_arguments(
    monkeypatch, json_reply, expected
):
    from app.core.llm.types import ToolCall

    calls = 0

    async def call(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return StandardResponse(content=json_reply)
        if calls == 2:
            assert kwargs["tool_choice"] == "auto"
            return StandardResponse(
                tool_calls=[ToolCall("call1", "remit_probe", '{"value":7}')]
            )
        return StandardResponse(content=kwargs["messages"][-1]["content"])

    monkeypatch.setattr(
        api_probe,
        "provider_for",
        lambda _: SimpleNamespace(call=AsyncMock(side_effect=call)),
    )
    result = asyncio.run(
        api_probe.check_capabilities(
            CONFIG, needs_tools=True, structured_mode="json_text_and_tool_arguments"
        )
    )
    assert result["structured_checks"]["tool_arguments"] == "supported"
    assert result["structured_checks"]["json_text"] == expected
    assert (
        result["structured_output"] == expected and result["tool_result"] == "supported"
    )
