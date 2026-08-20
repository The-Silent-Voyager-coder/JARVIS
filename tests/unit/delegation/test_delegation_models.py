"""Delegation model unit tests: states, limits, validation, and results.

Offline and deterministic — no I/O, no network, no external services.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.delegation.limits import (
    MAX_DELEGATION_DEPTH_CEILING,
    MAX_DELEGATION_DEPTH_DEFAULT,
    MAX_OUTPUT_BYTES_CEILING,
    MAX_OUTPUT_BYTES_DEFAULT,
    MAX_PERMISSION_REQUESTS_CEILING,
    MAX_PERMISSION_REQUESTS_DEFAULT,
    MAX_SESSION_COUNT_CEILING,
    MAX_SESSION_COUNT_DEFAULT,
    MAX_WALL_TIME_SECONDS_CEILING,
    MAX_WALL_TIME_SECONDS_DEFAULT,
)
from jarvis.delegation.models import (
    DelegationLimits,
    DelegationPermission,
    DelegationRequest,
    DelegationResult,
    DelegationRunStatus,
    DelegationState,
    transition_state,
)
from jarvis.exceptions import DelegationStateError, DelegationValidationError


class TestStateMachine:
    def test_terminal_states(self) -> None:
        for state in (
            DelegationState.COMPLETED,
            DelegationState.FAILED,
            DelegationState.CANCELLED,
            DelegationState.TIMED_OUT,
        ):
            assert state.is_terminal

    def test_non_terminal_states(self) -> None:
        for state in (DelegationState.CREATED, DelegationState.RUNNING, DelegationState.COMPLETING):
            assert not state.is_terminal

    def test_valid_transitions(self) -> None:
        assert DelegationState.can_transition(DelegationState.CREATED, DelegationState.STARTING)
        assert DelegationState.can_transition(DelegationState.STARTING, DelegationState.RUNNING)
        assert DelegationState.can_transition(
            DelegationState.RUNNING, DelegationState.WAITING_FOR_PERMISSION
        )
        assert DelegationState.can_transition(
            DelegationState.WAITING_FOR_PERMISSION, DelegationState.RUNNING
        )
        assert DelegationState.can_transition(DelegationState.RUNNING, DelegationState.COMPLETING)
        assert DelegationState.can_transition(DelegationState.COMPLETING, DelegationState.COMPLETED)

    def test_invalid_transitions(self) -> None:
        assert not DelegationState.can_transition(DelegationState.CREATED, DelegationState.RUNNING)
        assert not DelegationState.can_transition(  # noqa: E501
            DelegationState.COMPLETED, DelegationState.RUNNING
        )
        assert not DelegationState.can_transition(DelegationState.FAILED, DelegationState.RUNNING)

    def test_transition_state_raises(self) -> None:
        with pytest.raises(DelegationStateError, match="invalid delegation state transition"):
            transition_state(DelegationState.CREATED, DelegationState.RUNNING)

    def test_transition_state_same_is_noop(self) -> None:
        assert transition_state(DelegationState.RUNNING, DelegationState.RUNNING) is (
            DelegationState.RUNNING
        )

    def test_terminal_has_no_transitions(self) -> None:
        terminal = DelegationState.can_transition(
            DelegationState.COMPLETED, DelegationState.FAILED
        )
        assert terminal is False


class TestDelegationLimits:
    def test_defaults_are_within_ceilings(self) -> None:
        limits = DelegationLimits()
        limits.validate()
        assert limits.max_wall_time_seconds == MAX_WALL_TIME_SECONDS_DEFAULT
        assert limits.max_output_bytes == MAX_OUTPUT_BYTES_DEFAULT
        assert limits.max_permission_requests == MAX_PERMISSION_REQUESTS_DEFAULT
        assert limits.max_session_count == MAX_SESSION_COUNT_DEFAULT
        assert limits.max_delegation_depth == MAX_DELEGATION_DEPTH_DEFAULT

    def test_ceiling_values(self) -> None:
        assert MAX_WALL_TIME_SECONDS_CEILING >= MAX_WALL_TIME_SECONDS_DEFAULT
        assert MAX_OUTPUT_BYTES_CEILING >= MAX_OUTPUT_BYTES_DEFAULT
        assert MAX_PERMISSION_REQUESTS_CEILING >= MAX_PERMISSION_REQUESTS_DEFAULT
        assert MAX_SESSION_COUNT_CEILING >= MAX_SESSION_COUNT_DEFAULT
        assert MAX_DELEGATION_DEPTH_CEILING == 1  # never recursive

    def test_exceed_ceiling_rejected(self) -> None:
        limits = DelegationLimits(max_delegation_depth=2)
        with pytest.raises(DelegationValidationError, match="at most"):
            limits.validate()

    def test_non_positive_values_rejected(self) -> None:
        for limits in (
            DelegationLimits(max_wall_time_seconds=0.0),
            DelegationLimits(max_output_bytes=0),
            DelegationLimits(max_permission_requests=0),
            DelegationLimits(max_session_count=0),
            DelegationLimits(max_delegation_depth=0),
        ):
            with pytest.raises(DelegationValidationError):
                limits.validate()


class TestDelegationRequest:
    def test_valid_request(self) -> None:
        request = DelegationRequest(
            prompt="refactor the service", working_directory=Path("C:/tmp/ws")
        )
        request.validate()

    def test_empty_prompt_rejected(self) -> None:
        request = DelegationRequest(
            prompt=" ", working_directory=Path("C:/tmp/ws")
        )
        with pytest.raises(DelegationValidationError, match="non-empty prompt"):
            request.validate()

    def test_relative_working_directory_rejected(self) -> None:
        request = DelegationRequest(
            prompt="x", working_directory=Path("relative")
        )
        with pytest.raises(DelegationValidationError, match="absolute"):
            request.validate()

    def test_empty_working_directory_rejected(self) -> None:
        request = DelegationRequest(prompt="x", working_directory=Path(""))
        with pytest.raises(DelegationValidationError, match="working directory"):
            request.validate()

    def test_negative_depth_rejected(self) -> None:
        request = DelegationRequest(
            prompt="x", working_directory=Path("C:/tmp/ws"), depth=-1
        )
        with pytest.raises(DelegationValidationError, match="depth"):
            request.validate()

    def test_empty_capability_rejected(self) -> None:
        request = DelegationRequest(
            prompt="x",
            working_directory=Path("C:/tmp/ws"),
            requested_capabilities=("",),
        )
        with pytest.raises(DelegationValidationError, match="capabilities"):
            request.validate()


class TestDelegationRunStatus:
    def test_to_dict_shape(self) -> None:
        status = DelegationRunStatus(
            task_id="t-1",
            request_id="r-1",
            session_id="s-1",
            provider="opencode",
            provider_session_id="ps-1",
        )
        data = status.to_dict()
        assert data["task_id"] == "t-1"
        assert data["state"] == "created"
        assert data["permission_requests"] == 0
        assert data["output_bytes"] == 0

    def test_transition(self) -> None:
        status = DelegationRunStatus(task_id="t", request_id="r")
        status.transition(DelegationState.STARTING)
        assert status.state is DelegationState.STARTING


class TestDelegationResult:
    def test_to_dict_round_trip(self) -> None:
        result = DelegationResult(
            task_id="t-1",
            request_id="r-1",
            session_id="s-1",
            provider="opencode",
            state=DelegationState.COMPLETED,
            summary="done",
            files_changed=3,
            diff_available=True,
            diff="--- a/x\n+++ b/x\n",
        )
        data = result.to_dict()
        assert data["state"] == "completed"
        assert data["summary"] == "done"
        assert data["files_changed"] == 3
        assert data["diff"] == "--- a/x\n+++ b/x\n"

    def test_permission_defaults(self) -> None:
        permission = DelegationPermission(permission_id="p", session_id="s")
        assert permission.action == "unknown"
        assert permission.path is None
