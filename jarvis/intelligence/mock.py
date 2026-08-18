"""Deterministic mock provider for tests, benchmarks, and offline demos.

Not a toy: the mock provider honors capabilities (streaming, cancellation,
structured declarations), supports configurable failure and latency, and its
output is fully deterministic per request_id so assertions in tests are stable.
"""

from __future__ import annotations

import time
from typing import Any

from jarvis.exceptions import ProviderError
from jarvis.intelligence.models import (
    AIRequest,
    AIResponse,
    FinishReason,
    StreamChunk,
    TokenUsage,
    ToolCall,
)
from jarvis.intelligence.provider import (
    AIProvider,
    Capability,
    ProviderCapabilities,
    ProviderHealth,
    ProviderState,
)


class MockProvider(AIProvider):
    """Deterministic in-process provider.

    Unlike network adapters the mock is born READY: it has no external
    dependencies, so init() is a formality and generate() works immediately
    (this keeps tests short).

    Parameters:
    - fail_on_generate: raise ProviderError when generate() is called.
    - latency_ms: artificial delay before responding (0 = none).
    - capabilities: additional declared capabilities beyond TEXT_GENERATION
      (e.g. {Capability.STREAMING}) to exercise streaming paths.
    - model_ids: advertised model list (defaults to ("mock-model",)).
    """

    def __init__(
        self,
        provider_id: str = "mock",
        *,
        fail_on_generate: bool = False,
        latency_ms: float = 0.0,
        capabilities: set[Capability] | None = None,
        model_ids: tuple[str, ...] = ("mock-model",),
    ) -> None:
        super().__init__(provider_id)
        self._set_state(ProviderState.READY)
        self.fail_on_generate = fail_on_generate
        self.latency_ms = max(0.0, latency_ms)
        self._capabilities = ProviderCapabilities(
            capabilities=frozenset(
                {Capability.TEXT_GENERATION, *(capabilities or set())}
            ),
            model_ids=model_ids,
        )
        self._cancelled: set[str] = set()

    # --- surface -------------------------------------------------------

    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    def _probe_health(self) -> ProviderHealth:
        if self.fail_on_generate:
            return ProviderHealth(
                provider_id=self._provider_id,
                ok=False,
                state=ProviderState.DEGRADED,
                detail="mock provider configured to fail",
            )
        model = self._capabilities.model_ids[0] if self._capabilities.model_ids else None
        return ProviderHealth(
            provider_id=self._provider_id,
            ok=True,
            state=ProviderState.READY,
            detail="mock provider ready",
            model_loaded=model,
        )

    def generate(self, request: AIRequest) -> AIResponse:
        self._require_ready()
        self._maybe_wait(request)
        if request.metadata.get("force_error"):
            raise ProviderError("mock provider forced error")
        if self.fail_on_generate:
            raise ProviderError("mock provider is configured to fail")
        if request.tools and not self._capabilities.supports(Capability.TOOL_CALLING):
            self._require_capability(Capability.TOOL_CALLING)
        prompt = " ".join(
            message.content for message in request.messages if isinstance(message.content, str)
        )
        usage = TokenUsage(
            prompt_tokens=len(prompt), completion_tokens=4, total_tokens=len(prompt) + 4
        )
        tool_calls = None
        if request.tools:
            tool = request.tools[0]
            tool_calls = [
                ToolCall(
                    id="call_deterministic",
                    name=tool.name,
                    arguments={"query": prompt[:16]},
                )
            ]
        return AIResponse(
            request_id=request.request_id,
            provider=self._provider_id,
            model=request.model or (
                self._capabilities.model_ids[0]
                if self._capabilities.model_ids
                else "mock-model"
            ),
            content=f"mock:{prompt[:64] or 'empty'}",
            finish_reason=FinishReason.STOP,
            usage=usage,
            tool_calls=tool_calls,
        )

    async def stream(self, request: AIRequest) -> Any:
        self._require_ready()
        self._require_capability(Capability.STREAMING)
        if request.metadata.get("force_error"):
            yield StreamChunk.error_chunk("mock provider forced stream error")
            return
        if self.fail_on_generate:
            yield StreamChunk.error_chunk("mock provider is configured to fail")
            return
        self._maybe_wait(request)
        prompt = " ".join(
            message.content for message in request.messages if isinstance(message.content, str)
        )
        for token in (prompt[:32] or "empty")[:8].split():
            if request.request_id in self._cancelled:
                yield StreamChunk.completion(FinishReason.CANCELLED)
                return
            yield StreamChunk.text_delta(token + " ")
        yield StreamChunk.completion(FinishReason.STOP)

    def cancel(self, request_id: str) -> None:
        self._require_capability(Capability.CANCELLATION)
        self._cancelled.add(request_id)

    # --- helpers -------------------------------------------------------

    def _maybe_wait(self, request: AIRequest) -> None:
        if self.latency_ms > 0:
            override = request.metadata.get("latency_ms")
            time.sleep((float(override) if override is not None else self.latency_ms) / 1000.0)

    def reset(self) -> None:
        self._cancelled.clear()
        self.fail_on_generate = False
