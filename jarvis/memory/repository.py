"""Memory repository abstraction.

The core memory API (service) depends on this interface, never on SQL.
Concrete persistence (SQLite in Phase 3) must implement it behind the same
contract so storage can be swapped without touching business rules.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from jarvis.memory.models import Memory, MemoryFilter

# Aliases so the `list`/`search` method names below do not shadow the builtin
# `list` inside their own class-scope annotations (mypy valid-type).
MemoryList = list[Memory]
MemoryIdList = list[str]


@dataclass(frozen=True)
class RepositoryHealth:
    """Diagnostics for one memory database (docs/MEMORY.md §health)."""

    accessible: bool
    schema_valid: bool
    migrations_current: bool
    writable: bool
    fts_enabled: bool
    schema_version: int
    detail: str = ""
    database_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "accessible": self.accessible,
            "schema_valid": self.schema_valid,
            "migrations_current": self.migrations_current,
            "writable": self.writable,
            "fts_enabled": self.fts_enabled,
            "schema_version": self.schema_version,
            "detail": self.detail,
            "database_path": self.database_path,
        }


class MemoryRepository(ABC):
    """Persistence contract: create/get/update/delete/list/search/expire/count.

    Determinism contract: list() and search() return rows ordered by
    created_at DESC (stable, id tiebreak). Ranking and pagination are the
    service's job; the repository returns the full matching set.
    """

    @property
    @abstractmethod
    def fts_enabled(self) -> bool:
        """True when full-text search (FTS5) is active; False = LIKE fallback."""

    @abstractmethod
    def initialize(self) -> None:
        """Create/migrate schema. Raises MemoryDatabaseError on failure."""

    @abstractmethod
    def close(self) -> None:
        """Release the database connection (idempotent)."""

    @abstractmethod
    def health(self) -> RepositoryHealth:
        """Accessible, schema valid, migrations current, writable, FTS state."""

    @abstractmethod
    def create(self, memory: Memory) -> None:
        """Persist a new memory; duplicate id raises."""

    @abstractmethod
    def get(
        self,
        memory_id: str,
        *,
        include_expired: bool = False,
        include_deleted: bool = False,
    ) -> Memory | None:
        """Fetch one memory by id (None when absent or filtered out)."""

    @abstractmethod
    def update(self, memory: Memory) -> None:
        """Atomically replace a memory row (service bumps updated_at)."""

    @abstractmethod
    def delete(self, memory_id: str, deleted_at: datetime) -> bool:
        """Soft-delete one memory; returns False when absent. Auditable."""

    @abstractmethod
    def list(self, filters: MemoryFilter) -> MemoryList:
        """All non-deleted, non-expired rows matching the filters."""

    @abstractmethod
    def search(self, query: str, filters: MemoryFilter) -> MemoryList:
        """Rows matching the text query (FTS5 or LIKE fallback) + filters."""

    @abstractmethod
    def expire(self, now: datetime) -> MemoryIdList:
        """Soft-delete expired rows; returns the affected memory ids."""

    @abstractmethod
    def count(self, filters: MemoryFilter) -> int:
        """Number of rows matching the filters (same semantics as list)."""

    @abstractmethod
    def stats(self) -> dict[str, Any]:
        """Counts by type plus subsystem state (fts, schema version)."""
