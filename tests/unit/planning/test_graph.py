# ruff: noqa: E501
"""Task-graph unit tests (Phase 7)."""

from __future__ import annotations

import pytest

from jarvis.exceptions import PlanningValidationError
from jarvis.planning import graph as task_graph
from jarvis.planning.models import Plan, PlanStatus, Step


def lin(*tool_ids: str) -> list[Step]:
    return [
        Step(id=f"s{i}", sequence=i, description=f"step {i}", tool_id=t, arguments={})
        for i, t in enumerate(tool_ids, start=1)
    ]


def test_linear_order_unchanged() -> None:
    steps = lin("filesystem.list", "filesystem.read", "filesystem.write")
    assert [s.id for s in task_graph.topological_order(steps)] == ["s1", "s2", "s3"]
    assert task_graph.levels(steps) == {"s1": 0, "s2": 0, "s3": 0}


def test_dag_order_respects_deps() -> None:
    steps = lin("filesystem.list", "filesystem.read", "filesystem.write")
    steps[2] = Step(id="s3", sequence=3, description="w", tool_id="filesystem.write", arguments={}, depends_on=("s1",))
    ordered = task_graph.topological_order(steps)
    pos = {s.id: i for i, s in enumerate(ordered)}
    assert pos["s1"] < pos["s3"]


def test_missing_dep_rejected() -> None:
    steps = lin("filesystem.list")
    steps[0] = Step(id="s1", sequence=1, description="x", tool_id="filesystem.list", arguments={}, depends_on=("nope",))
    assert task_graph.find_missing_deps(steps) == [("s1", "nope")]
    with pytest.raises(PlanningValidationError, match="unknown step"):
        task_graph.topological_order(steps)


def test_self_dep_rejected() -> None:
    steps = [Step(id="s1", sequence=1, description="x", tool_id="filesystem.list", arguments={}, depends_on=("s1",))]
    assert task_graph.find_self_deps(steps) == ["s1"]
    with pytest.raises(PlanningValidationError, match="itself"):
        task_graph.topological_order(steps)


def test_cycle_rejected() -> None:
    a = Step(id="a", sequence=1, description="a", tool_id="filesystem.list", arguments={}, depends_on=("b",))
    b = Step(id="b", sequence=2, description="b", tool_id="filesystem.read", arguments={}, depends_on=("a",))
    assert task_graph.find_cycle([a, b]) is not None
    with pytest.raises(PlanningValidationError, match="cycle"):
        task_graph.topological_order([a, b])


def test_plan_validate_rejects_cycle() -> None:
    a = Step(id="a", sequence=1, description="a", tool_id="filesystem.list", arguments={}, depends_on=("b",))
    b = Step(id="b", sequence=2, description="b", tool_id="filesystem.read", arguments={}, depends_on=("a",))
    plan = Plan(id="p", goal="g", steps=(a, b), status=PlanStatus.DRAFT)
    with pytest.raises(PlanningValidationError, match="cycle"):
        plan.validate()


def test_plan_validate_rejects_unknown_dep() -> None:
    steps = [Step(id="s1", sequence=1, description="x", tool_id="filesystem.list", arguments={}, depends_on=("ghost",))]
    plan = Plan(id="p", goal="g", steps=tuple(steps), status=PlanStatus.DRAFT)
    with pytest.raises(PlanningValidationError, match="unknown step"):
        plan.validate()


def test_step_depends_on_roundtrip() -> None:
    step = Step(id="s1", sequence=1, description="x", tool_id="filesystem.list", arguments={}, depends_on=("a", "b"))
    assert Step.from_dict(step.to_dict()).depends_on == ("a", "b")
    # Old dicts without the key stay valid (Phase 6 compat).
    legacy = {"id": "s9", "sequence": 1, "description": "x", "tool_id": "filesystem.list"}
    assert Step.from_dict(legacy).depends_on == ()


def test_levels_depth() -> None:
    a = Step(id="a", sequence=1, description="a", tool_id="filesystem.list", arguments={})
    b = Step(id="b", sequence=2, description="b", tool_id="filesystem.read", arguments={}, depends_on=("a",))
    c = Step(id="c", sequence=3, description="c", tool_id="filesystem.write", arguments={}, depends_on=("b",))
    assert task_graph.levels([a, b, c]) == {"a": 0, "b": 1, "c": 2}
