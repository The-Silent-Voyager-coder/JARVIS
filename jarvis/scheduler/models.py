"""Scheduler models (roadmap Phase C).

A schedule is a named recurring job: `briefing` (daily-brief snapshot) or
`tool` (one permissioned tool call through the Phase 4 pipeline).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from jarvis.exceptions import SchedulerValidationError
from jarvis.scheduler.limits import MAX_INTERVAL_SECONDS_CEILING, MIN_INTERVAL_SECONDS


class ScheduleKind(StrEnum):
    """Supported job kinds (closed set — the tick executor rejects others)."""

    BRIEFING = "briefing"
    TOOL = "tool"


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Schedule:
    """One recurring job."""

    id: str = field(default_factory=lambda: f"sch_{uuid.uuid4().hex}")
    name: str = ""
    kind: ScheduleKind = ScheduleKind.BRIEFING
    interval_seconds: int = 3600
    payload: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    created_at: datetime = field(default_factory=_utcnow)
    last_run_at: datetime | None = None
    next_run_at: datetime = field(default_factory=_utcnow)
    last_status: str = "never"
    last_summary: str = ""

    def validate(self) -> None:
        if not self.id.strip():
            raise SchedulerValidationError("schedule id must not be empty")
        if not self.name.strip():
            raise SchedulerValidationError("schedule name must not be empty")
        if not isinstance(self.kind, ScheduleKind):
            raise SchedulerValidationError(f"unknown schedule kind: {self.kind!r}")
        if self.interval_seconds < MIN_INTERVAL_SECONDS:
            raise SchedulerValidationError(
                f"interval {self.interval_seconds}s below minimum {MIN_INTERVAL_SECONDS}s"
            )
        if self.interval_seconds > MAX_INTERVAL_SECONDS_CEILING:
            raise SchedulerValidationError(
                f"interval {self.interval_seconds}s exceeds ceiling "
                f"{MAX_INTERVAL_SECONDS_CEILING}s"
            )
        if self.kind is ScheduleKind.TOOL and not str(self.payload.get("tool_id", "")).strip():
            raise SchedulerValidationError("tool schedules require payload.tool_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind.value,
            "interval_seconds": self.interval_seconds,
            "payload": self.payload,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "next_run_at": self.next_run_at.isoformat(),
            "last_status": self.last_status,
            "last_summary": self.last_summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Schedule:
        try:
            kind = ScheduleKind(str(data.get("kind", "briefing")))
        except ValueError as exc:
            raise SchedulerValidationError(
                f"unknown schedule kind: {data.get('kind')!r}"
            ) from exc
        last_run = data.get("last_run_at")
        return cls(
            id=str(data.get("id", f"sch_{uuid.uuid4().hex}")),
            name=str(data.get("name", "")),
            kind=kind,
            interval_seconds=int(data.get("interval_seconds", 3600)),
            payload=dict(data.get("payload", {})),
            enabled=bool(data.get("enabled", True)),
            created_at=_parse_dt(data.get("created_at")) or _utcnow(),
            last_run_at=_parse_dt(last_run),
            next_run_at=_parse_dt(data.get("next_run_at")) or _utcnow(),
            last_status=str(data.get("last_status", "never")),
            last_summary=str(data.get("last_summary", "")),
        )


def _parse_dt(raw: Any) -> datetime | None:
    if raw is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def encode_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True)
