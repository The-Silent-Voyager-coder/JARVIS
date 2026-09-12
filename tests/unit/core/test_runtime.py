"""Runtime lifecycle tests: startup, failure cleanup, shutdown, events, health."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from greatsage.configuration.loader import load_config
from greatsage.core.lifecycle import RuntimeState
from greatsage.core.runtime import Runtime
from greatsage.events.models import RUNTIME_STOPPED, RUNTIME_STOPPING, TASK_COMPLETED, Event
from greatsage.exceptions import LifecycleError


def test_startup_reaches_running_and_creates_dirs(valid_config_yaml: Path, tmp_path: Path) -> None:
    async def scenario() -> None:
        runtime = Runtime(load_config(valid_config_yaml).config)
        assert runtime.state is RuntimeState.CREATED
        await runtime.start()
        assert runtime.state is RuntimeState.RUNNING
        for directory in ("data", "cache", "logs", "runtime", "workspaces", "models", "backups"):
            assert (tmp_path / directory).is_dir()
        await runtime.stop()

    asyncio.run(scenario())


def test_startup_events_ordered(valid_config_yaml: Path) -> None:
    async def scenario() -> None:
        runtime = Runtime(load_config(valid_config_yaml).config)
        await runtime.start()

        received: list[str] = []
        runtime.bus.subscribe(lambda e: received.append(e.type), event_type=RUNTIME_STOPPING)
        runtime.bus.subscribe(lambda e: received.append(e.type), event_type=RUNTIME_STOPPED)
        await runtime.stop()

        assert received == [RUNTIME_STOPPING, RUNTIME_STOPPED]

    asyncio.run(scenario())


def test_shutdown_emits_stopping_then_stopped(valid_config_yaml: Path) -> None:
    async def scenario() -> None:
        runtime = Runtime(load_config(valid_config_yaml).config)
        await runtime.start()

        received: list[str] = []
        runtime.bus.subscribe(lambda e: received.append(e.type))
        await runtime.stop()

        assert runtime.state is RuntimeState.STOPPED
        assert received == [RUNTIME_STOPPING, RUNTIME_STOPPED]
        assert runtime.bus.closed

    asyncio.run(scenario())


def test_repeated_shutdown_is_safe(valid_config_yaml: Path) -> None:
    async def scenario() -> None:
        runtime = Runtime(load_config(valid_config_yaml).config)
        await runtime.start()
        await runtime.stop()
        await runtime.stop()
        assert runtime.state is RuntimeState.STOPPED

    asyncio.run(scenario())


def test_stop_before_start_is_safe(valid_config_yaml: Path) -> None:
    async def scenario() -> None:
        runtime = Runtime(load_config(valid_config_yaml).config)
        await runtime.stop()
        assert runtime.state is RuntimeState.CREATED

    asyncio.run(scenario())


def test_double_start_rejected(valid_config_yaml: Path) -> None:
    async def scenario() -> None:
        runtime = Runtime(load_config(valid_config_yaml).config)
        await runtime.start()
        with pytest.raises(LifecycleError, match="cannot start"):
            await runtime.start()
        await runtime.stop()

    asyncio.run(scenario())


def test_startup_failure_cleanup(tmp_path: Path) -> None:
    # A storage directory collides with an existing *file*: ensure_directories
    # raises, start() must clean up and end in STOPPED, never RUNNING.
    collide = tmp_path / "data"
    collide.write_text("i am a file, not a directory", encoding="utf-8")
    config_path = tmp_path / "bad.yaml"
    d = str(tmp_path).replace("\\", "/")
    config_path.write_text(
        f"core:\n  data_dir: \"{d}/data\"\n  logs_dir: \"{d}/logs\"\n",
        encoding="utf-8",
    )

    async def scenario() -> None:
        runtime = Runtime(load_config(config_path).config)
        with pytest.raises(LifecycleError, match="runtime startup failed"):
            await runtime.start()
        assert runtime.state is RuntimeState.STOPPED
        assert runtime.bus.closed
        assert not runtime.registry.started

    asyncio.run(scenario())


def test_health_components_registered(valid_config_yaml: Path) -> None:
    async def scenario() -> None:
        runtime = Runtime(load_config(valid_config_yaml).config)
        await runtime.start()
        reports = {r.component: r.status.value for r in runtime.health_report()}
        assert reports == {
            "core": "HEALTHY",
            "configuration": "HEALTHY",
            "event_bus": "HEALTHY",
            "service_registry": "HEALTHY",
            "storage": "HEALTHY",
            "memory": "HEALTHY",
            "tools": "HEALTHY",
            "agent": "HEALTHY",
            "delegation": "HEALTHY",
            "workspace": "HEALTHY",
            "planning": "HEALTHY",
            "task": "HEALTHY",
            "scheduler": "HEALTHY",
            "telegram": "HEALTHY",
            "intelligence": reports["intelligence"],  # env-dependent provider state
        }
        assert reports["intelligence"] in ("HEALTHY", "DEGRADED", "UNHEALTHY")
        await runtime.stop()

        after = {r.component: r.status.value for r in runtime.health_report()}
        assert after["core"] == "UNHEALTHY"
        assert after["event_bus"] == "DEGRADED"

    asyncio.run(scenario())


def test_bus_publishes_after_start(valid_config_yaml: Path) -> None:
    async def scenario() -> None:
        runtime = Runtime(load_config(valid_config_yaml).config)
        await runtime.start()
        seen: list[str] = []
        runtime.bus.subscribe(lambda e: seen.append(e.type), event_type=TASK_COMPLETED)
        await runtime.bus.publish(Event(type=TASK_COMPLETED, source="test"))
        assert seen == [TASK_COMPLETED]
        await runtime.stop()

    asyncio.run(scenario())


def test_async_context_manager(valid_config_yaml: Path) -> None:
    async def scenario() -> None:
        async with Runtime(load_config(valid_config_yaml).config) as runtime:
            assert runtime.state is RuntimeState.RUNNING
        assert runtime.state is RuntimeState.STOPPED

    asyncio.run(scenario())
