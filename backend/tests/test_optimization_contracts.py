"""优化任务的真实边界回归，所有供应商调用均为协议仿真。"""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.llm.errors import NonRetryableLLMError
from app.core.llm.llm import LLM
from app.core.llm.types import StandardResponse, ToolCall, Usage
from app.services import api_probe, call_ledger, runtime_diagnostics


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setattr("app.services.team_state.context_for", lambda *_: "")
    monkeypatch.setattr("app.services.competitions.context_for", lambda *_: "")
    value = LLM(api_key="fixture-key", model="fixture-model")
    value.provider.call = AsyncMock(return_value=StandardResponse(content="ok"))
    return value


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_deterministic_provider_failure_is_not_retried(model, status):
    error = RuntimeError("rejected")
    error.status_code = status
    model.provider.call.side_effect = error
    with pytest.raises(RuntimeError):
        asyncio.run(
            model.chat(history=[{"role": "user", "content": "test"}], publish=False)
        )
    assert model.provider.call.await_count == 1


def test_final_shared_context_and_tools_count_before_request(model, monkeypatch):
    monkeypatch.setattr("app.services.team_state.context_for", lambda *_: "公" * 300)
    model.context_window = 500
    history = [{"role": "user", "content": "fixed"}]
    with pytest.raises(NonRetryableLLMError, match="最终请求超出"):
        asyncio.run(
            model.chat(
                history=history,
                tools=[{"description": "工" * 200}],
                max_tokens=100,
                publish=False,
            )
        )
    model.provider.call.assert_not_awaited()
    assert history == [{"role": "user", "content": "fixed"}]


def test_stream_progress_failure_never_repeats_paid_request(model, monkeypatch):
    model.task_id = "fixture"
    monkeypatch.setattr(
        "app.core.llm.llm.publish_activity",
        AsyncMock(side_effect=OSError("bus offline")),
    )
    monkeypatch.setattr(
        model, "send_message", AsyncMock(side_effect=OSError("bus offline"))
    )
    monkeypatch.setattr(call_ledger, "record", lambda *_: None)

    async def provider(**kwargs):
        await kwargs["on_delta"]("answer")
        return StandardResponse(content="answer")

    model.provider.call.side_effect = provider
    assert asyncio.run(model.chat()).content == "answer"
    assert model.provider.call.await_count == 1


def test_cancel_interrupts_retry_backoff(model):
    import httpx

    async def run():
        entered = asyncio.Event()

        async def failed(**kwargs):
            entered.set()
            raise httpx.ConnectError("temporary")

        model.provider.call.side_effect = failed
        task = asyncio.create_task(model.chat(publish=False))
        await asyncio.wait_for(entered.wait(), 2)
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert model.provider.call.await_count == 1


def test_capability_probe_checks_real_tool_return(monkeypatch):
    count = 0

    async def call(**kwargs):
        nonlocal count
        count += 1
        if count == 1:
            return StandardResponse(content='{"ready": true}')
        if count == 2:
            return StandardResponse(
                tool_calls=[ToolCall("c1", "remit_probe", '{"value":7}')]
            )
        return StandardResponse(content=kwargs["messages"][-1]["content"])

    provider = type("Provider", (), {})()
    provider.call = AsyncMock(side_effect=call)
    monkeypatch.setattr(api_probe, "provider_for", lambda *_: provider)
    config = {
        "api_type": "openai-chat",
        "api_key": "fixture",
        "base_url": None,
        "model_id": "fixture",
    }
    profile = asyncio.run(api_probe.check_capabilities(config, needs_tools=True))
    assert (
        profile["tools"]
        == profile["tool_result"]
        == profile["structured_output"]
        == "supported"
    )
    assert profile["calls"] == 3 and profile["vision"] == "unknown"
    assert "api_key" not in json.dumps(profile)


def test_capability_rate_limit_is_unknown_and_redacted(monkeypatch):
    error = RuntimeError("429 secret-canary https://private.invalid/key")
    provider = type("Provider", (), {})()
    provider.call = AsyncMock(side_effect=error)
    monkeypatch.setattr(api_probe, "provider_for", lambda *_: provider)
    profile = asyncio.run(
        api_probe.check_capabilities(
            {
                "api_type": "openai-chat",
                "api_key": "fixture",
                "base_url": None,
                "model_id": "fixture",
            },
            needs_tools=True,
        )
    )
    assert profile["tools"] == "unknown"
    assert profile["calls"] == 1
    assert "secret-canary" not in json.dumps(profile)


