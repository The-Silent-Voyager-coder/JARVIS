# ruff: noqa: E501
"""Planner unit tests (deterministic templates)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from greatsage.exceptions import PlanningValidationError
from greatsage.planning.planner import Planner
from greatsage.workspace.models import EntryPoint, ProjectType, StructureSummary, WorkspaceInfo


def make_workspace(root: Path, ptype: ProjectType = ProjectType.PYTHON) -> WorkspaceInfo:
    return WorkspaceInfo(
        root=root,
        name=root.name,
        project_type=ptype,
        entry_points=(EntryPoint(path=root / "README.md", kind="generic"),),
        structure=StructureSummary(root=root, depth=3, total_files=1, total_dirs=0, entries=[]),
        scanned_at=datetime.now(UTC),
    )


def test_planner_simple_goal(tmp_path: Path) -> None:
    planner = Planner(max_plan_steps=25)
    ws = make_workspace(tmp_path)
    plan = planner.create_plan("list files", ws)
    assert plan.goal == "list files"
    assert len(plan.steps) >= 1
    assert plan.steps[0].tool_id == "filesystem.list"
    assert plan.steps[0].risk_estimate == "low"


def test_planner_three_step_goal(tmp_path: Path) -> None:
    planner = Planner()
    ws = make_workspace(tmp_path)
    plan = planner.create_plan("list files, read file, write file", ws)
    assert len(plan.steps) == 3
    assert plan.steps[0].tool_id == "filesystem.list"
    assert plan.steps[1].tool_id == "filesystem.read"
    assert plan.steps[2].tool_id == "filesystem.write"
    assert all(s.rollback_hint is not None for s in plan.steps if s.tool_id == "filesystem.write")


def test_planner_empty_goal_rejected() -> None:
    planner = Planner()
    with pytest.raises(PlanningValidationError, match="goal"):
        planner.create_plan("", None)


def test_planner_respects_max_steps(tmp_path: Path) -> None:
    planner = Planner(max_plan_steps=2)
    ws = make_workspace(tmp_path)
    plan = planner.create_plan("list, read, write, system info, process list", ws)
    assert len(plan.steps) == 2
    assert plan.steps[0].sequence == 1
    assert plan.steps[1].sequence == 2


def test_planner_unknown_tool_never_emitted(tmp_path: Path) -> None:
    planner = Planner()
    ws = make_workspace(tmp_path)
    # Even with weird goal, planner should emit only allowed tools
    plan = planner.create_plan("do something completely unknown foobar", ws)
    allowed = {"filesystem.list", "filesystem.stat", "filesystem.read", "filesystem.mkdir", "filesystem.write", "process.list", "process.info", "system.info", "shell.execute"}
    for step in plan.steps:
        assert step.tool_id in allowed


def test_planner_acceptance_criteria_and_rollback(tmp_path: Path) -> None:
    planner = Planner()
    ws = make_workspace(tmp_path)
    plan = planner.create_plan("write file", ws)
    step = next(s for s in plan.steps if s.tool_id == "filesystem.write")
    assert step.acceptance_criteria
    assert step.rollback_hint is not None
    assert "remove" in step.rollback_hint.lower()


def test_planner_integration_goal_split(tmp_path: Path) -> None:
    planner = Planner()
    ws = make_workspace(tmp_path)
    plan = planner.create_plan("list files and read file and write file", ws)
    # Should produce 3 steps via "and" split
    assert len(plan.steps) == 3
