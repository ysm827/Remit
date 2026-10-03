"""最终请求的保守预算检查，不裁剪用户约束或完整工具调用。"""

import json

from app.core.llm.errors import NonRetryableLLMError


def estimate_request(messages: list, tools: list | None, output_tokens: int) -> dict:
    """包含追加上下文、工具定义、图片估算及输出预留，明确不是实测 usage。"""

    def count(value):
        if isinstance(value, dict):
            if value.get("type") in {"image_url", "input_image", "image"}:
                return 4096
            return sum(count(k) + count(v) for k, v in value.items()) + 4
        if isinstance(value, list):
            return sum(count(v) for v in value)
        text = str(value or "")
        non_ascii = sum(ord(c) > 127 for c in text)
        return non_ascii + (len(text) - non_ascii + 2) // 3

    input_estimate = count(messages) + count(tools or [])
    return {
        "input_estimate": input_estimate,
        "output_reserved": output_tokens,
        "total_estimate": int(input_estimate * 1.1) + output_tokens,
        "estimated": True,
    }


def check_request(
    messages: list, tools: list | None, output_tokens: int, context_window: int
) -> dict:
    """请求发送前检查；超限时保留草稿并要求拆分，禁止盲目重试。"""
    estimate = estimate_request(messages, tools, output_tokens)
    if estimate["total_estimate"] > context_window:
        raise NonRetryableLLMError(
            "最终请求超出上下文预算（含公共状态、工具与输出预留）；请拆分当前步骤。"
            + json.dumps(estimate)
        )
    return estimate
