import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.config.setting import ApiType, Settings, settings
from app.core.llm.llm_factory import _agent_llm
from app.routers import modeling_router
from app.routers.modeling_router import (
    ValidateApiKeyRequest,
    SaveApiConfigRequest,
    get_api_config_status,
    store_api_configuration,
    validate_api_key,
)


class ApiConfigFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_saved_api_config_survives_backend_restart(self):
        """界面保存后，新 Settings/LLM 实例必须仍能读取密钥。"""
        config = {
            "apiKey": "persisted-secret",
            "baseUrl": "https://relay.example.com/v1",
            "modelId": "deepseek-chat",
            "apiType": "openai-chat",
            "contextWindow": 128000,
        }
        request = SaveApiConfigRequest(
            coordinator=config,
            modeler=config,
            coder=config,
            writer=config,
            openalex_email="",
        )

        original_values = {
            name: getattr(settings, name)
            for role in ("COORDINATOR", "MODELER", "CODER", "WRITER")
            for name in (
                f"{role}_API_KEY",
                f"{role}_BASE_URL",
                f"{role}_MODEL",
                f"{role}_API_TYPE",
                f"{role}_CONTEXT_WINDOW",
            )
        }
        try:
            with tempfile.TemporaryDirectory() as tmp:
                user_config = Path(tmp) / ".env.user"
                with patch.object(
                    modeling_router,
                    "_USER_CONFIG_PATH",
                    user_config,
                    create=True,
                ):
                    await store_api_configuration(request)

                self.assertTrue(user_config.is_file())
                reloaded = Settings(_env_file=user_config)
                coordinator = _agent_llm(reloaded, "COORDINATOR", "task-test")
                self.assertEqual(coordinator.api_key, "persisted-secret")
                self.assertEqual(coordinator.model, "deepseek-chat")
                self.assertEqual(
                    coordinator.base_url,
                    "https://relay.example.com/v1",
                )
        finally:
            for name, value in original_values.items():
                setattr(settings, name, value)
            modeling_router._runtime_configured_agents.clear()

    async def test_api_validation_timeout_returns_actionable_message(self):
        request = ValidateApiKeyRequest(
            api_key="test-key",
            base_url="https://api.deepseek.com",
            model_id="deepseek-v4-pro",
            api_type="openai-chat",
        )

        with patch(
            "app.services.api_probe.OpenAIChatProvider.call",
            new=AsyncMock(side_effect=asyncio.TimeoutError),
        ):
            result = await validate_api_key(request)

        self.assertFalse(result.valid)
        self.assertIn("验证时限", result.message)
        self.assertIn("网络", result.message)

    async def test_blank_ui_values_do_not_overwrite_environment_config(self):
        blank_config = {
            "apiKey": "",
            "baseUrl": "",
            "modelId": "",
            "apiType": "",
            "contextWindow": 128000,
        }
        request = SaveApiConfigRequest(
            coordinator=blank_config,
            modeler={},
            coder={},
            writer={},
            openalex_email="",
        )

        with (
            patch.object(settings, "COORDINATOR_API_KEY", "env-key"),
            patch.object(settings, "COORDINATOR_MODEL", "gpt-5.6-sol"),
            patch.object(
                settings,
                "COORDINATOR_BASE_URL",
                "https://api.ebondai.com/",
            ),
            patch.object(
                settings,
                "COORDINATOR_API_TYPE",
                ApiType.OPENAI_RESPONSES,
            ),
            patch.object(modeling_router, "persist_user_config") as persist,
        ):
            await store_api_configuration(request)

            persist.assert_called_once()

            self.assertEqual(settings.COORDINATOR_API_KEY, "env-key")
            self.assertEqual(settings.COORDINATOR_MODEL, "gpt-5.6-sol")
            self.assertEqual(
                settings.COORDINATOR_BASE_URL,
                "https://api.ebondai.com/",
            )
            self.assertEqual(
                settings.COORDINATOR_API_TYPE,
                ApiType.OPENAI_RESPONSES,
            )

    async def test_status_reports_configuration_without_exposing_keys(self):
        patches = []
        for prefix in ("COORDINATOR", "MODELER", "CODER", "WRITER"):
            patches.extend(
                [
                    patch.object(settings, f"{prefix}_API_KEY", "secret-key"),
                    patch.object(settings, f"{prefix}_MODEL", "gpt-5.6-sol"),
                    patch.object(
                        settings,
                        f"{prefix}_BASE_URL",
                        "https://relay.example.com/v1",
                    ),
                    patch.object(
                        settings,
                        f"{prefix}_API_TYPE",
                        ApiType.OPENAI_RESPONSES,
                    ),
                    patch.object(settings, f"{prefix}_CONTEXT_WINDOW", 200000),
                ]
            )

        for active_patch in patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)

        status = await get_api_config_status()
        payload = status.model_dump()

        self.assertTrue(payload["configured"])
        for role in ("coordinator", "modeler", "coder", "writer"):
            self.assertTrue(payload["agents"][role]["configured"])
        coordinator = payload["agents"]["coordinator"]
        self.assertEqual(coordinator["api_type"], "openai-responses")
        self.assertEqual(coordinator["model_id"], "gpt-5.6-sol")
        self.assertEqual(coordinator["base_url"], "https://relay.example.com/v1")
        self.assertEqual(coordinator["context_window"], 200000)
        self.assertTrue(coordinator["api_key_configured"])
        self.assertEqual(coordinator["source"], "environment")
        self.assertNotIn("secret-key", repr(payload))


if __name__ == "__main__":
    unittest.main()
