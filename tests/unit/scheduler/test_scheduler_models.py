"""Scheduler model + limit tests (roadmap Phase C)."""

from __future__ import annotations

import pytest

from jarvis.exceptions import SchedulerValidationError
from jarvis.scheduler import limits
from jarvis.scheduler.models import Schedule, ScheduleKind


def test_kinds_closed_set() -> None:
    assert {k.value for k in ScheduleKind} == {"briefing", "tool"}


def test_valid_schedule() -> None:
    s = Schedule(name="morning", kind=ScheduleKind.BRIEFING, interval_seconds=3600)
    s.validate()
    assert s.id.startswith("sch_")
    assert s.enabled is True
    assert s.last_status == "never"
    d = s.to_dict()
    assert d["kind"] == "briefing" and d["interval_seconds"] == 3600
    assert Schedule.from_dict(d).id == s.id


def test_empty_name_rejected() -> None:
    with pytest.raises(SchedulerValidationError):
        Schedule(name="  ", kind=ScheduleKind.BRIEFING, interval_seconds=3600).validate()


def test_interval_floor_and_ceiling() -> None:
    with pytest.raises(SchedulerValidationError):
        Schedule(name="x", kind=ScheduleKind.BRIEFING, interval_seconds=59).validate()
    with pytest.raises(SchedulerValidationError):
        Schedule(
            name="x",
            kind=ScheduleKind.BRIEFING,
            interval_seconds=limits.MAX_INTERVAL_SECONDS_CEILING + 1,
        ).validate()


def test_tool_kind_requires_tool_id() -> None:
    with pytest.raises(SchedulerValidationError):
        Schedule(name="x", kind=ScheduleKind.TOOL, interval_seconds=3600, payload={}).validate()
    Schedule(
        name="x", kind=ScheduleKind.TOOL, interval_seconds=3600,
        payload={"tool_id": "system.info"},
    ).validate()


def test_unknown_kind_rejected() -> None:
    with pytest.raises(SchedulerValidationError):
        Schedule.from_dict({"name": "x", "kind": "nuke", "interval_seconds": 3600})


def test_limits_defaults_and_ceilings() -> None:
    assert limits.MAX_SCHEDULES_DEFAULT == 50
    assert limits.MAX_SCHEDULES_CEILING == 200
    assert limits.MIN_INTERVAL_SECONDS == 60
    with pytest.raises(ValueError):
        limits.check_bounded("scheduler.max_schedules", 201, limits.MAX_SCHEDULES_CEILING)
