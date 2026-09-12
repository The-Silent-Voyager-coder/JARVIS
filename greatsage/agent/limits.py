"""Agent loop limits: conservative defaults and absolute safety ceilings.

Phase 5A bounds every AI-driven loop. Defaults are conservative and fully
configurable via the ``agent`` configuration section, but the ceilings below
are hard constants: configuration validation rejects values above them and
the orchestrator re-validates every run against the effective limits
(defense in depth, spec §10-12). Limits are never unlimited.
"""

from __future__ import annotations

MAX_STEPS_DEFAULT = 12
MAX_STEPS_CEILING = 25

MAX_TOOL_CALLS_DEFAULT = 8
MAX_TOOL_CALLS_CEILING = 50

MAX_WALL_TIME_SECONDS_DEFAULT = 300.0
MAX_WALL_TIME_SECONDS_CEILING = 1800.0

MAX_SINGLE_TOOL_CALLS_DEFAULT = 3
MAX_SINGLE_TOOL_CALLS_CEILING = 10

MAX_TOTAL_TOOL_OUTPUT_BYTES_DEFAULT = 2 * 1024 * 1024  # 2 MiB
MAX_TOTAL_TOOL_OUTPUT_BYTES_CEILING = 16 * 1024 * 1024  # 16 MiB

LOOP_DETECTION_THRESHOLD_DEFAULT = 3
LOOP_DETECTION_THRESHOLD_CEILING = 25

AGENT_APPROVAL_WAIT_SECONDS_DEFAULT = 30.0
AGENT_APPROVAL_WAIT_SECONDS_CEILING = 300.0


def check_bounded(name: str, value: int | float, ceiling: int | float) -> None:
    """Raise ValueError when a limit exceeds its absolute safety ceiling."""
    if value > ceiling:
        raise ValueError(f"{name} must be at most {ceiling}, got {value}")
