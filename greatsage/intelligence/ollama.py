"""Ollama provider adapter (local, HTTP).

Connects to a configured Ollama endpoint (default http://127.0.0.1:11434),
discovers availability + models, and implements health/capabilities/generate/
stream/cancel. It never downloads models or touches the Ollama disk cache —
model selection stays a config concern. When Ollama is not running the
provider reports UNAVAILABLE and the runtime remains functional.
"""

from __future__ import annotations

import json
import logging
import urllib.error
from datetime import UTC, datetime
from typing import Any

from greatsage.exceptions import ProviderError, ProviderUnavailableError
from greatsage.intelligence import transport
from greatsage.intelligence.models import (
    AIRequest,
    AIResponse,
    FinishReason,
    Message,
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

log = logging.getLogger("greatsage.intelligence.ollama")

OLLAMA_DEFAULT_URL = "http://127.0.0.1:11434"


def _join_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def _map_finish_reason(reason: str | None) -> FinishReason:
    if reason == "length":
        return FinishReason.LENGTH
    if reason in ("tool_calls", "tool_call"):
        return FinishReason.TOOL_CALL
    if reason == "canceled":
        return FinishReason.CANCELLED
    return FinishReason.STOP


class OllamaProvider(AIProvider):
    """Adapter for a local Ollama server.

    Config fields (from ai.providers.local): base_url, model, enabled,
    timeout_seconds. The 'local' config slot is Phase 0/1 naming; the provider
    id stays 'local'.
    """

    def __init__(
        self,
        *,
        base_url: str = OLLAMA_DEFAULT_URL,
        model: str = "",
        timeout_seconds: float = 60.0,
        provider_id: str = "local",
    ) -> None:
        super().__init__(provider_id)
        self._base_url = base_url if base_url else OLLAMA_DEFAULT_URL
        self._configured_model = model
        self._timeout = timeout_seconds if timeout_seconds > 0 else 60.0
        self._models: tuple[str, ...] = ()

    # --- public surface ------------------------------------------------

    def capabilities(self) -> ProviderCapabilities:
        caps = {
            Capability.TEXT_GENERATION,
            Capability.STREAMING,
            Capability.LOCAL,
            Capability.CANCELLATION,
        }
        if self._models and any("vision" in name for name in self._models):
            caps.add(Capability.VISION)
        return ProviderCapabilities(
            capabilities=frozenset(caps),
            model_ids=self._models,
        )

    def _probe_health(self) -> ProviderHealth:
        try:
            data = transport.request_json(
                _join_url(self._base_url, "/api/tags"),
                timeout=min(self._timeout, 5.0),
                default_timeout=5.0,
            )
        except urllib.error.URLError:
            self._set_state(ProviderState.UNAVAILABLE, "connection failed")
            return ProviderHealth(
                provider_id=self._provider_id,
                ok=False,
                state=ProviderState.UNAVAILABLE,
                detail="connection failed",
            )
        except (transport.HTTPErrorStatus, ValueError) as exc:
            self._set_state(ProviderState.DEGRADED, "malformed response")
            return ProviderHealth(
                provider_id=self._provider_id,
                ok=False,
                state=ProviderState.DEGRADED,
                detail=f"malformed response: {str(exc)[:120]}",
            )
        models = tuple(
            str(item.get("name", ""))
            for item in data.get("models", [])
            if isinstance(item, dict) and item.get("name")
        )
        self._models = models
        loaded = self._configured_model if self._configured_model in models else None
        return ProviderHealth(
            provider_id=self._provider_id,
            ok=True,
            state=ProviderState.READY,
            detail=f"{len(models)} model(s) available",
            model_loaded=loaded,
        )

    def generate(self, request: AIRequest) -> AIResponse:
        self._require_ready()
        if request.tools:
            self._require_capability(Capability.TOOL_CALLING)
        started = datetime.now(UTC)
        try:
            data = transport.request_json(
                _join_url(self._base_url, "/api/chat"),
                method="POST",
                body=self._chat_body(request),
                timeout=request.timeout or self._timeout,
                default_timeout=self._timeout,
            )
        except urllib.error.URLError as exc:
            self._set_state(ProviderState.UNAVAILABLE, "connection failed")
            raise ProviderUnavailableError(
                f"ollama unreachable: {exc}"
            ) from exc
        except transport.HTTPErrorStatus as exc:
            raise ProviderError(f"ollama error: {exc}") from exc
        except ValueError as exc:
            raise ProviderError(f"ollama malformed response: {exc}") from exc
        if not isinstance(data, dict):
            raise ProviderError("ollama returned a non-object response")
        usage = None
        prompt_tokens = data.get("prompt_eval_count")
        completion_tokens = data.get("eval_count")
        if prompt_tokens is not None or completion_tokens is not None:
            usage = TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        tool_calls = None
        raw_calls = data.get("tool_calls") or []
        if raw_calls:
            tool_calls = [
                ToolCall(
                    id=str(call.get("id") or f"call_{index}"),
                    name=str(call.get("function", {}).get("name", "unknown")),
                    arguments=dict(call.get("function", {}).get("arguments", {})),
                )
                for index, call in enumerate(raw_calls)
                if isinstance(call, dict)
            ]
        elapsed = (datetime.now(UTC) - started).total_seconds() * 1000.0
        log.info(
            "ollama generate completed",
            extra={
                "component": "intelligence",
                "provider": self._provider_id,
                "duration_ms": elapsed,
                "model": data.get("model", self._configured_model),
            },
        )
        return AIResponse(
            request_id=request.request_id,
            provider=self._provider_id,
            model=str(data.get("model") or self._configured_model),
            content=str(data.get("message", {}).get("content") or ""),
            finish_reason=_map_finish_reason(data.get("done_reason")),
            usage=usage,
            tool_calls=tool_calls,
        )

    async def stream(self, request: AIRequest) -> Any:
        self._require_ready()
        if request.tools:
            self._require_capability(Capability.TOOL_CALLING)
        try:
            response = transport.request_text(
                _join_url(self._base_url, "/api/chat"),
                method="POST",
                body=self._chat_body(request, streaming=True),
                timeout=request.timeout or self._timeout,
                default_timeout=self._timeout,
            )
        except urllib.error.URLError as exc:
            self._set_state(ProviderState.UNAVAILABLE, "connection failed")
            raise ProviderUnavailableError(f"ollama unreachable: {exc}") from exc
        except transport.HTTPErrorStatus as exc:
            raise ProviderError(f"ollama error: {exc}") from exc
        for line in response.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except ValueError as exc:
                raise ProviderError(f"ollama malformed stream line: {exc}") from exc
            if not isinstance(data, dict):
                continue
            if data.get("error"):
                yield StreamChunk.error_chunk(str(data["error"]))
                return
            content = data.get("message", {}).get("content")
            if content:
                yield StreamChunk.text_delta(str(content))
            raw_calls = data.get("tool_calls") or []
            for call in raw_calls:
                if not isinstance(call, dict):
                    continue
                yield StreamChunk.tool_call_delta(
                    tool_call_id=str(call.get("id")),
                    name=str(call.get("function", {}).get("name")),
                    arguments=json.dumps(call.get("function", {}).get("arguments", {})),
                )
            if data.get("done"):
                prompt_tokens = data.get("prompt_eval_count")
                completion_tokens = data.get("eval_count")
                usage = None
                if prompt_tokens is not None or completion_tokens is not None:
                    usage = TokenUsage(
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                    )
                yield StreamChunk.completion(
                    _map_finish_reason(data.get("done_reason")), usage=usage
                )
                return

    def cancel(self, request_id: str) -> None:
        """Best-effort cancel; Ollama polls the client, so cancelling is a no-op.

        In-flight generations are interrupted by closing the connection; the
        adapter has no server-side handle. The capability is advertised so the
        service layer can record the intent without crashing.
        """
        log.info(
            "ollama cancel requested (no server-side handle)",
            extra={"component": "intelligence", "provider": self._provider_id},
        )

    # --- internals ------------------------------------------------------

    def _chat_body(self, request: AIRequest, streaming: bool = False) -> dict[str, Any]:
        messages: list[dict[str, Any]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        for message in request.messages:
            messages.append(
                {
                    "role": message.role.value,
                    "content": self._render_content(message),
                    **(
                        {"tool_call_id": message.tool_call_id}
                        if message.tool_call_id
                        else {}
                    ),
                }
            )
        body: dict[str, Any] = {
            "model": request.model or self._configured_model,
            "messages": messages,
            "stream": streaming,
        }
        if request.temperature is not None:
            body["options"] = {"temperature": request.temperature}
        if request.tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    },
                }
                for tool in request.tools
            ]
        return body

    def _render_content(self, message: Message) -> str:
        if isinstance(message.content, str):
            return message.content
        parts: list[str] = []
        for part in message.content:
            if part.kind == "text":
                parts.append(part.text)
            else:
                parts.append(
                    f"[tool_call name={part.name} arguments={json.dumps(part.arguments)}]"
                )
        return "\n".join(parts)

    def _on_shutdown(self) -> None:
        self._models = ()
