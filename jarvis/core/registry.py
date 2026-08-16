"""Minimal service registry with dependency-ordered lifecycle.

Deliberately simple (Phase 1 contract): register, resolve, duplicate
detection, missing-service errors, and start/stop in dependency order.
Not a dependency-injection framework.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from jarvis.exceptions import ServiceError

log = logging.getLogger("jarvis.core.registry")


@dataclass(frozen=True)
class ServiceRecord:
    name: str
    service: Any
    dependencies: tuple[str, ...] = ()


@dataclass
class ServiceRegistry:
    """Register named services and start/stop them in dependency order.

    Lifecycle hooks: a service object may expose `start()` and/or `stop()`
    (sync or async); the registry calls them if present.
    """

    _records: dict[str, ServiceRecord] = field(default_factory=dict)
    _started: bool = False

    def register(self, name: str, service: Any, dependencies: tuple[str, ...] = ()) -> None:
        if name in self._records:
            raise ServiceError(f"service already registered: {name}")
        self._records[name] = ServiceRecord(name=name, service=service, dependencies=dependencies)

    def get(self, name: str) -> Any:
        record = self._records.get(name)
        if record is None:
            raise ServiceError(f"unknown service: {name}")
        return record.service

    def has(self, name: str) -> bool:
        return name in self._records

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._records))

    @property
    def started(self) -> bool:
        return self._started

    # --- lifecycle -----------------------------------------------------

    def _order(self) -> list[str]:
        """Topological order by declared dependencies; raises on cycles/missing deps."""
        remaining = dict(self._records)
        ordered: list[str] = []
        while remaining:
            progressed = False
            for name in sorted(remaining):
                record = remaining[name]
                unmet = [dep for dep in record.dependencies if dep in remaining]
                missing = [dep for dep in record.dependencies if dep not in self._records]
                if missing:
                    raise ServiceError(f"service '{name}' depends on unknown service: {missing[0]}")
                if not unmet:
                    ordered.append(name)
                    del remaining[name]
                    progressed = True
            if not progressed:
                cycle = sorted(remaining)
                raise ServiceError(f"service dependency cycle detected among: {cycle}")
        return ordered

    def start_all(self) -> None:
        ordered = self._order()
        started: list[str] = []
        try:
            for name in ordered:
                service = self._records[name].service
                starter = getattr(service, "start", None)
                if starter is not None:
                    starter()
                started.append(name)
        except Exception as exc:
            self._stop_reverse(started)
            failing = started[-1] if started else "?"
            raise ServiceError(f"failed to start service '{failing}': {exc}") from exc
        self._started = True

    def stop_all(self) -> None:
        self._started = False
        self._stop_reverse(list(self._records))

    def _stop_reverse(self, names: list[str]) -> None:
        for name in reversed(names):
            record = self._records[name]
            stopper: Callable[[], Any] | None = getattr(record.service, "stop", None)
            if stopper is None:
                continue
            try:
                stopper()
            except Exception as exc:
                log.error(
                    f"error stopping service '{name}'",
                    exc_info=exc,
                    extra={"component": "registry"},
                )