def test_text_probe_rejects_empty_reply(monkeypatch):
    provider = type("Provider", (), {})()
    provider.call = AsyncMock(return_value=StandardResponse(content=""))
    monkeypatch.setattr(api_probe, "provider_for", lambda *_: provider)
    valid, _ = asyncio.run(
        api_probe.check_model_connection(
            api_type="openai-chat",
            api_key="fixture",
            model_id="fixture",
            base_url="",
            timeout=1,
        )
    )
    assert not valid


def test_call_ledger_unknown_usage_is_null_and_idempotent(tmp_path, monkeypatch, model):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "project/work_dir/fixture"
    root.mkdir(parents=True)
    model.task_id = "fixture"
    asyncio.run(model.chat(publish=False))
    first = call_ledger.summary(root)
    assert (
        first["attempts"] == 1
        and first["prompt_tokens"] is None
        and first["cost"] is None
    )
    model.provider.call.return_value = StandardResponse(
        content="ok", usage=Usage(12, 5, True)
    )
    asyncio.run(model.chat(publish=False))
    result = call_ledger.summary(root)
    assert (
        result["attempts"] == 2
        and result["prompt_tokens"] == 12
        and not result["usage_complete"]
    )


def test_diagnostics_allowlist_excludes_user_content(tmp_path):
    (tmp_path / "workflow_state.json").write_text(
        json.dumps(
            {
                "status": "failed",
                "problem": {"ques_all": "secret-canary"},
                "error": "secret-canary",
                "completed_nodes": ["coordinator"],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "private-canary.csv").write_text("secret-canary")
    report = runtime_diagnostics.diagnostic_preview(tmp_path)
    serialized = json.dumps(report)
    assert "secret-canary" not in serialized and "private-canary" not in serialized
    assert "data_directory" not in serialized and "api_key" not in serialized
    assert report["task"]["completed_step_count"] == 1


def test_capability_endpoint_requires_explicit_authorization(monkeypatch):
    from app.routers import common_router

    probe = AsyncMock()
    monkeypatch.setattr(api_probe, "check_capabilities", probe)
    app = FastAPI()
    app.include_router(common_router.router)
    with TestClient(app) as client:
        assert (
            client.post("/api/model-capabilities", json={"role": "coder"}).status_code
            == 422
        )
    probe.assert_not_awaited()


def test_chapter_notes_conflict_preserves_saved_plan(tmp_path, monkeypatch):
    from app.routers import writing_router
    from app.services.writing_workspace import write_json

    monkeypatch.setattr(writing_router, "_root", lambda *_: tmp_path)
    write_json(
        tmp_path / "chapter-plan.json", {"evidence_revision": "e1", "notes": "keep"}
    )
    write_json(tmp_path / "input.json", {"revision": "e1"})
    app = FastAPI()
    app.include_router(writing_router.router)
    with TestClient(app) as client:
        original = client.get("/api/writing/fixture/chapter-plan").json()
        first = client.put(
            "/api/writing/fixture/chapter-plan",
            json={
                "version": original["version"],
                "evidence_revision": "e1",
                "notes": "accepted",
            },
        )
        assert first.status_code == 200
        assert (
            client.put(
                "/api/writing/fixture/chapter-plan",
                json={
                    "version": original["version"],
                    "evidence_revision": "e1",
                    "notes": "stale",
                },
            ).status_code
            == 409
        )
    assert (
        json.loads((tmp_path / "chapter-plan.json").read_text(encoding="utf-8"))[
            "notes"
        ]
        == "accepted"
    )


def test_template_does_not_depend_on_launch_directory(tmp_path, monkeypatch):
    from app.utils.common_utils import get_config_template

    monkeypatch.chdir(tmp_path)
    assert "firstPage" in get_config_template()


def test_stage_budget_survives_new_llm_instance(tmp_path, monkeypatch, model):
    from app.config.setting import settings

    monkeypatch.chdir(tmp_path)
    (tmp_path / "project/work_dir/fixture").mkdir(parents=True)
    monkeypatch.setattr(settings, "LLM_STAGE_CALL_LIMIT", 1)
    model.task_id = "fixture"
    asyncio.run(model.chat(publish=False))
    fresh = LLM(api_key="fixture", model="fixture", task_id="fixture")
    fresh.provider.call = AsyncMock(return_value=StandardResponse(content="unexpected"))
    with pytest.raises(NonRetryableLLMError, match="预算已用完"):
        asyncio.run(fresh.chat(publish=False))
    fresh.provider.call.assert_not_awaited()


def test_truncated_capability_does_not_mark_model_unsupported(monkeypatch):
    provider = type("Provider", (), {})()
    provider.call = AsyncMock(
        return_value=StandardResponse(content="{", finish_reason="length")
    )
    monkeypatch.setattr(api_probe, "provider_for", lambda *_: provider)
    profile = asyncio.run(
        api_probe.check_capabilities(
            {
                "api_type": "openai-chat",
                "api_key": "fixture",
                "base_url": None,
                "model_id": "fixture",
            },
            needs_tools=True,
        )
    )
    assert profile["structured_output"] == profile["tools"] == "unknown"
    assert profile["error"]["status"] == "verification_failed"


def test_unknown_diagnostic_task_returns_404(tmp_path, monkeypatch):
    from app.routers import common_router

    monkeypatch.chdir(tmp_path)
    app = FastAPI()
    app.include_router(common_router.router)
    with TestClient(app) as client:
        response = client.get("/api/diagnostics?task_id=missing")
    assert response.status_code == 404
    assert str(tmp_path) not in response.text


def test_packaged_migration_preserves_existing_and_original_data(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "remit_migration_test",
        Path(__file__).resolve().parents[2] / "tools/remit_prod_app.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    old, data = tmp_path / "old", tmp_path / "用户 data"
    (old / "project").mkdir(parents=True)
    (old / "project/answer.txt").write_text("original")
    (old / ".env.user").write_text("fixture-placeholder")
    monkeypatch.setattr(module, "BACKEND_DIR", old)
    monkeypatch.setattr(module, "DATA_DIR", data)
    module.prepare_user_data()
    assert (data / "project/answer.txt").read_text() == "original"
    (data / "project/answer.txt").write_text("new result")
    module.prepare_user_data()
    assert (data / "project/answer.txt").read_text() == "new result"
    assert (old / "project/answer.txt").read_text() == "original"


def test_shared_model_config_persists_without_returning_secret(tmp_path, monkeypatch):
    from app.routers import modeling_router
    from app.config.setting import Settings
    from app.schemas.api_config import SaveConfigurationRequest

    local = Settings(_env_file=None)
    monkeypatch.setattr(modeling_router, "settings", local)
    monkeypatch.setattr(modeling_router, "_runtime_configured_agents", set())
    config_path = tmp_path / ".env.user"
    monkeypatch.setattr(modeling_router, "_USER_CONFIG_PATH", config_path)
    request = SaveConfigurationRequest(
        coordinator={
            "apiKey": "shared-fixture-secret",
            "modelId": "shared-fixture",
            "apiType": "openai-chat",
            "baseUrl": "https://fixture.invalid/v1",
        },
        modeler={},
        coder={},
        writer={},
        openalex_email="",
        shared_core=True,
    )
    response = asyncio.run(modeling_router.store_api_configuration(request))
    assert response["success"]
    reloaded = Settings(_env_file=config_path)
    assert reloaded.MODEL_SHARED_CORE
    assert reloaded.CODER_API_KEY == reloaded.WRITER_API_KEY == "shared-fixture-secret"
    assert reloaded.MODELER_MODEL == "shared-fixture"
    public = asyncio.run(modeling_router.get_api_config_status()).model_dump_json()
    assert "shared-fixture-secret" not in public


def test_stage_time_budget_is_durable(tmp_path, monkeypatch, model):
    from app.config.setting import settings

    monkeypatch.chdir(tmp_path)
    root = tmp_path / "project/work_dir/fixture"
    root.mkdir(parents=True)
    monkeypatch.setattr(settings, "LLM_STAGE_API_SECONDS", 1.0)
    model.task_id = "fixture"

    async def slow(**_):
        await asyncio.sleep(0.005)
        return StandardResponse(content="ok")

    model.provider.call.side_effect = slow
    asyncio.run(model.chat(publish=False))
    # 将已经观测到的耗时持久化到超过预算，模拟下一进程读取同一账本。
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(root / ".calls.sqlite3")) as db:
        db.execute("UPDATE calls SET elapsed_seconds=2")
        db.commit()
    with pytest.raises(NonRetryableLLMError, match="等待时间"):
        asyncio.run(model.chat(publish=False))
    assert model.provider.call.await_count == 1
