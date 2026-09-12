"""Provider registry tests: registration, duplicate rejection, lookup,
enumeration, lifecycle, health isolation."""

from __future__ import annotations

import pytest

from greatsage.exceptions import ServiceError
from greatsage.intelligence.mock import MockProvider
from greatsage.intelligence.provider import ProviderState
from greatsage.intelligence.registry import ProviderRegistry


@pytest.fixture
def registry() -> ProviderRegistry:
    return ProviderRegistry()


def test_register_and_get(registry: ProviderRegistry) -> None:
    provider = MockProvider("alpha")
    registry.register(provider)
    assert registry.get("alpha") is provider
    assert registry.has("alpha")
    assert not registry.has("beta")


def test_duplicate_rejected(registry: ProviderRegistry) -> None:
    registry.register(MockProvider("alpha"))
    with pytest.raises(ServiceError, match="duplicate provider id"):
        registry.register(MockProvider("alpha"))


def test_get_unknown_raises(registry: ProviderRegistry) -> None:
    with pytest.raises(ServiceError, match="unknown provider"):
        registry.get("nope")


def test_enumerate_and_ids(registry: ProviderRegistry) -> None:
    registry.register(MockProvider("a"))
    registry.register(MockProvider("b"))
    assert set(registry.ids()) == {"a", "b"}
    assert {p.provider_id() for p in registry.enumerate()} == {"a", "b"}


def test_initialize_ready(registry: ProviderRegistry) -> None:
    registry.register(MockProvider("healthy"))
    state = registry.initialize("healthy")
    assert state is ProviderState.READY
    assert registry.health("healthy").ok


def test_initialize_degraded_provider(registry: ProviderRegistry) -> None:
    registry.register(MockProvider("flaky", fail_on_generate=True))
    state = registry.initialize("flaky")
    assert state in (ProviderState.DEGRADED, ProviderState.UNAVAILABLE, ProviderState.READY)
    assert registry.health("flaky").ok is False


def test_initialize_all_and_shutdown(registry: ProviderRegistry) -> None:
    registry.register(MockProvider("a"))
    registry.register(MockProvider("b"))
    states = registry.initialize_all()
    assert all(state is ProviderState.READY for state in states.values())
    registry.shutdown_all()
    assert registry.get("a").state is ProviderState.STOPPED
    assert registry.get("b").state is ProviderState.STOPPED
    assert registry.health("a").ok is False


def test_health_all(registry: ProviderRegistry) -> None:
    registry.register(MockProvider("a"))
    registry.register(MockProvider("b"))
    registry.initialize_all()
    health = registry.health_all()
    assert set(health) == {"a", "b"}
    assert health["a"].ok
    assert health["a"].latency_ms is not None and health["a"].latency_ms >= 0


def test_snapshot_metadata(registry: ProviderRegistry) -> None:
    registry.register(MockProvider("a", capabilities={}))
    snapshot = registry.snapshot()
    assert "a" in snapshot
    assert snapshot["a"]["state"] == "ready"
    assert "text_generation" in snapshot["a"]["capabilities"]


def test_failing_provider_does_not_break_registry(registry: ProviderRegistry) -> None:
    registry.register(MockProvider("broken", fail_on_generate=True))
    registry.register(MockProvider("good"))
    registry.initialize_all()
    health = registry.health_all()
    assert health["broken"].ok is False
    assert health["good"].ok is True
