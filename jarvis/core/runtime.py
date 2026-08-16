"""J.A.R.V.I.S. core runtime.

Coordinates startup and shutdown of the Phase 1 service set:

    load configuration → logging → registry/bus/storage/health →
    start services → emit RuntimeStarted event → RUNNING

Startup failures clean up already-initialized resources before re-raising;
shutdown is graceful and safe to repeat.
"""

from __future__ import annotations

import logging
from typing import Any

from jarvis.configuration.loader import load_config
from jarvis.configuration.model import JarvisConfig
from jarvis.core.health import HealthRegistry, HealthReport, HealthStatus
from jarvis.core.lifecycle import Lifecycle, RuntimeState
from jarvis.core.registry import ServiceRegistry
from jarvis.core.storage import StorageManager
from jarvis.events.bus import EventBus
from jarvis.events.models import RUNTIME_STARTED, RUNTIME_STOPPED, RUNTIME_STOPPING, Event
from jarvis.exceptions import LifecycleError
from jarvis.observability.logging import flush_logging, setup_logging

log = logging.getLogger("jarvis.core.runtime")


class Runtime:
    """The J.A.R.V.I.S. core runtime facade."""

    def __init__(self, config: JarvisConfig) -> None:
        self._config = config
        self._lifecycle = Lifecycle()
        self._registry: ServiceRegistry | None = None
        self._bus: EventBus | None = None
        self._storage: StorageManager | None = None
        self._health: HealthRegistry | None = None

    @classmethod
    def create(cls, config_path: str | None = None) -> Runtime:
        """Load validated configuration and create a Runtime (state CREATED)."""
        loaded = load_config(config_path)
        return cls(loaded.config)

    # --- accessors -----------------------------------------------------

    @property
    def config(self) -> JarvisConfig:
        return self._config

    @property
    def state(self) -> RuntimeState:
        return self._lifecycle.state

    @property
    def registry(self) -> ServiceRegistry:
        if self._registry is None:
            raise LifecycleError("service registry not initialized")
        return self._registry

    @property
    def bus(self) -> EventBus:
        if self._bus is None:
            raise LifecycleError("event bus not initialized")
        return self._bus

    @property
    def storage(self) -> StorageManager:
        if self._storage is None:
            raise LifecycleError("storage not initialized")
        return self._storage

    @property
    def health(self) -> HealthRegistry:
        if self._health is None:
            raise LifecycleError("health registry not initialized")
        return self._health

    # --- lifecycle -----------------------------------------------------

    async def start(self) -> None:
        """Initialize logging, services, storage; emit RuntimeStarted; RUNNING."""
        if self.state is not RuntimeState.CREATED:
            raise LifecycleError(f"cannot start runtime from state {self.state.value}")
        self._lifecycle.transition(RuntimeState.INITIALIZING)
        try:
            setup_logging(self._config.logging, self._config.core.logs_dir)

            registry = ServiceRegistry()
            bus = EventBus()
            storage = StorageManager(self._config.core)
            health = HealthRegistry()

            registry.register("service_registry", registry)
            registry.register("event_bus", bus)
            registry.register("storage", storage)
            registry.register("health", health)
            self._register_health_checks(health)

            self._registry = registry
            self._bus = bus
            self._storage = storage
            self._health = health

            storage.ensure_directories()

            registry.start_all()

            await bus.publish(
                Event(
                    type=RUNTIME_STARTED,
                    source="core.runtime",
                    payload={"version": "0.2.0", "config_source": "loaded"},
                )
            )
            self._lifecycle.transition(RuntimeState.RUNNING)
        except Exception as exc:
            await self._cleanup_after_failure()
            raise LifecycleError(f"runtime startup failed: {exc}") from exc

        log.info("runtime started", extra={"component": "core"})

    async def stop(self) -> None:
        """Graceful shutdown. Safe to call repeatedly and before start()."""
        if self.state in (RuntimeState.CREATED, RuntimeState.STOPPED):
            return
        if self.state not in (
            RuntimeState.INITIALIZING, RuntimeState.RUNNING, RuntimeState.STOPPING,
        ):
            return
        if self.state is not RuntimeState.STOPPING:
            self._lifecycle.transition(RuntimeState.STOPPING)

        bus = self._bus
        if self._registry is not None:
            self._registry.stop_all()

        if bus is not None and not bus.closed:
            try:
                await bus.publish(Event(type=RUNTIME_STOPPING, source="core.runtime"))
            except Exception as exc:
                log.error(
                    "failed to emit RuntimeStopping", exc_info=exc, extra={"component": "core"}
                )

            try:
                await bus.publish(Event(type=RUNTIME_STOPPED, source="core.runtime"))
            except Exception as exc:
                log.error(
                    "failed to emit RuntimeStopped", exc_info=exc, extra={"component": "core"}
                )

            await bus.close()

        flush_logging()
        self._lifecycle.transition(RuntimeState.STOPPED)
        log.info("runtime stopped", extra={"component": "core"})

    async def _cleanup_after_failure(self) -> None:
        try:
            if self.state is not RuntimeState.INITIALIZING:
                return
            self._lifecycle.transition(RuntimeState.STOPPING)
            if self._registry is not None:
                self._registry.stop_all()
            if self._bus is not None:
                await self._bus.close()
            flush_logging()
            self._lifecycle.transition(RuntimeState.STOPPED)
        except Exception as exc:  # cleanup must never mask the original error
            log.error(
                "cleanup after startup failure was incomplete",
                exc_info=exc,
                extra={"component": "core"},
            )

    # --- health --------------------------------------------------------

    def _register_health_checks(self, health: HealthRegistry) -> None:
        health.register("core", lambda: self._core_status(), "core runtime lifecycle")
        health.register(
            "configuration",
            lambda: HealthStatus.HEALTHY,
            "configuration loaded and validated",
        )
        health.register("event_bus", self._bus_status, "event bus accepting events")
        health.register(
            "service_registry", self._registry_status, "services registered and started"
        )
        health.register(
            "storage", self._storage_status, f"storage root: {self._config.core.data_dir}"
        )

    def _core_status(self) -> HealthStatus:
        if self.state is RuntimeState.RUNNING:
            return HealthStatus.HEALTHY
        if self.state in (RuntimeState.INITIALIZING, RuntimeState.STOPPING):
            return HealthStatus.DEGRADED
        return HealthStatus.UNHEALTHY

    def _bus_status(self) -> HealthStatus:
        if self._bus is not None and not self._bus.closed:
            return HealthStatus.HEALTHY
        if self._bus is not None:
            return HealthStatus.DEGRADED
        return HealthStatus.UNHEALTHY

    def _registry_status(self) -> HealthStatus:
        if self._registry is not None and self._registry.started:
            return HealthStatus.HEALTHY
        if self._registry is not None:
            return HealthStatus.DEGRADED
        return HealthStatus.UNHEALTHY

    def _storage_status(self) -> HealthStatus:
        if self._storage is None:
            return HealthStatus.UNHEALTHY
        return HealthStatus.HEALTHY if self._storage.probe_writable() else HealthStatus.UNHEALTHY

    def health_report(self) -> list[HealthReport]:
        return self.health.check_all()

    def overall_health(self) -> HealthStatus:
        return self.health.overall()

    # --- async context manager -----------------------------------------

    async def __aenter__(self) -> Runtime:
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.stop()
