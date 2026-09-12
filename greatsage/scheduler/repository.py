"""Scheduler repository abstraction (roadmap Phase C)."""

from __future__ import annotations

import abc
from dataclasses import dataclass

from greatsage.scheduler.models import Schedule


@dataclass(frozen=True)
class SchedulerHealth:
    accessible: bool
    schema_valid: bool
    migrations_current: bool
    writable: bool
    schema_version: int
    detail: str
    database_path: str


class SchedulerRepository(abc.ABC):
    """Abstract persistence for schedules."""

    @abc.abstractmethod
    def initialize(self) -> None: ...

    @abc.abstractmethod
    def close(self) -> None: ...

    @abc.abstractmethod
    def save(self, schedule: Schedule) -> None: ...

    @abc.abstractmethod
    def get(self, schedule_id: str) -> Schedule | None: ...

    @abc.abstractmethod
    def remove(self, schedule_id: str) -> bool: ...

    @abc.abstractmethod
    def list(self) -> list[Schedule]: ...

    @abc.abstractmethod
    def count(self) -> int: ...

    @abc.abstractmethod
    def health(self) -> SchedulerHealth: ...
