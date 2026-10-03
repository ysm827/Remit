"""Fallback checks use the target model's profile and limits, before paid calls."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config.setting import settings
from app.core.llm.errors import NonRetryableLLMError
from app.core.llm.llm import LLM
from app.core.llm.types import StandardResponse
from app.services import model_capabilities as profiles


@pytest.fixture
def fallback(monkeypatch):
    for key, value in {
        "FALLBACK_ENABLED": True,
        "FALLBACK_MODEL": "alternate",
        "FALLBACK_API_KEY": "fixture",
        "FALLBACK_API_TYPE": "openai-chat",
        "FALLBACK_BASE_URL": "https://fixture.invalid/v1",
        "FALLBACK_CONTEXT_WINDOW": 4000,
        "FALLBACK_MAX_TOKENS": 1000,
        "LLM_HARD_RETRY_LIMIT": 1,
    }.items():
        monkeypatch.setattr(settings, key, value)
    model = LLM(
        api_key="fixture",
        model="primary",
        api_type="openai-chat",
        base_url="https://fixture.invalid/v1",
        max_tokens=3000,
    )
    model.capability_role = "coder"
    model.capabilities = {
        key: "supported"
        for key in (
            "connection",
            "text",
            "structured_output",
            "tools",
            "tool_result",
            "vision",
        )
    }
    model.provider.call = AsyncMock(side_effect=RuntimeError("temporary"))
    provider = SimpleNamespace(
        call=AsyncMock(return_value=StandardResponse(content="ok"))
    )
    monkeypatch.setattr("app.core.llm.llm._resolve_provider", lambda _: provider)
    profile = dict(model.capabilities)
    monkeypatch.setattr(profiles, "load_profile", lambda *_, **__: dict(profile))
    monkeypatch.setattr(
        profiles,
        "fallback_config",
        lambda *_, **__: {
            "api_type": "openai-chat",
            "api_key": "fixture",
            "model_id": "alternate",
            "base_url": settings.FALLBACK_BASE_URL,
            "context_window": settings.FALLBACK_CONTEXT_WINDOW,
            "max_tokens": settings.FALLBACK_MAX_TOKENS,
            "reasoning_effort": None,
        },
    )
    return model, provider, profile


@pytest.mark.parametrize("verdict", ["unknown", "unsupported"])
def test_unverified_fallback_tools_never_receive_request(fallback, verdict):
    model, provider, profile = fallback
    profile["tools"] = verdict
    with pytest.raises(NonRetryableLLMError, match="备用模型"):
        asyncio.run(
            model.chat(
                tools=[{"name": "execute_code"}],
                max_tokens=100,
                max_retries=1,
                publish=False,
            )
        )
    provider.call.assert_not_awaited()
    assert model.model == "primary"


def test_fallback_rechecks_budget_before_switch(fallback, monkeypatch):
    model, provider, _ = fallback
    monkeypatch.setattr(settings, "FALLBACK_CONTEXT_WINDOW", 500)
    with pytest.raises(NonRetryableLLMError, match="上下文预算"):
        asyncio.run(
            model.chat(
                history=[{"role": "user", "content": "约束" * 500}],
                max_tokens=100,
                max_retries=1,
                publish=False,
            )
        )
    provider.call.assert_not_awaited()
    assert model.model == "primary"


def test_validated_fallback_uses_own_profile_and_output_limit(fallback):
    model, provider, profile = fallback
    profile["vision"] = "unknown"
    assert asyncio.run(model.chat(max_retries=1, publish=False)).content == "ok"
    assert model.model == "alternate" and model.context_window == 4000
    assert model.capabilities["vision"] == "unknown"
    assert provider.call.call_args.kwargs["max_tokens"] == 1000
    with pytest.raises(NonRetryableLLMError, match="备用模型"):
        asyncio.run(
            model.chat(
                history=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": "data:image/png;base64,AA=="},
                            }
                        ],
                    }
                ],
                publish=False,
            )
        )
    assert provider.call.await_count == 1


def test_explicit_output_request_is_not_silently_shortened(fallback):
    model, provider, _ = fallback
    with pytest.raises(NonRetryableLLMError, match="输出上限"):
        asyncio.run(model.chat(max_tokens=1500, max_retries=1, publish=False))
    provider.call.assert_not_awaited()


def test_disabled_fallback_keeps_primary_failure(fallback, monkeypatch):
    model, provider, _ = fallback
    monkeypatch.setattr(settings, "FALLBACK_ENABLED", False)
    with pytest.raises(RuntimeError, match="temporary"):
        asyncio.run(model.chat(max_retries=1, publish=False))
    provider.call.assert_not_awaited()


@pytest.mark.parametrize("role", ["coder", "vision"])
def test_probe_saves_separate_role_profile_and_config_change_expires_it(
    tmp_path, monkeypatch, role
):
    from app.routers import common_router
    from app.services import api_probe

    monkeypatch.setattr(profiles, "USER_CONFIG_PATH", tmp_path / ".env.user")
    monkeypatch.setattr(settings, "FALLBACK_API_KEY", "fallback-secret")
    monkeypatch.setattr(settings, "FALLBACK_MODEL", "fallback-model")
    config = profiles.fallback_config(role)
    primary = profiles.profile_path(role)
    primary.write_text('{"primary":true}', encoding="utf-8")
    profile = {
        "schema_version": 2,
        "fingerprint": api_probe.capability_fingerprint(config),
        "text": "supported",
    }
    probe = AsyncMock(return_value=profile)
    monkeypatch.setattr(api_probe, "check_capabilities", probe)
    asyncio.run(
        common_router.check_model_capabilities(
            common_router.CapabilityCheckRequest(
                role=role, fallback=True, authorized=True
            )
        )
    )
    assert probe.call_args.args[0] == config
    assert probe.call_args.kwargs["needs_tools"] == (role == "coder")
    assert probe.call_args.kwargs["needs_vision"] == (role == "vision")
    assert primary.read_text() == '{"primary":true}'
    assert profiles.load_profile(role, fallback=True)["text"] == "supported"
    monkeypatch.setattr(
        settings, "FALLBACK_CONTEXT_WINDOW", config["context_window"] + 1
    )
    assert profiles.load_profile(role, fallback=True)["text"] == "unknown"
    assert (
        profiles.load_profile(role, fallback=True, effective_config=config)["text"]
        == "supported"
    )


def test_image_request_uses_separately_verified_same_config_vision(
    fallback, monkeypatch
):
    model, provider, profile = fallback
    profile["vision"] = "unknown"
    monkeypatch.setattr(settings, "FALLBACK_CONTEXT_WINDOW", 12000)

    def load(role, **kwargs):
        assert (
            kwargs["fallback"] and kwargs["effective_config"]["model_id"] == "alternate"
        )
        return {"vision": "supported"} if role == "vision" else dict(profile)

    monkeypatch.setattr(profiles, "load_profile", load)
    history = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,AA=="},
                }
            ],
        }
    ]
    assert (
        asyncio.run(
            model.chat(history=history, max_tokens=100, max_retries=1, publish=False)
        ).content
        == "ok"
    )
    assert provider.call.await_count == 1
    assert model.capabilities["vision"] == "supported"


def test_saved_fallback_survives_restart_and_can_be_disabled(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.config.setting import Settings
    from app.routers import modeling_router
    from app.schemas.api_config import SaveConfigurationRequest

    monkeypatch.setattr(modeling_router, "_USER_CONFIG_PATH", tmp_path / ".env.user")
    monkeypatch.setattr(modeling_router, "_runtime_configured_agents", set())
    before = settings.model_dump()
    app = FastAPI()
    app.include_router(modeling_router.router)
    client = TestClient(app)
    try:
        request = SaveConfigurationRequest(
            coordinator={},
            modeler={},
            coder={},
            writer={},
            openalex_email="",
            fallback_enabled=True,
            fallback={
                "apiKey": "fallback-secret",
                "modelId": "alternate",
                "apiType": "openai-chat",
                "baseUrl": "https://fixture.invalid/v1",
                "contextWindow": 32000,
                "maxTokens": 1000,
            },
        )
        assert (
            client.post("/save-api-config", json=request.model_dump()).status_code
            == 200
        )
        reloaded = Settings(_env_file=tmp_path / ".env.user")
        assert reloaded.FALLBACK_MODEL == "alternate"
        assert reloaded.FALLBACK_CONTEXT_WINDOW == 32000
        assert reloaded.FALLBACK_MAX_TOKENS == 1000
        assert reloaded.FALLBACK_ENABLED
        status = client.get("/api-config-status").json()
        assert status["agents"]["fallback"]["max_tokens"] == 1000
        assert status["fallback_enabled"] and status["agents"]["fallback"]["configured"]
        assert "fallback-secret" not in json.dumps(status)
        request.fallback_enabled = False
        assert (
            client.post("/save-api-config", json=request.model_dump()).status_code
            == 200
        )
        assert not Settings(_env_file=tmp_path / ".env.user").FALLBACK_ENABLED
    finally:
        client.close()
        for key, value in before.items():
            setattr(settings, key, value)
