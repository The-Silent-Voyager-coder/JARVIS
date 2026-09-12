"""Service registry tests: registration, retrieval, duplicates, lifecycle."""

from __future__ import annotations

import pytest

from greatsage.core.registry import ServiceRegistry
from greatsage.exceptions import ServiceError


class StartStopService:
    def __init__(self, log: list[str], name: str) -> None:
        self.log = log
        self.name = name

    def start(self) -> None:
        self.log.append(f"start:{self.name}")

    def stop(self) -> None:
        self.log.append(f"stop:{self.name}")


class BadStartService:
    def start(self) -> None:
        raise RuntimeError("cannot start")


def test_register_get_roundtrip() -> None:
    registry = ServiceRegistry()
    bus = object()
    registry.register("event_bus", bus)
    assert registry.get("event_bus") is bus
    assert registry.has("event_bus")
    assert not registry.has("other")


def test_duplicate_registration_detected() -> None:
    registry = ServiceRegistry()
    registry.register("event_bus", object())
    with pytest.raises(ServiceError, match="already registered"):
        registry.register("event_bus", object())


def test_missing_service_raises() -> None:
    registry = ServiceRegistry()
    with pytest.raises(ServiceError, match="unknown service"):
        registry.get("nope")


def test_names_sorted() -> None:
    registry = ServiceRegistry()
    registry.register("zebra", object())
    registry.register("apple", object())
    assert registry.names == ("apple", "zebra")


def test_start_all_in_dependency_order() -> None:
    registry = ServiceRegistry()
    order: list[str] = []
    registry.register("resources", StartStopService(order, "resources"))
    registry.register("tasks", StartStopService(order, "tasks"), dependencies=("resources",))
    registry.start_all()
    assert order == ["start:resources", "start:tasks"]
    assert registry.started
    assert order == ["start:resources", "start:tasks"]


def test_stop_all_reverse_order() -> None:
    registry = ServiceRegistry()
    order: list[str] = []
    registry.register("resources", StartStopService(order, "resources"))
    registry.register("tasks", StartStopService(order, "tasks"), dependencies=("resources",))
    registry.start_all()
    registry.stop_all()
    assert order == ["start:resources", "start:tasks", "stop:tasks", "stop:resources"]
    assert not registry.started


def test_start_failure_stops_started_services() -> None:
    registry = ServiceRegistry()
    order: list[str] = []
    registry.register("resources", StartStopService(order, "resources"))
    registry.register("bad", BadStartService(), dependencies=("resources",))
    with pytest.raises(ServiceError, match="failed to start service"):
        registry.start_all()
    assert order == ["start:resources", "stop:resources"]


def test_unknown_dependency_rejected() -> None:
    registry = ServiceRegistry()
    registry.register("tasks", object(), dependencies=("ghost",))
    with pytest.raises(ServiceError, match="unknown service"):
        registry.start_all()


def test_cycle_detected() -> None:
    registry = ServiceRegistry()
    registry.register("a", object(), dependencies=("b",))
    registry.register("b", object(), dependencies=("a",))
    with pytest.raises(ServiceError, match="cycle"):
        registry.start_all()


def test_missing_dependency_rejected() -> None:
    registry = ServiceRegistry()
    registry.register("a", object(), dependencies=("missing_service",))
    with pytest.raises(ServiceError, match="unknown service"):
        registry.start_all()
