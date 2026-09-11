"""Scheduler limits (roadmap Phase C)."""

from __future__ import annotations

MAX_SCHEDULES_DEFAULT = 50
MAX_SCHEDULES_CEILING = 200

MIN_INTERVAL_SECONDS = 60
DEFAULT_INTERVAL_SECONDS = 3600
MAX_INTERVAL_SECONDS_CEILING = 604800


def check_bounded(name: str, value: float | int, ceiling: float | int) -> None:
    if value > ceiling:
        raise ValueError(f"{name} value {value} exceeds ceiling {ceiling} (at most {ceiling})")
