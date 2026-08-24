"""Task models tests."""

import pytest

from jarvis.exceptions import TaskStateError, TaskValidationError
from jarvis.task.models import TaskRecord, TaskState, transition_state


def test_task_state_transitions() -> None:
    assert TaskState.PENDING.value == "pending"
    rec = TaskRecord(id="t1", plan_id="p1", goal="g", state=TaskState.PENDING, total_steps=1)
    rec.transition(TaskState.RUNNING)
    assert rec.state == TaskState.RUNNING
    rec.transition(TaskState.COMPLETED)
    assert rec.state == TaskState.COMPLETED
    with pytest.raises(TaskStateError):
        rec.transition(TaskState.RUNNING)


def test_task_validate() -> None:
    with pytest.raises(TaskValidationError):
        TaskRecord(id=" ", plan_id="p", goal="g").validate()
    with pytest.raises(TaskValidationError):
        TaskRecord(id="t", plan_id=" ", goal="g").validate()


def test_transition_state() -> None:
    assert transition_state(TaskState.PENDING, TaskState.PENDING) == TaskState.PENDING
    with pytest.raises(TaskStateError):
        transition_state(TaskState.COMPLETED, TaskState.RUNNING)
