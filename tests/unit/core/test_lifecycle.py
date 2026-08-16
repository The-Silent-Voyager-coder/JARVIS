"""Lifecycle state machine tests: valid/invalid transitions."""

from __future__ import annotations

import pytest

from jarvis.core.lifecycle import Lifecycle, RuntimeState
from jarvis.exceptions import LifecycleError


def test_valid_sequence() -> None:
    lc = Lifecycle()
    assert lc.state is RuntimeState.CREATED

    lc.transition(RuntimeState.INITIALIZING)
    assert lc.state is RuntimeState.INITIALIZING

    lc.transition(RuntimeState.RUNNING)
    assert lc.state is RuntimeState.RUNNING

    lc.transition(RuntimeState.STOPPING)
    assert lc.state is RuntimeState.STOPPING

    lc.transition(RuntimeState.STOPPED)
    assert lc.state is RuntimeState.STOPPED


def test_invalid_transition_stopped_to_running() -> None:
    lc = Lifecycle()
    lc.transition(RuntimeState.INITIALIZING)
    lc.transition(RuntimeState.RUNNING)
    lc.transition(RuntimeState.STOPPING)
    lc.transition(RuntimeState.STOPPED)

    with pytest.raises(LifecycleError, match="invalid runtime transition"):
        lc.transition(RuntimeState.RUNNING)


def test_invalid_transition_skips_stopping() -> None:
    lc = Lifecycle()
    lc.transition(RuntimeState.INITIALIZING)
    lc.transition(RuntimeState.RUNNING)
    with pytest.raises(LifecycleError):
        lc.transition(RuntimeState.CREATED)


def test_state_preserved_after_failed_transition() -> None:
    lc = Lifecycle()
    lc.transition(RuntimeState.INITIALIZING)
    with pytest.raises(LifecycleError):
        lc.transition(RuntimeState.STOPPED)
    assert lc.state is RuntimeState.INITIALIZING


def test_failure_cleanup_transition_allowed() -> None:
    lc = Lifecycle()
    lc.transition(RuntimeState.INITIALIZING)
    lc.transition(RuntimeState.STOPPING)
    lc.transition(RuntimeState.STOPPED)
    assert lc.state is RuntimeState.STOPPED


def test_createstart_rejected() -> None:
    lc = Lifecycle()
    lc.transition(RuntimeState.INITIALIZING)
    lc.transition(RuntimeState.RUNNING)
    with pytest.raises(LifecycleError):
        lc.transition(RuntimeState.INITIALIZING)


def test_error_message_lists_allowed() -> None:
    lc = Lifecycle()
    lc.transition(RuntimeState.INITIALIZING)
    lc.transition(RuntimeState.RUNNING)
    with pytest.raises(LifecycleError) as exc:
        lc.transition(RuntimeState.STOPPED)
    assert "running" in str(exc.value)
    assert "stopping" in str(exc.value)
