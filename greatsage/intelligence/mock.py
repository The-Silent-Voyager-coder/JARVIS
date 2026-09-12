"""Deterministic mock provider for tests, benchmarks, and offline demos.

Not a toy: the mock provider honors capabilities (streaming, cancellation,
structured declarations), supports configurable failure and latency, and its
output is fully deterministic per request_id so assertions in tests are stable.
"""

from __future__ import annotations

import time
from typing import Any

from greatsage.exceptions import ProviderError
from greatsage.intelligence.models import (
    AIRequest,
    AIResponse,
    FinishReason,
    StreamChunk,
    TokenUsage,
    ToolCall,
)
from greatsage.intelligence.provider import (
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
    - script: deterministic response sequence for agent-loop tests. Each
      entry is a dict with optional "content" (str) and "tool_calls"
      (list of {"id", "name", "arguments"}), e.g.:
          ({"tool_calls": [{"id": "call_1", "name": "system.info",
                            "arguments": {}}]},
           {"content": "all done"})
      Entries are consumed in order on successive generate() calls; once the
      script is exhausted the provider falls back to its default response.
      When the script contains tool calls, TOOL_CALLING is declared
      automatically (a provider that returns tool calls supports them).
    """

    def __init__(
        self,
        provider_id: str = "mock",
        *,
        fail_on_generate: bool = False,
        latency_ms: float = 0.0,
        capabilities: set[Capability] | None = None,
        model_ids: tuple[str, ...] = ("mock-model",),
        script: tuple[dict[str, Any], ...] | None = None,
    ) -> None:
        super().__init__(provider_id)
        self._set_state(ProviderState.READY)
        self.fail_on_generate = fail_on_generate
        self.latency_ms = max(0.0, latency_ms)
        declared = set(capabilities or set())
        if script and any(entry.get("tool_calls") for entry in script):
            declared.add(Capability.TOOL_CALLING)
        self._capabilities = ProviderCapabilities(
            capabilities=frozenset({Capability.TEXT_GENERATION, *declared}),
            model_ids=model_ids,
        )
        self._script = script
        self._script_index = 0
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
        model = request.model or (
            self._capabilities.model_ids[0]
            if self._capabilities.model_ids
            else "mock-model"
        )
        if self._script is not None:
            return self._scripted_response(request, model)
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
            model=model,
            content=f"mock:{prompt[:64] or 'empty'}",
            finish_reason=FinishReason.STOP,
            usage=usage,
            tool_calls=tool_calls,
        )

    def _scripted_response(self, request: AIRequest, model: str) -> AIResponse:
        prompt = " ".join(
            message.content for message in request.messages if isinstance(message.content, str)
        )
        usage = TokenUsage(
            prompt_tokens=len(prompt), completion_tokens=4, total_tokens=len(prompt) + 4
        )
        if self._script is None or self._script_index >= len(self._script):
            return AIResponse(
                request_id=request.request_id,
                provider=self._provider_id,
                model=model,
                content=f"mock:{prompt[:64] or 'empty'}",
                finish_reason=FinishReason.STOP,
                usage=usage,
            )
        entry = self._script[self._script_index]
        self._script_index += 1
        raw_calls = entry.get("tool_calls") or []
        calls = [
            ToolCall(
                id=str(call["id"]),
                name=str(call["name"]),
                arguments=dict(call.get("arguments") or {}),
            )
            for call in raw_calls
        ]
        finish = FinishReason.TOOL_CALL if calls else FinishReason.STOP
        requested = entry.get("finish_reason")
        if requested is not None:
            finish = FinishReason(str(requested))
        return AIResponse(
            request_id=request.request_id,
            provider=self._provider_id,
            model=model,
            content=entry.get("content"),
            finish_reason=finish,
            usage=usage,
            tool_calls=calls or None,
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
        self._script_index = 0
        self.fail_on_generate = False
