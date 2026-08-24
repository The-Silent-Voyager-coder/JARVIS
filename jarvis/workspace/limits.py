"""Workspace limits (Phase 6)."""

from __future__ import annotations

MAX_SCAN_DEPTH_DEFAULT = 3
MAX_SCAN_DEPTH_CEILING = 10

MAX_ENTRIES_DEFAULT = 500
MAX_ENTRIES_CEILING = 5000

SCAN_TIMEOUT_SECONDS_DEFAULT = 10.0
SCAN_TIMEOUT_SECONDS_CEILING = 60.0


def check_bounded(name: str, value: float | int, ceiling: float | int) -> None:
    if value > ceiling:
        raise ValueError(f"{name} value {value} exceeds ceiling {ceiling} (at most {ceiling})")
