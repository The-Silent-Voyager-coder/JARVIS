"""OpenCode provider adapter (remote code execution).

Connectivity/health via `/global/health`, session lifecycle via
`/session/*`, sync generation via `POST /session/:id/message`
(`{parts, model{providerID,modelID}, variant, system}` → `{info, parts}`),
async delegation via `POST /session/:id/prompt_async` (204) + `/event`
SSE, abort via `/session/:id/abort`. No authority delegation, no agent
loop — the provider merely routes model calls to an OpenCode server.

Model selectors look like `provider/model#variant`
(e.g. `opencode/muse-spark-1.3-contributor-free#xhigh`); a bare model id
resolves to the `opencode` provider namespace. Variants are server-side
effort presets — unknown variants produce a server error, never a
silent downgrade.

The OpenCode server surface is interrogated at init time through `/doc`
(OpenAPI 3.1); if the spec cannot be fetched, the adapter reports DEGRADED
but still attempts direct endpoint calls, which keeps the runtime functional.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from jarvis.delegation.models import DelegationEvent, DelegationEventKind
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
        model: str = "",
        timeout_seconds: float = 60.0,
        provider_id: str = "opencode",
    ) -> None:
        super().__init__(provider_id)
        self._base_url = base_url if base_url else OPENCODE_DEFAULT_URL
        self._api_key: str | None = None
        self._api_key_env = api_key_env
        self._default_model = model.strip()
        self._timeout = timeout_seconds if timeout_seconds > 0 else 60.0
        self._spec_fetched = False

    # --- public surface ------------------------------------------------

    def capabilities(self) -> ProviderCapabilities:
        caps = {
            Capability.TEXT_GENERATION,
            Capability.REMOTE,
            Capability.CANCELLATION,
            Capability.CODE_EXECUTION,
            Capability.DELEGATION,
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
        ok = bool(data.get("ok", data.get("healthy", data.get("status") == "ok")))
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
                f"{self._base_url.rstrip('/')}/session/{urllib.parse.quote(session_id)}/message",
                method="POST",
                body=self._message_body(request),
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
            raise ProviderError("opencode returned a non-object message response")
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
        parts = data.get("parts")
        part_list: list[Any] = parts if isinstance(parts, list) else []
        texts: list[str] = []
        for part in part_list:
            if not isinstance(part, dict):
                continue
            if part.get("type") != "text":
                continue
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text)
        content = "\n".join(texts) if texts else None
        raw_info: Any = data.get("info")
        info: dict[str, Any] = raw_info if isinstance(raw_info, dict) else {}
        usage = self._parse_usage(data) or self._parse_usage(info)
        tool_calls = None
        raw_calls = [
            part for part in part_list
            if isinstance(part, dict) and part.get("type") in ("tool", "tool_call", "function_call")
        ]
        if raw_calls:
            tool_calls = [
                ToolCall(
                    id=str(call.get("id") or call.get("callID") or f"call_{index}"),
                    name=_tool_call_name(call),
                    arguments=dict(
                        call.get("args") or call.get("arguments") or call.get("input") or {}
                    ),
                )
                for index, call in enumerate(raw_calls)
            ]
        model_echo = (
            request.model
            or self._default_model
            or (str(info.get("modelID")) if info.get("modelID") else None)
            or "opencode"
        )
        return AIResponse(
            request_id=request.request_id,
            provider=self._provider_id,
            model=model_echo,
            content=str(content) if content is not None else None,
            finish_reason=_map_finish_reason(
                data.get("finish_reason") or info.get("stopReason") or (tool_calls and "tool")
            ),
            usage=usage,
            tool_calls=tool_calls,
        )

    def cancel(self, request_id: str) -> None:
        """Best-effort session abort is a no-op in phase 2 (no handle)."""
        log.info(
            "opencode cancel requested (no in-flight handle)",
            extra={"component": "intelligence", "provider": self._provider_id},
        )

    # --- delegation surface (Phase 5B) --------------------------------

    def create_session(self) -> str:
        """Create a fresh OpenCode session and return its id."""
        return self._create_session()

    def send_delegation_prompt(
        self,
        session_id: str,
        prompt: str,
        working_directory: str | None = None,
    ) -> None:
        """Send the delegation prompt for asynchronous execution.

        `working_directory` has already passed JARVIS path security in the
        DelegationManager. The 1.18 message API carries no directory field,
        so scoping stays a JARVIS-side permission decision (every executor
        file/shell action is allow/ask/deny gated); it is not forwarded.
        """
        body: dict[str, Any] = {"parts": [{"type": "text", "text": prompt}]}
        try:
            transport.request_json(
                f"{self._base_url.rstrip('/')}/session/"
                f"{urllib.parse.quote(session_id)}/prompt_async",
                method="POST",
                body=body,
                timeout=min(self._timeout, 10.0),
                default_timeout=10.0,
                headers=self._auth_headers(),
            )
        except urllib.error.URLError as exc:
            raise ProviderUnavailableError(f"opencode unreachable: {exc}") from exc
        except transport.HTTPErrorStatus as exc:
            raise ProviderError(f"opencode prompt error: {exc}") from exc
        except ValueError as exc:
            raise ProviderError(f"opencode malformed prompt response: {exc}") from exc

    def iter_session_events(self, session_id: str) -> Iterator[DelegationEvent]:
        """Stream normalized session events (SSE) for a delegated session.

        Wire-format translation happens here and only here: raw OpenCode
        event names/payloads are mapped to provider-neutral DelegationEvent
        kinds. Malformed or unknown events degrade to NOTE, never crash.
        """
        url = (
            f"{self._base_url.rstrip('/')}/session/"
            f"{urllib.parse.quote(session_id)}/event"
        )
        try:
            stream = transport.iter_sse(
                url,
                headers=self._auth_headers(),
                timeout=self._timeout,
                default_timeout=self._timeout,
            )
            for name, data in stream:
                event = self._translate_sse(session_id, name, data)
                if event is not None:
                    yield event
        except urllib.error.URLError as exc:
            raise ProviderUnavailableError(f"opencode event stream unreachable: {exc}") from exc
        except transport.HTTPErrorStatus as exc:
            raise ProviderError(f"opencode event stream error: {exc}") from exc

    def respond_permission(
        self,
        session_id: str,
        permission_id: str,
        approved: bool,
        remember: bool | None = None,
    ) -> None:
        """Answer one permission request with the JARVIS decision."""
        body: dict[str, Any] = {"response": approved}
        if remember is not None:
            body["remember"] = remember
        try:
            transport.request_json(
                f"{self._base_url.rstrip('/')}/session/"
                f"{urllib.parse.quote(session_id)}/permissions/"
                f"{urllib.parse.quote(permission_id)}",
                method="POST",
                body=body,
                timeout=min(self._timeout, 10.0),
                default_timeout=10.0,
                headers=self._auth_headers(),
            )
        except urllib.error.URLError as exc:
            raise ProviderUnavailableError(f"opencode unreachable: {exc}") from exc
        except transport.HTTPErrorStatus as exc:
            raise ProviderError(f"opencode permission error: {exc}") from exc
        except ValueError as exc:
            raise ProviderError(f"opencode malformed permission response: {exc}") from exc

    def abort_session(self, session_id: str) -> None:
        """Abort a delegated session (best-effort; never raises)."""
        try:
            transport.request_json(
                f"{self._base_url.rstrip('/')}/session/"
                f"{urllib.parse.quote(session_id)}/abort",
                method="POST",
                body={},
                timeout=min(self._timeout, 10.0),
                default_timeout=10.0,
                headers=self._auth_headers(),
            )
        except Exception as exc:  # abort is best-effort
            log.debug("opencode session abort failed: %s", exc)

    def get_session_diff(self, session_id: str) -> dict[str, Any] | None:
        """Fetch the file-change diff of a completed session (best-effort)."""
        try:
            data = transport.request_json(
                f"{self._base_url.rstrip('/')}/session/"
                f"{urllib.parse.quote(session_id)}/diff",
                timeout=min(self._timeout, 10.0),
                default_timeout=10.0,
                headers=self._auth_headers(),
            )
        except Exception as exc:  # diff is best-effort review material
            log.debug("opencode session diff unavailable: %s", exc)
            return None
        return data if isinstance(data, dict) else None

    def dispose_session(self, session_id: str) -> None:
        """Release a delegated session (best-effort)."""
        self._cleanup_session(session_id)

    # --- internals ------------------------------------------------------

    def _translate_sse(
        self, session_id: str, name: str, data: str
    ) -> DelegationEvent | None:
        try:
            raw = json.loads(data) if data.strip() else {}
        except ValueError:
            log.debug("opencode malformed SSE event skipped: %s", name)
            return None
        if not isinstance(raw, dict):
            return DelegationEvent(
                kind=DelegationEventKind.NOTE,
                session_id=session_id,
                message=None,
                metadata={"event": name[:120]},
            )
        inner: dict[str, Any] = {}
        if isinstance(raw.get("properties"), dict):
            inner = raw["properties"]
        else:
            inner = raw
        lowered = name.lower()
        if _contains_permission(inner, name):
            return self._permission_event(session_id, name, inner)
        if "error" in lowered or inner.get("error"):
            return DelegationEvent(
                kind=DelegationEventKind.FAILED,
                session_id=session_id,
                message=_string(inner.get("error")) or _string(inner.get("message")),
                metadata={"event": name[:120]},
            )
        if "cancel" in lowered or inner.get("cancelled") is True:
            return DelegationEvent(
                kind=DelegationEventKind.CANCELLED,
                session_id=session_id,
                message=None,
                metadata={"event": name[:120]},
            )
        if (
            lowered.endswith(".completed")
            or lowered.endswith(".done")
            or inner.get("status") == "completed"
            or inner.get("completed") is True
        ):
            return DelegationEvent(
                kind=DelegationEventKind.COMPLETED,
                session_id=session_id,
                message=_string(inner.get("summary"))
                or _string(inner.get("text"))
                or _string(inner.get("content")),
                metadata={"event": name[:120]},
            )
        text = _string(inner.get("text")) or _string(inner.get("content"))
        return DelegationEvent(
            kind=DelegationEventKind.PROGRESS,
            session_id=session_id,
            message=text[:400] if text else None,
            metadata={"event": name[:120]},
        )

    def _permission_event(
        self, session_id: str, name: str, inner: dict[str, Any]
    ) -> DelegationEvent:
        block = inner.get("key")
        if isinstance(block, dict) and isinstance(block.get("permissions"), dict):
            block = block["permissions"]
        permission_id = (
            _string(inner.get("permissionID"))
            or _string(inner.get("permission_id"))
            or _string(inner.get("permissionId"))
            or name[:120]
        )
        path = _string(block.get("path")) if isinstance(block, dict) else None
        action = (
            _string(block.get("action")) if isinstance(block, dict) else None
        ) or _string(inner.get("action")) or "unknown"
        description = (
            _string(block.get("description")) if isinstance(block, dict) else None
        ) or _string(inner.get("description"))
        return DelegationEvent(
            kind=DelegationEventKind.PERMISSION_REQUESTED,
            session_id=session_id,
            message=description,
            metadata={
                "permission_id": permission_id,
                "action": action,
                "path": path or "",
            },
        )

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

    @staticmethod
    def _split_model(model: str | None) -> tuple[dict[str, str] | None, str | None]:
        """Split `provider/model#variant` into ({providerID, modelID}, variant).

        A bare model id resolves to the `opencode` provider namespace; an
        empty model means "server default" (no model key is sent).
        """
        if not model or not model.strip():
            return None, None
        rest, _, variant = model.strip().partition("#")
        if "/" in rest:
            provider, _, model_id = rest.partition("/")
        else:
            provider, model_id = "opencode", rest
        if not model_id.strip():
            return None, variant.strip() or None
        return (
            {"providerID": provider.strip(), "modelID": model_id.strip()},
            variant.strip() or None,
        )

    def _message_body(self, request: AIRequest) -> dict[str, Any]:
        utterances = [
            (message.role.value, self._render_content(message))
            for message in request.messages
            if message.role.value != "system"
        ]
        if len(utterances) == 1 and not request.system_prompt:
            text = utterances[0][1]
        else:
            lines = []
            if request.system_prompt:
                lines.append(f"system: {request.system_prompt}")
            lines.extend(f"{role}: {content}" for role, content in utterances)
            text = "\n".join(lines)
        body: dict[str, Any] = {"parts": [{"type": "text", "text": text}]}
        if request.system_prompt:
            body["system"] = request.system_prompt
        model, variant = self._split_model(request.model or self._default_model or None)
        if model:
            body["model"] = model
        if variant:
            body["variant"] = variant
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


def _tool_call_name(call: dict[str, Any]) -> str:
    """Best-effort tool name across part shapes (unknown -> "unknown")."""
    nested = call.get("function")
    nested_name = nested.get("name") if isinstance(nested, dict) else None
    return str(call.get("name") or call.get("tool") or nested_name or "unknown")


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


def _contains_permission(inner: dict[str, Any], name: str) -> bool:
    if "permission" in name.lower():
        return True
    if "permissionID" in inner or "permission_id" in inner or "permissionId" in inner:
        return True
    block = inner.get("key")
    if isinstance(block, dict) and isinstance(block.get("permissions"), dict):
        return True
    return False


def _string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
