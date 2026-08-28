"""Provider 接口定义。

每家模型厂商一个实现，把各自的 API 差异关在本层之内。
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.core.llm.types import StandardResponse

DeltaCallback = Callable[[str], Awaitable[None]]


@dataclass(slots=True)
class ProviderRequest:
    """Provider-neutral invocation assembled by the LLM facade."""

    messages: list[dict]
    model: str
    api_key: str
    base_url: str | None
    tools: list[dict] | None
    tool_choice: str | None
    max_tokens: int | None
    top_p: float | None
    on_delta: DeltaCallback | None
    reasoning_effort: str | None


class BaseProvider(ABC):
    """统一的模型调用契约。"""

    async def call(
        self,
        messages: list[dict],
        model: str,
        api_key: str,
        base_url: str | None = None,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        on_delta: DeltaCallback | None = None,
        reasoning_effort: str | None = None,
    ) -> StandardResponse:
        """Freeze the public call contract and dispatch a request object."""
        request = ProviderRequest(
            messages=messages,
            model=model,
            api_key=api_key,
            base_url=base_url,
            tools=tools,
            tool_choice=tool_choice,
            max_tokens=max_tokens,
            top_p=top_p,
            on_delta=on_delta,
            reasoning_effort=reasoning_effort,
        )
        return await self.send(request)

    @abstractmethod
    async def send(self, request: ProviderRequest) -> StandardResponse:
        """Translate and execute one provider-neutral request."""
