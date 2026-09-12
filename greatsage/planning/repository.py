"""Planning repository abstraction (Phase 6)."""

from __future__ import annotations

import abc
from dataclasses import dataclass

from greatsage.planning.models import Plan


@dataclass(frozen=True)
class PlanningHealth:
    accessible: bool
    schema_valid: bool
    migrations_current: bool
    writable: bool
    schema_version: int
    detail: str
    database_path: str


class PlanningRepository(abc.ABC):
    @abc.abstractmethod
    def initialize(self) -> None: ...

    @abc.abstractmethod
    def close(self) -> None: ...

    @abc.abstractmethod
    def save(self, plan: Plan) -> None: ...

    @abc.abstractmethod
    def get(self, plan_id: str) -> Plan | None: ...

    @abc.abstractmethod
    def list(self) -> list[Plan]: ...

    @abc.abstractmethod
    def health(self) -> PlanningHealth: ...
