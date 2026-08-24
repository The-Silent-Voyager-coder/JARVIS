"""Task execution limits (Phase 6)."""

from __future__ import annotations

MAX_STEPS_DEFAULT = 25
MAX_STEPS_CEILING = 50

PER_STEP_TIMEOUT_DEFAULT = 30.0
PER_STEP_TIMEOUT_CEILING = 300.0

TOTAL_TIMEOUT_DEFAULT = 600.0
TOTAL_TIMEOUT_CEILING = 3600.0


def check_bounded(name: str, value: float | int, ceiling: float | int) -> None:
    if value > ceiling:
        raise ValueError(f"{name} value {value} exceeds ceiling {ceiling} (at most {ceiling})")
