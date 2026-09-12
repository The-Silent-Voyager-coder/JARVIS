"""Cooperative cancellation for tasks (Phase 6)."""

from __future__ import annotations

import threading


class CancellationToken:
    """Thread-safe cooperative cancel flag."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def is_set(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            from greatsage.exceptions import TaskCancelledError

            raise TaskCancelledError("task cancelled")
