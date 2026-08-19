"""Cancellation token for agent runs (spec §13).

The orchestrator checks the token between steps and before each tool call,
and propagates cancellation to the provider (where supported). A cancelled
run always ends in the CANCELLED terminal state — it never stays RUNNING.
"""

from __future__ import annotations

import threading

from jarvis.exceptions import AgentCancelledError


class CancellationToken:
    """Thread-safe cooperative cancellation flag."""

    def __init__(self) -> None:
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def raise_if_cancelled(self) -> None:
        if self._cancelled.is_set():
            raise AgentCancelledError("agent task cancelled")
