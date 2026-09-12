"""Planning limits (Phase 6)."""

from __future__ import annotations

MAX_PLAN_STEPS_DEFAULT = 25
MAX_PLAN_STEPS_CEILING = 50


def check_bounded(name: str, value: float | int, ceiling: float | int) -> None:
    if value > ceiling:
        raise ValueError(f"{name} value {value} exceeds ceiling {ceiling} (at most {ceiling})")
