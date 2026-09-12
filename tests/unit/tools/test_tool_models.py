"""Schema and argument validation tests (spec §3, §38, §39)."""

from __future__ import annotations

import pytest

from greatsage.exceptions import ToolValidationError
from greatsage.tools.models import (
    ApprovalOutcome,
    ToolCategory,
    ToolDecision,
    ToolRequest,
    ToolRisk,
    validate_arguments,
    validate_tool_schema,
)

VALID_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "count": {"type": "integer"},
        "ratio": {"type": "number"},
        "flag": {"type": "boolean"},
        "items": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["path"],
}


def test_valid_schema_accepted() -> None:
    validate_tool_schema(VALID_SCHEMA)


@pytest.mark.parametrize(
    "schema",
    [
        None,
        "not-a-dict",
        {"type": "array"},
        {"type": "object"},
        {"type": "object", "properties": "x"},
        {"type": "object", "properties": {"a": {}}},
        {"type": "object", "properties": {"a": {"type": "time"}}},
        {"type": "object", "properties": {"a": {"type": "string"}}, "required": "a"},
        {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["b"]},
    ],
)
def test_invalid_schema_rejected(schema: object) -> None:
    with pytest.raises(ToolValidationError):
        validate_tool_schema(schema)


def test_valid_arguments_accepted() -> None:
    validate_arguments({"path": "C:/x", "count": 2, "ratio": 1.5, "flag": True,
                        "items": ["a"]}, VALID_SCHEMA)


def test_missing_required_rejected() -> None:
    with pytest.raises(ToolValidationError, match="missing required argument"):
        validate_arguments({}, VALID_SCHEMA)


def test_wrong_types_rejected() -> None:
    with pytest.raises(ToolValidationError, match="expected integer"):
        validate_arguments({"path": "x", "count": "2"}, VALID_SCHEMA)
    with pytest.raises(ToolValidationError, match="expected number"):
        validate_arguments({"path": "x", "count": 1, "ratio": True}, VALID_SCHEMA)
    with pytest.raises(ToolValidationError, match="expected string"):
        validate_arguments({"path": 5}, VALID_SCHEMA)
    with pytest.raises(ToolValidationError, match="array items must be string"):
        validate_arguments({"path": "x", "items": [1]}, VALID_SCHEMA)


def test_boolean_not_integer() -> None:
    with pytest.raises(ToolValidationError, match="expected integer"):
        validate_arguments({"path": "x", "count": True}, VALID_SCHEMA)


def test_unknown_arguments_rejected() -> None:
    with pytest.raises(ToolValidationError, match="unknown arguments"):
        validate_arguments({"path": "x", "surprise": 1}, VALID_SCHEMA)


def test_integer_accepts_number_like_int_only() -> None:
    validate_arguments({"path": "x", "count": 3}, VALID_SCHEMA)
    with pytest.raises(ToolValidationError):
        validate_arguments({"path": "x", "count": 3.5}, VALID_SCHEMA)


def test_decision_enum_no_boolean() -> None:
    # spec §9: decisions are ALLOW/DENY/ASK, never a boolean
    assert ToolDecision.ALLOW.value == "allow"
    assert ToolDecision.DENY.value == "deny"
    assert ToolDecision.ASK.value == "ask"


def test_risk_enum_covers_all_required_levels() -> None:
    assert {risk.value for risk in ToolRisk} == {
        "safe", "low", "medium", "high", "critical",
    }


def test_approval_outcomes() -> None:
    assert {outcome.value for outcome in ApprovalOutcome} == {
        "approved", "denied", "timeout", "cancelled",
    }


def test_categories_include_reserved() -> None:
    assert ToolCategory.NETWORK.value == "network"
    assert ToolCategory.BROWSER.value == "browser"
    assert ToolCategory.GUI.value == "gui"


def test_request_and_request_id() -> None:
    request = ToolRequest(request_id="r1", tool_id="x", arguments={}, source="cli")
    assert request.request_id == "r1"
    assert request.source == "cli"
    assert request.session_id is None
