"""Deterministic provider router.

Pipeline: AIRequest -> capability filter -> availability filter -> routing
policy -> selected provider. Rules are deterministic and ordered:

1. explicit provider request (request metadata "provider" hint, or the
   configured default provider) -> use it; if unavailable -> error, never
   fall back.
2. capability filter: drop providers that lack required capabilities
   (streaming if requested, tool calling if tools declared, code execution
   for CODING task kind).
3. availability filter: drop providers not in READY state.
4. coding tasks prefer the OpenCode provider (remote code execution) when
   capable and available; otherwise prefer a local-only provider.
5. fallback: first capable provider; still nothing -> RoutingError listing
   the available alternatives.

Every route records the requested / selected provider, reason, and the
alternatives it saw (observability contract, docs/INTERFACES.md).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from jarvis.exceptions import RoutingError
from jarvis.intelligence.models import AIRequest, TaskKind
from jarvis.intelligence.provider import AIProvider, Capability, ProviderState
from jarvis.intelligence.registry import ProviderRegistry

log = logging.getLogger("jarvis.intelligence.router")


@dataclass(frozen=True)
class Route:
    request_id: str
    requested_provider: str | None
    selected_provider: str | None
    reason: str
    alternatives: tuple[str, ...] = ()
    model: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "requested_provider": self.requested_provider,
            "selected_provider": self.selected_provider,
            "reason": self.reason,
            "alternatives": list(self.alternatives),
            "model": self.model,
        }


class Router:
    """Routes AI requests to a provider using deterministic policy."""

    def __init__(
        self,
        registry: ProviderRegistry,
        *,
        default_provider: str | None = None,
    ) -> None:
        self._registry = registry
        self._default_provider = default_provider

    # --- public --------------------------------------------------------

    def route(self, request: AIRequest) -> Route:
        requested = self._requested_provider(request)
        candidates = self._available_providers(request)
        alternatives = tuple(provider.provider_id() for provider in candidates)

        if requested is not None:
            provider = self._resolve(requested)
            if provider is None:
                raise RoutingError(
                    f"requested provider '{requested}' is not registered"
                    f" (available: {', '.join(self._registry.ids()) or 'none'})"
                )
            if provider.state is not ProviderState.READY:
                raise RoutingError(
                    f"requested provider '{requested}' is {provider.state.value}; "
                    "explicit selection does not fall back"
                )
            selected: AIProvider | None = provider
            reason = f"explicit selection: {requested}"
        else:
            selected, reason = self._policy_select(candidates)

        if selected is None:
            registered = self._registry.ids()
            registered_txt = ", ".join(registered) if registered else "(none registered)"
            raise RoutingError(
                "no provider available for this request"
                f" (registered: {registered_txt}; candidates after filters: {len(candidates)})"
            )
        route = Route(
            request_id=request.request_id,
            requested_provider=requested,
            selected_provider=selected.provider_id(),
            reason=reason,
            alternatives=alternatives,
            model=request.model,
        )
        log.info(
            "route selected: %s",
            route.selected_provider,
            extra={
                "component": "intelligence",
                "request_id": request.request_id,
                **route.to_dict(),
            },
        )
        return route

    def _requested_provider(self, request: AIRequest) -> str | None:
        metadata_hint = request.metadata.get("provider")
        if isinstance(metadata_hint, str) and metadata_hint:
            return metadata_hint
        return self._default_provider

    # --- pipelining ----------------------------------------------------

    def _available_providers(self, request: AIRequest) -> list[AIProvider]:
        required = self._required_capabilities(request)
        providers: list[AIProvider] = []
        for provider in self._registry.enumerate():
            if provider.state is not ProviderState.READY:
                continue
            caps = provider.capabilities()
            if not caps.all_supports(required):
                continue
            if request.model and caps.model_ids and request.model not in caps.model_ids:
                continue
            providers.append(provider)
        return providers

    def _required_capabilities(self, request: AIRequest) -> frozenset[Capability]:
        required: set[Capability] = {Capability.TEXT_GENERATION}
        task_kind = request.metadata.get("task_kind")
        if task_kind == TaskKind.CODING.value:
            required.add(Capability.CODE_EXECUTION)
        if request.metadata.get("require_streaming") is True:
            required.add(Capability.STREAMING)
        if request.tools:
            required.add(Capability.TOOL_CALLING)
        return frozenset(required)

    def _policy_select(
        self, candidates: list[AIProvider]
    ) -> tuple[AIProvider | None, str]:
        if not candidates:
            return None, "no capable provider in READY state"
        for provider in candidates:
            if Capability.CODE_EXECUTION in provider.capabilities().capabilities:
                return provider, "policy: coding task prefers remote code execution"
        for provider in candidates:
            caps = provider.capabilities()
            if caps.supports(Capability.LOCAL) and not caps.supports(Capability.REMOTE):
                return provider, "policy: local provider preferred"
        return candidates[0], "policy: first capable provider"

    # --- internals -----------------------------------------------------

    def _resolve(self, provider_id: str) -> AIProvider | None:
        if self._registry.has(provider_id):
            return self._registry.get(provider_id)
        return None
