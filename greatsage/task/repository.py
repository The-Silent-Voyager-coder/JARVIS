"""Task repository abstraction (Phase 6)."""

from __future__ import annotations

import abc
from dataclasses import dataclass

from greatsage.task.models import StepResult, TaskRecord


@dataclass(frozen=True)
class TaskHealth:
    accessible: bool
    schema_valid: bool
    migrations_current: bool
    writable: bool
    schema_version: int
    detail: str
    database_path: str


class TaskRepository(abc.ABC):
    @abc.abstractmethod
    def initialize(self) -> None: ...

    @abc.abstractmethod
    def close(self) -> None: ...

    @abc.abstractmethod
    def create_task(self, record: TaskRecord) -> None: ...

    @abc.abstractmethod
    def get_task(self, task_id: str) -> TaskRecord | None: ...

    @abc.abstractmethod
    def update_task(self, record: TaskRecord) -> None: ...

    @abc.abstractmethod
    def list_tasks(self) -> list[TaskRecord]: ...

    @abc.abstractmethod
    def save_step_result(self, task_id: str, result: StepResult) -> None: ...

    @abc.abstractmethod
    def get_step_results(self, task_id: str) -> list[StepResult]: ...

    @abc.abstractmethod
    def health(self) -> TaskHealth: ...
