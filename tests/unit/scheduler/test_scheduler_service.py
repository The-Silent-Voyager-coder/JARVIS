"""Scheduler repository + tick executor tests (roadmap Phase C)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jarvis.configuration.loader import load_config
from jarvis.exceptions import SchedulerUnavailableError, SchedulerValidationError
from jarvis.scheduler.models import ScheduleKind
from jarvis.scheduler.service import SchedulerService
from jarvis.scheduler.sqlite_repository import SqliteSchedulerRepository


def _service(tmp_path: Path) -> SchedulerService:
    d = str(tmp_path).replace("\\", "/")
    cfg = tmp_path / "sched.yaml"
    cfg.write_text(
        f"scheduler:\n  enabled: true\n  max_schedules: 50\n  database_path: \"{d}/sched.db\"\n",
        encoding="utf-8",
    )
    service = SchedulerService()
    service.start(load_config(cfg).config)
    return service


def test_repository_round_trip(tmp_path: Path) -> None:
    repo = SqliteSchedulerRepository(tmp_path / "s.db")
    repo.initialize()
    from jarvis.scheduler.models import Schedule

    s = Schedule(name="a", kind=ScheduleKind.BRIEFING, interval_seconds=3600)
    s.validate()
    repo.save(s)
    assert repo.count() == 1
    assert repo.get(s.id) is not None
    assert len(repo.list()) == 1
    assert repo.remove(s.id) is True
    assert repo.remove(s.id) is False
    h = repo.health()
    assert h.accessible and h.schema_valid and h.migrations_current and h.writable
    repo.close()


def test_add_list_remove(tmp_path: Path) -> None:
    service = _service(tmp_path)
    try:
        data = service.add(name="m", kind="briefing", interval_seconds=3600)
        assert data["id"].startswith("sch_")
        assert len(service.list()) == 1
        assert service.remove(data["id"])["removed"] is True
        assert service.list() == []
    finally:
        service.shutdown()


def test_add_rejects_bad_kind_and_limit(
    tmp_path: Path
) -> None:
    service = _service(tmp_path)
    try:
        with pytest.raises(SchedulerValidationError):
            service.add(name="x", kind="nuke", interval_seconds=3600)
        with pytest.raises(SchedulerValidationError):
            service.add(name="x", kind="briefing", interval_seconds=5)
    finally:
        service.shutdown()


def test_tick_runs_due_only(tmp_path: Path) -> None:
    service = _service(tmp_path)
    calls: list[str] = []

    def record(schedule: object) -> tuple[bool, str]:
        calls.append(getattr(schedule, "id", "?"))
        return True, "ok"

    try:
        service.register_handler("briefing", record)
        due = service.add(name="due", kind="briefing", interval_seconds=3600)
        future = service.add(name="later", kind="briefing", interval_seconds=3600)
        # push one schedule into the future directly via the repository
        repo = service._repository
        assert repo is not None
        item = repo.get(future["id"])
        assert item is not None
        from jarvis.scheduler.models import Schedule

        repo.save(Schedule(
            id=item.id, name=item.name, kind=item.kind,
            interval_seconds=item.interval_seconds, payload=item.payload,
            enabled=item.enabled, created_at=item.created_at,
            last_run_at=item.last_run_at,
            next_run_at=datetime.now(UTC) + timedelta(hours=2),
            last_status=item.last_status, last_summary=item.last_summary,
        ))
        out = service.tick()
        assert out["ran_count"] == 1
        assert out["ran"][0]["schedule_id"] == due["id"]
        assert calls == [due["id"]]
        updated = repo.get(due["id"])
        assert updated is not None and updated.last_status == "ok"
        assert updated.next_run_at > datetime.now(UTC)
    finally:
        service.shutdown()


def test_tick_handler_error_becomes_failed_run(
    tmp_path: Path
) -> None:
    service = _service(tmp_path)
    try:
        def boom(schedule: object) -> tuple[bool, str]:
            raise RuntimeError("kaput")

        service.register_handler("briefing", boom)
        data = service.add(name="x", kind="briefing", interval_seconds=3600)
        out = service.tick()
        assert out["ran_count"] == 1
        assert out["ran"][0]["ok"] is False
        repo = service._repository
        assert repo is not None
        updated = repo.get(data["id"])
        assert updated is not None and updated.last_status == "failed"
    finally:
        service.shutdown()


def test_tick_missing_handler_fails_open(
    tmp_path: Path
) -> None:
    service = _service(tmp_path)
    try:
        service.add(name="x", kind="tool", interval_seconds=3600,
                    payload={"tool_id": "system.info"})
        out = service.tick()
        assert out["ran"][0]["ok"] is False
    finally:
        service.shutdown()


def test_unavailable_when_disabled(
    tmp_path: Path
) -> None:
    d = str(tmp_path).replace("\\", "/")
    cfg = tmp_path / "disabled.yaml"
    cfg.write_text(
        f"scheduler:\n  enabled: false\n  max_schedules: 50\n  database_path: \"{d}/s.db\"\n",
        encoding="utf-8",
    )
    service = SchedulerService()
    service.start(load_config(cfg).config)
    try:
        assert service.health()["status"] == "disabled"
        with pytest.raises(SchedulerUnavailableError):
            service.list()
    finally:
        service.shutdown()
