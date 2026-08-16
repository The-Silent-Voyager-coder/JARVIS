"""Runtime lifecycle state machine.

Valid transitions (Phase 1 contract):

    CREATED → INITIALIZING → RUNNING → STOPPING → STOPPED

plus INITIALIZING → STOPPING (startup failure cleanup). STOPPED is terminal;
rejected transitions raise LifecycleError and leave the state unchanged.
"""

from __future__ import annotations

from enum import Enum

from jarvis.exceptions import LifecycleError


class RuntimeState(Enum):
    CREATED = "created"
    INITIALIZING = "initializing"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"


_TRANSITIONS: dict[RuntimeState, frozenset[RuntimeState]] = {
    RuntimeState.CREATED: frozenset({RuntimeState.INITIALIZING}),
    RuntimeState.INITIALIZING: frozenset({RuntimeState.RUNNING, RuntimeState.STOPPING}),
    RuntimeState.RUNNING: frozenset({RuntimeState.STOPPING}),
    RuntimeState.STOPPING: frozenset({RuntimeState.STOPPED}),
    RuntimeState.STOPPED: frozenset(),
}


class Lifecycle:
    """Owns the current runtime state and enforces valid transitions."""

    def __init__(self) -> None:
        self._state = RuntimeState.CREATED

    @property
    def state(self) -> RuntimeState:
        return self._state

    def transition(self, target: RuntimeState) -> None:
        allowed = _TRANSITIONS[self._state]
        if target not in allowed:
            raise LifecycleError(
                f"invalid runtime transition: {self._state.value} -> {target.value} "
                f"(allowed from {self._state.value}: {sorted(s.value for s in allowed) or 'none'})"
            )
        self._state = target
