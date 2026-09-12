"""Planning models tests."""

import pytest

from greatsage.exceptions import PlanningValidationError
from greatsage.planning.models import Plan, Step


def test_step_validate() -> None:
    s = Step(sequence=1, description="do", tool_id="filesystem.list", arguments={})
    s.validate()
    with pytest.raises(PlanningValidationError):
        Step(sequence=0, description="x", tool_id="t").validate()
    with pytest.raises(PlanningValidationError):
        Step(sequence=1, description=" ", tool_id="t").validate()


def test_plan_validate() -> None:
    s = Step(sequence=1, description="a", tool_id="filesystem.list", arguments={})
    p = Plan(goal="test", steps=(s,))
    p.validate()
    with pytest.raises(PlanningValidationError):
        Plan(goal=" ", steps=(s,)).validate()
    with pytest.raises(PlanningValidationError):
        Plan(goal="x", steps=()).validate()
    # sequences must be contiguous
    s2 = Step(sequence=3, description="b", tool_id="filesystem.list", arguments={})
    with pytest.raises(PlanningValidationError):
        Plan(goal="x", steps=(s, s2)).validate()


def test_plan_roundtrip() -> None:
    s = Step(sequence=1, description="a", tool_id="filesystem.list", arguments={"path": "."})
    p = Plan(goal="hello", steps=(s,))
    d = p.to_dict()
    p2 = Plan.from_dict(d)
    assert p2.goal == "hello"
    assert p2.steps[0].tool_id == "filesystem.list"
