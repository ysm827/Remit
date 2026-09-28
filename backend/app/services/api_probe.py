"""Small, side-effect-contained probes for user-supplied service settings."""

import asyncio
from collections.abc import Callable

import requests

from app.config.setting import ApiType, settings
from app.core.llm.providers.anthropic import AnthropicProvider
from app.core.llm.providers.base import BaseProvider
from app.core.llm.providers.gemini import GeminiProvider
from app.core.llm.providers.openai_chat import OpenAIChatProvider
from app.core.llm.providers.openai_responses import OpenAIResponsesProvider


ProviderFactory = Callable[[], BaseProvider]

_PROVIDER_FACTORIES: dict[ApiType, ProviderFactory] = {
    ApiType.OPENAI_RESPONSES: OpenAIResponsesProvider,
    ApiType.ANTHROPIC: AnthropicProvider,
    ApiType.GEMINI: GeminiProvider,
}


def provider_for(api_type: str) -> BaseProvider:
    """Create the requested adapter, defaulting to OpenAI-compatible chat."""
    try:
        normalized = ApiType(api_type)
    except ValueError:
        normalized = ApiType.OPENAI_CHAT
    return _PROVIDER_FACTORIES.get(normalized, OpenAIChatProvider)()


def explain_probe_failure(error: Exception) -> str:
    """Translate provider failures into a short settings-dialog diagnosis."""
    detail = str(error)
    folded = detail.casefold()
    diagnoses = (
        (("401", "unauthorized"), "密钥未获服务商认可，可能无效或已经过期"),
        (("404", "not found"), "没有找到所填模型，请同时核对模型名称与服务地址"),
        (("429", "rate limit"), "服务商正在限流，请稍后再验证"),
        (("403", "forbidden"), "当前账号无权调用该模型，也可能是余额不足"),
    )
    for markers, message in diagnoses:
        if any(marker in folded for marker in markers):
            return f"✗ {message}"
    compact = " ".join(detail.split())
    if len(compact) > 80:
        compact = f"{compact[:77]}..."
    return f"✗ 服务验证失败：{compact or type(error).__name__}"


def probe_openalex(email: str) -> None:
    """Raise when OpenAlex rejects the supplied polite-pool identity."""
    query = {"mailto": email}
    if settings.OPENALEX_API_KEY:
        query["api_key"] = settings.OPENALEX_API_KEY
    response = requests.get(
        "https://api.openalex.org/works",
        params=query,
        timeout=15,
    )
    response.raise_for_status()


async def check_model_connection(
    *,
    api_type: str,
    api_key: str,
    model_id: str,
    base_url: str,
    timeout: float,
) -> tuple[bool, str]:
    """Exercise the cheapest possible model request and explain any failure."""
    provider = provider_for(api_type)
    endpoint = None if base_url == "https://api.openai.com/v1" else base_url
    try:
        await asyncio.wait_for(
            provider.call(
                messages=[{"role": "user", "content": "Reply with OK."}],
                model=model_id,
                api_key=api_key,
                base_url=endpoint,
                max_tokens=2,
            ),
            timeout=timeout,
        )
    except TimeoutError:
        return False, "✗ 服务商在验证时限内没有响应；请检查网络、代理和防火墙"
    except Exception as error:
        return False, explain_probe_failure(error)
    return True, "✓ 模型连接可用"


def check_openalex_identity(email: str) -> tuple[bool, str]:
    try:
        probe_openalex(email)
    except Exception as error:
        return False, f"✗ OpenAlex 拒绝了该联系邮箱：{error}"
    return True, "✓ OpenAlex 联系邮箱可用"
