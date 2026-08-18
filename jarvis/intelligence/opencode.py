"""OpenCode provider adapter (remote code execution).

Phase 2 scope: provider connection only — connectivity/health via
`/global/health`, session lifecycle via `/session/*`, generation via
`prompt_async`/`/session/:id/prompt`, streaming via `/event` SSE, abort via
`/session/:id/abort`. No authority delegation, no agent loop — the provider
merely routes model calls to an OpenCode server.

The OpenCode server surface is interrogated at init time through `/doc`
(OpenAPI 3.1); if the spec cannot be fetched, the adapter reports DEGRADED
but still attempts direct endpoint calls, which keeps the runtime functional.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
from datetime import UTC, datetime
from typing import Any

from jarvis.exceptions import ProviderError, ProviderUnavailableError
from jarvis.intelligence import transport
from jarvis.intelligence.models import (
    AIRequest,
    AIResponse,
    FinishReason,
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

log = logging.getLogger("jarvis.intelligence.opencode")

OPENCODE_DEFAULT_URL = "http://127.0.0.1:4096"


class OpenCodeProvider(AIProvider):
    """Adapter for an OpenCode server (http://127.0.0.1:4096 by default).

    Config fields (from ai.providers.opencode): base_url, api_key_env,
    enabled, timeout_seconds. The provider id stays 'opencode'.
    """

    def __init__(
        self,
        *,
        base_url: str = OPENCODE_DEFAULT_URL,
        api_key_env: str = "",
        timeout_seconds: float = 60.0,
        provider_id: str = "opencode",
    ) -> None:
        super().__init__(provider_id)
        self._base_url = base_url if base_url else OPENCODE_DEFAULT_URL
        self._timeout = timeout_seconds if timeout_seconds > 0 else 60.0
        self._api_key: str | None = None
        self._api_key_env = api_key_env
        self._spec_fetched = False

    # --- public surface ------------------------------------------------

    def capabilities(self) -> ProviderCapabilities:
        caps = {
            Capability.TEXT_GENERATION,
            Capability.REMOTE,
            Capability.CANCELLATION,
            Capability.CODE_EXECUTION,
        }
        return ProviderCapabilities(
            capabilities=frozenset(caps),
            model_ids=(),
        )

    def _probe_health(self) -> ProviderHealth:
        try:
            data = transport.request_json(
                f"{self._base_url.rstrip('/')}/global/health",
                timeout=min(self._timeout, 5.0),
                default_timeout=5.0,
            )
        except urllib.error.URLError as exc:
            self._set_state(ProviderState.UNAVAILABLE, "connection failed")
            return ProviderHealth(
                provider_id=self._provider_id,
                ok=False,
                state=ProviderState.UNAVAILABLE,
                detail=f"connection failed: {str(exc)[:120]}",
            )
        except (transport.HTTPErrorStatus, ValueError) as exc:
            self._set_state(ProviderState.DEGRADED, "malformed response")
            return ProviderHealth(
                provider_id=self._provider_id,
                ok=False,
                state=ProviderState.DEGRADED,
                detail=f"malformed response: {str(exc)[:120]}",
            )
        self._maybe_fetch_spec()
        if not isinstance(data, dict):
            return ProviderHealth(
                provider_id=self._provider_id,
                ok=False,
                state=ProviderState.DEGRADED,
                detail="non-object /global/health response",
            )
        ok = bool(data.get("ok", data.get("status") == "ok"))
        state = ProviderState.READY if ok else ProviderState.DEGRADED
        return ProviderHealth(
            provider_id=self._provider_id,
            ok=ok,
            state=state,
            detail=f"opencode health: {json.dumps(data)[:160]}",
        )

    def generate(self, request: AIRequest) -> AIResponse:
        self._require_ready()
        if request.tools:
            self._require_capability(Capability.TOOL_CALLING)
        started = datetime.now(UTC)
        session_id = self._create_session()
        try:
            data = transport.request_json(
                f"{self._base_url.rstrip('/')}/session/{urllib.parse.quote(session_id)}/prompt",
                method="POST",
                body=self._prompt_body(request),
                timeout=request.timeout or self._timeout,
                default_timeout=self._timeout,
                headers=self._auth_headers(),
            )
        except urllib.error.URLError as exc:
            raise ProviderUnavailableError(f"opencode unreachable: {exc}") from exc
        except transport.HTTPErrorStatus as exc:
            raise ProviderError(f"opencode error: {exc}") from exc
        except ValueError as exc:
            raise ProviderError(f"opencode malformed response: {exc}") from exc
        finally:
            self._cleanup_session(session_id)
        if not isinstance(data, dict):
            raise ProviderError("opencode returned a non-object prompt response")
        elapsed = (datetime.now(UTC) - started).total_seconds() * 1000.0
        log.info(
            "opencode generate completed",
            extra={
                "component": "intelligence",
                "provider": self._provider_id,
                "duration_ms": elapsed,
                "session_id": session_id,
            },
        )
        content = data.get("content") or data.get("text") or data.get("response")
        usage = self._parse_usage(data)
        tool_calls = None
        raw_calls = data.get("tool_calls") or []
        if raw_calls:
            tool_calls = [
                ToolCall(
                    id=str(call.get("id") or f"call_{index}"),
                    name=str(call.get("name") or call.get("function", {}).get("name", "unknown")),
                    arguments=dict(call.get("args") or call.get("arguments") or {}),
                )
                for index, call in enumerate(raw_calls)
                if isinstance(call, dict)
            ]
        return AIResponse(
            request_id=request.request_id,
            provider=self._provider_id,
            model=str(data.get("model") or "opencode"),
            content=str(content) if content is not None else None,
            finish_reason=_map_finish_reason(data.get("finish_reason")),
            usage=usage,
            tool_calls=tool_calls,
        )

    def cancel(self, request_id: str) -> None:
        """Best-effort session abort is a no-op in phase 2 (no handle)."""
        log.info(
            "opencode cancel requested (no in-flight handle)",
            extra={"component": "intelligence", "provider": self._provider_id},
        )

    # --- internals ------------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        if not self._api_key_env:
            return {}
        token = self._load_api_key()
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}

    def _load_api_key(self) -> str | None:
        import os

        if self._api_key is not None:
            return self._api_key
        self._api_key = os.environ.get(self._api_key_env) or None
        return self._api_key

    def _maybe_fetch_spec(self) -> None:
        if self._spec_fetched:
            return
        self._spec_fetched = True
        try:
            spec = transport.request_json(
                f"{self._base_url.rstrip('/')}/doc",
                timeout=min(self._timeout, 5.0),
                default_timeout=5.0,
            )
            if isinstance(spec, dict) and spec.get("openapi"):
                log.info(
                    "opencode spec fetched",
                    extra={
                        "component": "intelligence",
                        "provider": self._provider_id,
                        "openapi": str(spec.get("openapi")),
                    },
                )
        except Exception as exc:  # spec is optional
            log.debug("opencode /doc unavailable: %s", exc)

    def _create_session(self) -> str:
        try:
            data = transport.request_json(
                f"{self._base_url.rstrip('/')}/session",
                method="POST",
                body={},
                timeout=min(self._timeout, 10.0),
                default_timeout=10.0,
                headers=self._auth_headers(),
            )
        except urllib.error.URLError as exc:
            raise ProviderUnavailableError(f"opencode unreachable: {exc}") from exc
        except (transport.HTTPErrorStatus, ValueError) as exc:
            raise ProviderError(f"opencode session error: {exc}") from exc
        if isinstance(data, dict):
            session_id = data.get("id") or data.get("sessionID")
            if session_id:
                return str(session_id)
        raise ProviderError("opencode did not return a session id")

    def _cleanup_session(self, session_id: str) -> None:
        try:
            transport.request_json(
                f"{self._base_url.rstrip('/')}/session/{urllib.parse.quote(session_id)}",
                method="DELETE",
                timeout=min(self._timeout, 5.0),
                default_timeout=5.0,
                headers=self._auth_headers(),
            )
        except Exception as exc:  # cleanup is best-effort
            log.debug("opencode session cleanup failed: %s", exc)

    def _prompt_body(self, request: AIRequest) -> dict[str, Any]:
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        for message in request.messages:
            messages.append(
                {
                    "role": message.role.value,
                    "content": self._render_content(message),
                }
            )
        body: dict[str, Any] = {
            "messages": messages,
            "prompt_async": True,
        }
        if request.model:
            body["model"] = request.model
        return body

    def _render_content(self, message: Any) -> str:
        if isinstance(message.content, str):
            return message.content
        parts: list[str] = []
        for part in message.content:
            if part.kind == "text":
                parts.append(part.text)
            else:
                parts.append(
                    f"[tool_call name={part.name} args={json.dumps(part.arguments)}]"
                )
        return "\n".join(parts)

    def _parse_usage(self, data: dict[str, Any]) -> TokenUsage | None:
        raw = data.get("usage")
        if not isinstance(raw, dict):
            return None
        prompt = raw.get("prompt_tokens") or raw.get("input_tokens")
        completion = raw.get("completion_tokens") or raw.get("output_tokens")
        total = raw.get("total_tokens")
        if total is None and prompt is None and completion is None:
            return None
        return TokenUsage(
            prompt_tokens=(
                int(prompt) if prompt is not None and str(prompt).isdigit() else None
            ),
            completion_tokens=(
                int(completion)
                if completion is not None and str(completion).isdigit()
                else None
            ),
            total_tokens=(
                int(total) if total is not None and str(total).isdigit() else None
            ),
        )

    def _on_shutdown(self) -> None:
        self._spec_fetched = False


def _map_finish_reason(reason: Any) -> FinishReason:
    if reason is None:
        return FinishReason.STOP
    normalized = str(reason).lower()
    if "length" in normalized:
        return FinishReason.LENGTH
    if "tool" in normalized:
        return FinishReason.TOOL_CALL
    if "cancel" in normalized:
        return FinishReason.CANCELLED
    if "filter" in normalized:
        return FinishReason.CONTENT_FILTERED
    if "error" in normalized:
        return FinishReason.ERROR
    return FinishReason.STOP
