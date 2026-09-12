"""Workspace repository abstraction (Phase 6)."""

from __future__ import annotations

import abc
from dataclasses import dataclass
from pathlib import Path

from greatsage.workspace.models import WorkspaceInfo


@dataclass(frozen=True)
class WorkspaceHealth:
    accessible: bool
    schema_valid: bool
    migrations_current: bool
    writable: bool
    schema_version: int
    detail: str
    database_path: str


class WorkspaceRepository(abc.ABC):
    """Abstract persistence for workspace scans."""

    @abc.abstractmethod
    def initialize(self) -> None: ...

    @abc.abstractmethod
    def close(self) -> None: ...

    @abc.abstractmethod
    def save(self, info: WorkspaceInfo) -> None: ...

    @abc.abstractmethod
    def get(self, workspace_id: str) -> WorkspaceInfo | None: ...

    @abc.abstractmethod
    def get_by_root(self, root: Path) -> WorkspaceInfo | None: ...

    @abc.abstractmethod
    def list(self) -> list[WorkspaceInfo]: ...

    @abc.abstractmethod
    def health(self) -> WorkspaceHealth: ...
