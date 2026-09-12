"""Provider registry: registration, lookup, enumeration, lifecycle, health.

Duplicate provider IDs are rejected. Registry calls are synchronous and
fail-safe: an unhealthy provider is reported as such, never raised from
registry-level iteration.
"""

from __future__ import annotations

import logging
from typing import Any

from greatsage.exceptions import ServiceError
from greatsage.intelligence.provider import AIProvider, ProviderHealth, ProviderState

log = logging.getLogger("greatsage.intelligence.registry")


class ProviderRegistry:
    """Registry of AIProvider instances plus lifecycle/health bookkeeping."""

    def __init__(self) -> None:
        self._providers: dict[str, AIProvider] = {}

    # --- registration / lookup ------------------------------------------

    def register(self, provider: AIProvider) -> None:
        provider_id = provider.provider_id()
        if provider_id in self._providers:
            raise ServiceError(f"duplicate provider id: {provider_id}")
        self._providers[provider_id] = provider
        log.info("provider registered: %s", provider_id, extra={"component": "intelligence"})

    def get(self, provider_id: str) -> AIProvider:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise ServiceError(f"unknown provider: {provider_id}") from exc

    def has(self, provider_id: str) -> bool:
        return provider_id in self._providers

    def enumerate(self) -> tuple[AIProvider, ...]:
        return tuple(self._providers.values())

    def ids(self) -> tuple[str, ...]:
        return tuple(self._providers)

    def capabilities_for(self, provider_id: str) -> Any:
        return self.get(provider_id).capabilities()

    # --- health ----------------------------------------------------------

    def health(self, provider_id: str) -> ProviderHealth:
        return self.get(provider_id).health()

    def health_all(self) -> dict[str, ProviderHealth]:
        return {
            provider_id: self.get(provider_id).health()
            for provider_id in self.ids()
        }

    # --- lifecycle -------------------------------------------------------

    def initialize(self, provider_id: str) -> ProviderState:
        provider = self.get(provider_id)
        provider.init()
        return provider.state

    def initialize_all(self) -> dict[str, ProviderState]:
        return {provider_id: self.initialize(provider_id) for provider_id in self.ids()}

    def shutdown(self, provider_id: str) -> None:
        self.get(provider_id).shutdown()

    def shutdown_all(self) -> None:
        for provider in self._providers.values():
            provider.shutdown()
        log.info("all providers shut down", extra={"component": "intelligence"})

    # --- reporting -------------------------------------------------------

    def snapshot(self) -> dict[str, dict[str, Any]]:
        """Provider metadata without running health probes."""
        return {
            provider_id: {
                "class": type(provider).__name__,
                "state": provider.state.value,
                "detail": provider.detail,
                "capabilities": sorted(
                    capability.value for capability in provider.capabilities().capabilities
                ),
            }
            for provider_id, provider in self._providers.items()
        }
