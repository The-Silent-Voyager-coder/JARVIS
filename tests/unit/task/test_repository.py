# ruff: noqa: E501
"""Task repository tests."""

from pathlib import Path

from greatsage.task.models import StepResult, TaskRecord, TaskState
from greatsage.task.sqlite_repository import SqliteTaskRepository


def test_task_repository_crud(tmp_path: Path) -> None:
    db = tmp_path / "tasks.db"
    repo = SqliteTaskRepository(db)
    repo.initialize()
    rec = TaskRecord(id="t1", plan_id="p1", goal="g", state=TaskState.PENDING, total_steps=2)
    repo.create_task(rec)
    fetched = repo.get_task("t1")
    assert fetched is not None
    assert fetched.id == "t1"
    rec.transition(TaskState.RUNNING)
    rec.current_step = 1
    repo.update_task(rec)
    assert repo.get_task("t1").state == TaskState.RUNNING
    # step results
    sr = StepResult(step_id="s1", sequence=1, tool_id="filesystem.list", success=True, output={"ok": True}, duration_ms=10.0)
    repo.save_step_result("t1", sr)
    results = repo.get_step_results("t1")
    assert len(results) == 1
    assert results[0].step_id == "s1"
    # list
    assert len(repo.list_tasks()) == 1
    # health
    h = repo.health()
    assert h.accessible is True
    assert h.schema_valid is True
    repo.close()
