"""Loop detection for the agent orchestrator (spec §11).

Identical tool calls (same tool_id and arguments) in a row indicate a loop.
Detection is purely structural — no semantic analysis — and deterministic:
after `threshold` consecutive identical calls the detector reports a loop and
the orchestrator stops the run (AgentLimitReached).
"""

from __future__ import annotations

import json

from jarvis.agent.models import ToolCall
from jarvis.exceptions import AgentValidationError


def _signature(call: ToolCall) -> str:
    normalized = json.dumps(call.arguments, sort_keys=True, default=str)
    return f"{call.tool_id}:{normalized}"


class LoopDetector:
    """Counts consecutive identical tool calls."""

    def __init__(self, threshold: int) -> None:
        if threshold < 2:
            raise AgentValidationError(
                f"loop detection threshold must be >= 2, got {threshold}"
            )
        self._threshold = threshold
        self._streak = 0
        self._last: str | None = None

    @property
    def threshold(self) -> int:
        return self._threshold

    @property
    def streak(self) -> int:
        return self._streak

    def record(self, call: ToolCall) -> bool:
        """Record one call; returns True when the loop threshold is reached."""
        signature = _signature(call)
        if signature == self._last:
            self._streak += 1
        else:
            self._streak = 1
            self._last = signature
        return self._streak >= self._threshold

    def reset(self) -> None:
        self._streak = 0
        self._last = None
