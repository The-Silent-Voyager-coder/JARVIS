"""Agent limit defaults, ceilings, and bounded validation (spec §10-12)."""

from __future__ import annotations

import pytest

from greatsage.agent.limits import (
    AGENT_APPROVAL_WAIT_SECONDS_CEILING,
    AGENT_APPROVAL_WAIT_SECONDS_DEFAULT,
    LOOP_DETECTION_THRESHOLD_CEILING,
    LOOP_DETECTION_THRESHOLD_DEFAULT,
    MAX_SINGLE_TOOL_CALLS_CEILING,
    MAX_SINGLE_TOOL_CALLS_DEFAULT,
    MAX_STEPS_CEILING,
    MAX_STEPS_DEFAULT,
    MAX_TOOL_CALLS_CEILING,
    MAX_TOOL_CALLS_DEFAULT,
    MAX_TOTAL_TOOL_OUTPUT_BYTES_CEILING,
    MAX_TOTAL_TOOL_OUTPUT_BYTES_DEFAULT,
    MAX_WALL_TIME_SECONDS_CEILING,
    MAX_WALL_TIME_SECONDS_DEFAULT,
    check_bounded,
)
from greatsage.agent.models import AgentLimits
from greatsage.exceptions import AgentValidationError


def test_defaults_are_bounded() -> None:
    assert MAX_STEPS_DEFAULT <= MAX_STEPS_CEILING
    assert MAX_TOOL_CALLS_DEFAULT <= MAX_TOOL_CALLS_CEILING
    assert MAX_WALL_TIME_SECONDS_DEFAULT <= MAX_WALL_TIME_SECONDS_CEILING
    assert MAX_SINGLE_TOOL_CALLS_DEFAULT <= MAX_SINGLE_TOOL_CALLS_CEILING
    assert MAX_TOTAL_TOOL_OUTPUT_BYTES_DEFAULT <= MAX_TOTAL_TOOL_OUTPUT_BYTES_CEILING
    assert LOOP_DETECTION_THRESHOLD_DEFAULT <= LOOP_DETECTION_THRESHOLD_CEILING
    assert AGENT_APPROVAL_WAIT_SECONDS_DEFAULT <= AGENT_APPROVAL_WAIT_SECONDS_CEILING


def test_check_bounded_allows_at_ceiling() -> None:
    assert check_bounded("agent.max_steps", MAX_STEPS_CEILING, MAX_STEPS_CEILING) is None


def test_check_bounded_rejects_above_ceiling() -> None:
    with pytest.raises(ValueError, match="must be at most"):
        check_bounded("agent.max_tool_calls", MAX_TOOL_CALLS_CEILING + 1, MAX_TOOL_CALLS_CEILING)


def test_default_limits_validate() -> None:
    AgentLimits().validate()


def test_limits_reject_max_steps_above_ceiling() -> None:
    with pytest.raises(AgentValidationError, match="max_steps must be at most"):
        AgentLimits(max_steps=MAX_STEPS_CEILING + 1).validate()


def test_limits_reject_max_tool_calls_above_ceiling() -> None:
    with pytest.raises(AgentValidationError, match="max_tool_calls must be at most"):
        AgentLimits(max_tool_calls=MAX_TOOL_CALLS_CEILING + 1).validate()


def test_limits_reject_wall_clock_above_ceiling() -> None:
    with pytest.raises(AgentValidationError, match="max_wall_time_seconds must be at most"):
        AgentLimits(max_wall_time_seconds=MAX_WALL_TIME_SECONDS_CEILING + 1).validate()


def test_limits_reject_single_tool_calls_above_ceiling() -> None:
    with pytest.raises(AgentValidationError, match="max_single_tool_calls must be at most"):
        AgentLimits(max_single_tool_calls=MAX_SINGLE_TOOL_CALLS_CEILING + 1).validate()


def test_limits_reject_output_bytes_above_ceiling() -> None:
    with pytest.raises(AgentValidationError, match="max_total_tool_output_bytes must be at most"):
        AgentLimits(max_total_tool_output_bytes=MAX_TOTAL_TOOL_OUTPUT_BYTES_CEILING + 1).validate()


def test_limits_reject_loop_threshold_above_ceiling() -> None:
    with pytest.raises(AgentValidationError, match="loop_detection_threshold must be at most"):
        AgentLimits(loop_detection_threshold=LOOP_DETECTION_THRESHOLD_CEILING + 1).validate()


def test_limits_reject_approval_wait_above_ceiling() -> None:
    with pytest.raises(AgentValidationError, match="approval_wait_seconds must be at most"):
        AgentLimits(approval_wait_seconds=AGENT_APPROVAL_WAIT_SECONDS_CEILING + 1).validate()


def test_limits_reject_loop_threshold_below_two() -> None:
    with pytest.raises(AgentValidationError, match="loop_detection_threshold must be >= 2"):
        AgentLimits(loop_detection_threshold=1).validate()


def test_limits_reject_non_positive_wall_clock() -> None:
    with pytest.raises(AgentValidationError, match="max_wall_time_seconds must be positive"):
        AgentLimits(max_wall_time_seconds=0).validate()


def test_limits_reject_zero_steps() -> None:
    with pytest.raises(AgentValidationError, match="max_steps must be >= 1"):
        AgentLimits(max_steps=0).validate()


def test_limits_allow_boundary_values() -> None:
    AgentLimits(max_steps=MAX_STEPS_CEILING, max_tool_calls=MAX_TOOL_CALLS_CEILING).validate()
