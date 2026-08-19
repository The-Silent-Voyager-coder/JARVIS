"""Loop detection: structural, deterministic, threshold-based (spec §11)."""

from __future__ import annotations

import pytest

from jarvis.agent.loopdetect import LoopDetector
from jarvis.agent.models import ToolCall
from jarvis.exceptions import AgentValidationError


def _call(tool_id: str = "filesystem.list", arguments: dict | None = None) -> ToolCall:
    return ToolCall(id="c", tool_id=tool_id, arguments=dict(arguments or {}))


def test_threshold_below_two_rejected() -> None:
    with pytest.raises(AgentValidationError, match=">= 2"):
        LoopDetector(1)


def test_identical_tool_calls_detect_loop() -> None:
    detector = LoopDetector(threshold=2)
    assert detector.record(_call()) is False
    assert detector.streak == 1
    assert detector.record(_call()) is True
    assert detector.streak == 2


def test_argument_order_does_not_matter() -> None:
    detector = LoopDetector(threshold=2)
    assert detector.record(_call(arguments={"a": 1, "b": 2})) is False
    assert detector.record(_call(arguments={"b": 2, "a": 1})) is True


def test_different_arguments_reset_streak() -> None:
    detector = LoopDetector(threshold=3)
    detector.record(_call(arguments={"query": "a"}))
    detector.record(_call(arguments={"query": "a"}))
    assert detector.record(_call(arguments={"query": "b"})) is False
    assert detector.streak == 1


def test_different_tool_resets_streak() -> None:
    detector = LoopDetector(threshold=2)
    detector.record(_call())
    assert detector.record(_call(tool_id="shell.execute")) is False
    assert detector.streak == 1


def test_loop_records_true_at_threshold_and_after() -> None:
    detector = LoopDetector(threshold=3)
    detector.record(_call())
    detector.record(_call())
    assert detector.record(_call()) is True
    assert detector.record(_call()) is True


def test_reset_clears_streak() -> None:
    detector = LoopDetector(threshold=2)
    detector.record(_call())
    detector.reset()
    assert detector.streak == 0
    assert detector.record(_call()) is False


def test_non_serializable_arguments_do_not_crash() -> None:
    detector = LoopDetector(threshold=2)
    marker_a = object()
    marker_b = object()
    assert detector.record(_call(arguments={"x": marker_a})) is False
    assert detector.record(_call(arguments={"x": marker_b})) is False
    assert detector.streak == 1
    detector.record(_call(arguments={"x": [1, {"k": "v"}]}))
    assert detector.streak >= 1
