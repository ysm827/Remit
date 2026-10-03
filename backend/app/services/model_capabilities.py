"""配置指纹绑定的能力档案；配置变化后返回 unknown，不沿用旧结论。"""

import json
from pathlib import Path

from app.config.setting import USER_CONFIG_PATH, settings
from app.services.api_probe import capability_fingerprint


ROLE_REQUIREMENTS = {
    "coordinator": {
        "label": "协调手",
        "needs_tools": False,
        "needs_vision": False,
        "structured_mode": "json_text",
    },
    "modeler": {
        "label": "建模手",
        "needs_tools": False,
        "needs_vision": False,
        "structured_mode": "json_text",
    },
    "coder": {
        "label": "代码手",
        "needs_tools": True,
        "needs_vision": False,
        "structured_mode": "tool_arguments",
        "parallel_tool_calls": False,
    },
    "writer": {
        "label": "论文手",
        "needs_tools": True,
        "needs_vision": False,
        "structured_mode": "json_text_and_tool_arguments",
    },
    "vision": {
        "label": "赛题识图",
        "needs_tools": False,
        "needs_vision": True,
        "structured_mode": "json_text",
    },
    "model_scout": {
        "label": "模型探索者",
        "needs_tools": False,
        "needs_vision": False,
        "structured_mode": "json_text",
    },
    "model_critic": {
        "label": "模型盲审者",
        "needs_tools": False,
        "needs_vision": False,
        "structured_mode": "json_text",
    },
}


def requirements(role: str) -> dict:
    result = dict(ROLE_REQUIREMENTS[role])
    result.update(
        max_calls=1 + 2 * int(result["needs_tools"]) + int(result["needs_vision"]),
        max_output_tokens=8192,
    )
    return result


def role_config(role: str, config=settings) -> dict:
    """内部使用的有效配置，包含密钥，不可直接作为 HTTP 响应。"""
    if role == "vision":

        def pick(name):
            return getattr(config, f"VISION_{name}", None) or getattr(
                config, f"COORDINATOR_{name}", None
            )

        protocol = pick("API_TYPE")
        return {
            "api_type": str(
                protocol.value if hasattr(protocol, "value") else protocol or ""
            ),
            "api_key": pick("API_KEY"),
            "model_id": pick("MODEL"),
            "base_url": pick("BASE_URL"),
            "max_tokens": config.VISION_MAX_TOKENS,
            "context_window": 128000,
            "reasoning_effort": None,
        }
    prefix = role.upper()
    protocol = getattr(config, f"{prefix}_API_TYPE")
    return {
        "api_type": str(
            protocol.value if hasattr(protocol, "value") else protocol or ""
        ),
        "api_key": getattr(config, f"{prefix}_API_KEY"),
        "model_id": getattr(config, f"{prefix}_MODEL"),
        "base_url": getattr(config, f"{prefix}_BASE_URL"),
        "context_window": getattr(config, f"{prefix}_CONTEXT_WINDOW"),
        "max_tokens": getattr(config, f"{prefix}_MAX_TOKENS"),
        "reasoning_effort": getattr(config, f"{prefix}_REASONING_EFFORT", None),
    }


def profile_path(role: str) -> Path:
    return USER_CONFIG_PATH.parent / f".capability-{role.lower()}.json"


def fallback_config(role: str, config=settings) -> dict:
    """Resolve the same fallback connection used by this role at runtime."""
    base = role_config(role, config)
    protocol = config.FALLBACK_API_TYPE or base["api_type"]
    return {
        "api_type": str(protocol.value if hasattr(protocol, "value") else protocol),
        "api_key": config.FALLBACK_API_KEY,
        "model_id": config.FALLBACK_MODEL,
        "base_url": config.FALLBACK_BASE_URL or base["base_url"],
        "context_window": config.FALLBACK_CONTEXT_WINDOW,
        "max_tokens": config.FALLBACK_MAX_TOKENS,
        "reasoning_effort": config.FALLBACK_REASONING_EFFORT,
    }


def load_profile(
    role: str,
    config=settings,
    *,
    fallback: bool = False,
    effective_config: dict | None = None,
) -> dict:
    """文件损坏或身份不匹配时不声明验证通过。"""
    try:
        key = f"fallback-{role}" if fallback else role
        profile = json.loads(profile_path(key).read_text(encoding="utf-8"))
        if (
            isinstance(profile, dict)
            and profile.get("schema_version") == 2
            and profile.get("fingerprint")
            == capability_fingerprint(
                effective_config
                if effective_config is not None
                else fallback_config(role, config)
                if fallback
                else role_config(role, config)
            )
        ):
            return {**profile, "requirements": requirements(role)}
    except (OSError, ValueError):
        pass
    return {
        "requirements": requirements(role),
        "connection": "unknown",
        "text": "unknown",
        "tools": "unknown",
        "tool_result": "unknown",
        "structured_output": "unknown",
        "vision": "unknown",
        "checked_at": None,
    }
