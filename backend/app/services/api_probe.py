"""Small, side-effect-contained probes for user-supplied service settings."""

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4
import io
import random
import time

from app.core.json_recovery import decode_json_object
from app.core.llm.content import build_image_block, build_text_block
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
    return f"✗ 服务验证失败（{type(error).__name__}）；请检查接入协议、网络和参数。"


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
        response = await asyncio.wait_for(
            provider.call(
                messages=[{"role": "user", "content": "Reply with OK."}],
                model=model_id,
                api_key=api_key,
                base_url=endpoint,
                max_tokens=128,
            ),
            timeout=timeout,
        )
    except TimeoutError:
        return False, "✗ 服务商在验证时限内没有响应；请检查网络、代理和防火墙"
    except Exception as error:
        return False, explain_probe_failure(error)
    if not (response.content or "").strip():
        return False, "✗ 连接已建立，但模型未返回非空文本；能力仍未验证"
    return True, "✓ 模型连接与文本回复可用；工具能力尚未验证"


def capability_fingerprint(config: dict) -> str:
    """绑定协议、身份、密钥及有效参数，仅返回摘要。"""
    return hashlib.sha256(
        json.dumps(config, sort_keys=True, default=str).encode()
    ).hexdigest()


def vision_challenge() -> tuple[list[dict], dict, str]:
    """Build a synthetic image whose expected answer is absent from the prompt."""
    from PIL import Image, ImageDraw, ImageFont

    rng = random.SystemRandom()
    colors = ["red", "green", "blue", "yellow", "magenta", "cyan"]
    rng.shuffle(colors)
    expected = {"code": f"{rng.randrange(1000000):06d}", "colors": colors}
    picture = Image.new("RGB", (600, 240), "white")
    draw = ImageDraw.Draw(picture)
    draw.text(
        (130, 25), expected["code"], fill="black", font=ImageFont.load_default(size=70)
    )
    for index, color in enumerate(colors):
        draw.rectangle((index * 100 + 5, 135, index * 100 + 95, 225), fill=color)
    output = io.BytesIO()
    picture.save(output, format="PNG")
    image = output.getvalue()
    return (
        [
            build_text_block(
                'Read the image. Return only JSON with "code": the six printed digits as a string '
                '(preserve leading zeros), and "colors": the six block colors from left to right. '
                "Use the names red, green, blue, yellow, magenta, cyan."
            ),
            build_image_block(image),
        ],
        expected,
        hashlib.sha256(image).hexdigest(),
    )


