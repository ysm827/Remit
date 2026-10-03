"""LLM Provider 的可分类错误。"""


class NonRetryableLLMError(RuntimeError):
    """重复发送相同请求不会改善的上游错误。"""


class ModelStageBudgetExceeded(NonRetryableLLMError):
    """Durable stage allowance exhausted; provider configuration may be valid."""

    def __init__(self, *, used_calls, call_limit, elapsed_seconds, seconds_limit):
        self.used_calls = used_calls
        self.call_limit = call_limit
        self.elapsed_seconds = elapsed_seconds
        self.seconds_limit = seconds_limit
        if used_calls >= call_limit:
            detail = f"本阶段模型调用预算已用完（{used_calls}/{call_limit} 次）"
        else:
            detail = (
                f"本阶段累计模型等待时间已达上限（{elapsed_seconds:.1f}/"
                f"{seconds_limit:.1f} 秒）"
            )
        super().__init__(
            detail + "；成果已保留，普通恢复不会重置额度，请调整阶段预算。"
        )


class TransientLLMError(RuntimeError):
    """供应商响应或传输异常，可在有限次数内重新请求。"""


class ResponseStreamInterruptedError(TransientLLMError):
    """响应流结束但没有终态；部分文本不能作为完整结果执行。"""


class ProviderRefusalError(NonRetryableLLMError):
    """模型因安全策略拒绝处理当前请求。"""

    def __init__(
        self,
        provider: str,
        model: str,
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        self.provider = provider
        self.model = model
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        super().__init__(f"{provider} 模型 {model} 拒绝处理当前请求")
