"""Session-scoped working memory (RAM only, Phase 3 §27).

Working memory is deliberately ephemeral: it exists for the duration of a
session, is isolated between sessions, and never becomes long-term memory
automatically. Items carry an optional TTL and are swept lazily on access.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from greatsage.memory.models import utcnow

WORKING_DEFAULT_TTL_SECONDS = 1800.0


@dataclass(frozen=True)
class WorkingMemoryItem:
    id: str
    content: Any
    session_id: str
    created_at: datetime
    expires_at: datetime | None

    @property
    def expired(self) -> bool:
        return self.expires_at is not None and self.expires_at <= utcnow()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "content": self.content,
        }


class WorkingMemory:
    """One session's RAM working memory."""

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._items: dict[str, WorkingMemoryItem] = {}

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def size(self) -> int:
        return len(self._items)

    def add(
        self,
        content: Any,
        *,
        ttl_seconds: float | None = None,
        item_id: str | None = None,
    ) -> str:
        """Store an item; returns its id. ttl_seconds=None means no TTL."""
        ttl = WORKING_DEFAULT_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        now = utcnow()
        expires = now + timedelta(seconds=ttl) if ttl > 0 else None
        item = WorkingMemoryItem(
            id=item_id or f"wm_{uuid.uuid4().hex}",
            content=content,
            session_id=self._session_id,
            created_at=now,
            expires_at=expires,
        )
        self._items[item.id] = item
        return item.id

    def get(self, item_id: str) -> WorkingMemoryItem | None:
        item = self._items.get(item_id)
        if item is None:
            return None
        if item.expired:
            self._items.pop(item_id, None)
            return None
        return item

    def remove(self, item_id: str) -> bool:
        return self._items.pop(item_id, None) is not None

    def list(self) -> list[WorkingMemoryItem]:
        """Active (non-expired) items, newest first."""
        self.sweep()
        return sorted(self._items.values(), key=lambda i: i.created_at, reverse=True)

    def sweep(self) -> int:
        """Drop expired items; returns the number dropped."""
        now = utcnow()
        dropped = [
            iid
            for iid, item in self._items.items()
            if item.expires_at is not None and item.expires_at <= now
        ]
        for iid in dropped:
            self._items.pop(iid, None)
        return len(dropped)

    def clear(self) -> None:
        self._items.clear()


class WorkingMemoryStore:
    """Session → WorkingMemory map with strict per-session isolation."""

    def __init__(self) -> None:
        self._sessions: dict[str, WorkingMemory] = {}

    def session(self, session_id: str) -> WorkingMemory:
        """Get (or lazily create) a session's working memory."""
        existing = self._sessions.get(session_id)
        if existing is None:
            existing = WorkingMemory(session_id)
            self._sessions[session_id] = existing
        return existing

    def drop(self, session_id: str) -> bool:
        """End a session's working memory (lifecycle end)."""
        return self._sessions.pop(session_id, None) is not None

    def sweep_all(self) -> int:
        return sum(session.sweep() for session in self._sessions.values())

    @property
    def session_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._sessions))