async def check_capabilities(
    config: dict,
    *,
    needs_tools: bool,
    needs_vision: bool = False,
    structured_mode: str = "json_text",
    parallel_tool_calls: bool | None = None,
) -> dict:
    """Probe only requested workflow capabilities; record usage without retries."""
    profile = {
        "schema_version": 2,
        "fingerprint": capability_fingerprint(config),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "connection": "unknown",
        "text": "unknown",
        "tools": "unknown",
        "tool_result": "unknown",
        "structured_output": "unknown",
        "vision": "unknown",
        "calls": 0,
        "error": None,
        "errors": {},
        "attempts": [],
        "structured_mode": structured_mode,
        "probe_parameters": {"max_tokens": 8192, "timeout_seconds": 90},
    }
    structured_checks = {
        key: "unknown"
        for key in ("json_text", "tool_arguments")
        if key in structured_mode
    }
    profile["structured_checks"] = structured_checks
    current_check = "text"
    provider = provider_for(config["api_type"])
    kwargs = {key: config[key] for key in ("api_key", "base_url")}
    kwargs.update(model=config["model_id"], max_tokens=8192)
    if config.get("reasoning_effort"):
        kwargs["reasoning_effort"] = config["reasoning_effort"]

    async def invoke(messages, **extra):
        profile["calls"] += 1
        attempt = {
            "check": current_check,
            "status": "verification_failed",
            "prompt_tokens": None,
            "completion_tokens": None,
            "cost": None,
        }
        profile["attempts"].append(attempt)
        started = time.monotonic()
        try:
            result = await asyncio.wait_for(
                provider.call(messages=messages, **kwargs, **extra), 90
            )
            profile["connection"] = "supported"
            usage = getattr(result, "usage", None)
            if usage is not None and usage.known:
                attempt.update(
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                )
            reason = str(result.finish_reason or "").lower()
            if (
                usage is not None and usage.known and usage.completion_tokens >= 8192
            ) or any(
                value in reason
                for value in ("length", "max_tokens", "max_output_tokens", "incomplete")
            ):
                attempt["status"] = "truncated"
                raise ValueError("验证输出被截断，能力未知")
            attempt["status"] = "completed"
            return result
        except asyncio.CancelledError:
            attempt["status"] = "cancelled_outcome_unknown"
            raise
        finally:
            attempt["elapsed_seconds"] = round(time.monotonic() - started, 3)

    try:
        response = await invoke(
            [
                {
                    "role": "user",
                    "content": (
                        'Return only the JSON object {"ready": true}.'
                        if "json_text" in structured_mode
                        else "Reply with OK."
                    ),
                }
            ]
        )
        profile["connection"] = "supported"
        profile["text"] = (
            "supported" if (response.content or "").strip() else "unsupported"
        )
        if "json_text" in structured_mode:
            parsed = decode_json_object(response.content or "")
            structured_checks["json_text"] = (
                "supported"
                if isinstance(parsed, dict) and parsed.get("ready") is True
                else "unsupported"
            )
        if needs_tools:
            current_check = "tools"
            messages = [
                {
                    "role": "user",
                    "content": "Call remit_probe once with value 7. After receiving the result, reply with its verification token only.",
                }
            ]
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "remit_probe",
                        "description": "Return a verification token",
                        "parameters": {
                            "type": "object",
                            "properties": {"value": {"type": "integer"}},
                            "required": ["value"],
                        },
                    },
                }
            ]
            response = await invoke(
                messages,
                tools=tools,
                tool_choice="auto",
                parallel_tool_calls=parallel_tool_calls,
            )
            calls = response.tool_calls
            valid = len(calls) == 1 and calls[0].name == "remit_probe"
            try:
                valid = valid and json.loads(calls[0].arguments) == {"value": 7}
            except (ValueError, IndexError):
                valid = False
            profile["tools"] = "supported" if valid else "unsupported"
            if "tool_arguments" in structured_mode:
                structured_checks["tool_arguments"] = profile["tools"]
            if valid:
                token = uuid4().hex[:16]
                messages.extend(
                    [
                        {
                            "role": "assistant",
                            "content": response.content,
                            "tool_calls": [
                                {
                                    "id": calls[0].id,
                                    "type": "function",
                                    "function": {
                                        "name": calls[0].name,
                                        "arguments": calls[0].arguments,
                                    },
                                }
                            ],
                        },
                        {"role": "tool", "tool_call_id": calls[0].id, "content": token},
                    ]
                )
                current_check = "tool_result"
                final = await invoke(
                    messages,
                    tools=tools,
                    tool_choice="none",
                    parallel_tool_calls=parallel_tool_calls,
                )
                profile["tool_result"] = (
                    "supported"
                    if (final.content or "").strip() == token
                    else "unsupported"
                )
        if needs_vision:
            current_check = "vision"
            content, expected, digest = vision_challenge()
            profile["vision_evidence"] = {"image_sha256": digest}
            response = await invoke([{"role": "user", "content": content}])
            actual = decode_json_object(response.content or "")
            profile["vision"] = "supported" if actual == expected else "unsupported"
            profile["vision_evidence"]["matched"] = actual == expected
    except Exception as error:
        # 限流、超时及网关拒绝不证明“不支持”，保留未测能力为 unknown。
        detail = str(error).casefold()
        unsupported_image = (
            current_check == "vision"
            and any(
                phrase in detail
                for phrase in (
                    "does not support image",
                    "does not support vision",
                    "images are not supported",
                    "image input is not supported",
                    "model is not multimodal",
                )
            )
            and any(code in detail for code in ("400", "422"))
        )
        if unsupported_image:
            profile["vision"] = "unsupported"
        profile["error"] = {
            "status": "unsupported" if unsupported_image else "verification_failed",
            "check": current_check,
            "message": explain_probe_failure(error),
        }
        profile["errors"][current_check] = profile["error"]
    values = list(structured_checks.values())
    profile["structured_output"] = (
        "unsupported"
        if "unsupported" in values
        else "supported"
        if values and all(value == "supported" for value in values)
        else "unknown"
    )
    return profile


def check_openalex_identity(email: str) -> tuple[bool, str]:
    try:
        probe_openalex(email)
    except Exception as error:
        return False, f"✗ OpenAlex 拒绝了该联系邮箱：{error}"
    return True, "✓ OpenAlex 联系邮箱可用"
