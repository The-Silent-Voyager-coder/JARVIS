"""CLI integration tests: schedule add/list/remove/tick/health."""

from __future__ import annotations

from pathlib import Path

import pytest

from greatsage.cli import EXIT_FAILURE, EXIT_INVALID, EXIT_OK, main


def test_schedule_health(valid_config_yaml: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["schedule", "health", "--config", str(valid_config_yaml)])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "Great Sage Scheduler Health" in out
    assert "healthy" in out


def test_schedule_add_list_tick_remove_briefing(
    valid_config_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = str(valid_config_yaml)
    code = main([
        "schedule", "add", "--name", "morning", "--kind", "briefing",
        "--every", "3600", "--config", cfg,
    ])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "Scheduled sch_" in out

    code = main(["schedule", "list", "--config", cfg])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "briefing" in out and "morning" in out
    sched_id = [line.split()[0] for line in out.splitlines() if "morning" in line][0]

    code = main(["schedule", "tick", "--config", cfg])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "Tick ran 1 schedule(s)." in out
    assert sched_id in out and "ok" in out

    code = main(["schedule", "tick", "--config", cfg])
    assert code == EXIT_OK
    assert "Tick ran 0 schedule(s)." in capsys.readouterr().out

    code = main(["schedule", "remove", sched_id, "--config", cfg])
    assert code == EXIT_OK
    assert f"Removed schedule {sched_id}." in capsys.readouterr().out


def test_schedule_tick_tool_runs_through_pipeline(
    valid_config_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = str(valid_config_yaml)
    code = main([
        "schedule", "add", "--name", "sysinfo", "--kind", "tool",
        "--every", "3600", "--tool", "system.info", "--config", cfg,
    ])
    assert code == EXIT_OK
    code = main(["schedule", "tick", "--config", cfg])
    assert code == EXIT_OK
    assert "Tick ran 1 schedule(s)." in capsys.readouterr().out


def test_schedule_add_rejects_bad_input(
    valid_config_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = str(valid_config_yaml)
    code = main([
        "schedule", "add", "--name", "x", "--kind", "nuke",
        "--every", "3600", "--config", cfg,
    ])
    assert code == EXIT_INVALID
    assert "unknown kind" in capsys.readouterr().err

    code = main([
        "schedule", "add", "--name", "x", "--kind", "briefing",
        "--every", "5", "--config", cfg,
    ])
    assert code == EXIT_INVALID
    assert "--every" in capsys.readouterr().err

    code = main([
        "schedule", "add", "--name", "x", "--kind", "tool",
        "--every", "3600", "--config", cfg,
    ])
    assert code == EXIT_INVALID
    assert "--tool" in capsys.readouterr().err

    code = main([
        "schedule", "add", "--name", "x", "--kind", "tool",
        "--every", "3600", "--tool", "system.info",
        "--args", "not-json", "--config", cfg,
    ])
    assert code == EXIT_INVALID
    assert "--args" in capsys.readouterr().err


def test_schedule_remove_unknown(
    valid_config_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["schedule", "remove", "sch_absent", "--config", str(valid_config_yaml)])
    assert code == EXIT_FAILURE
    assert "unknown schedule" in capsys.readouterr().err


def test_schedule_briefing_outside_roots_fails(
    valid_config_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = str(valid_config_yaml)
    code = main([
        "schedule", "add", "--name", "evil", "--kind", "briefing",
        "--every", "3600", "--out", "C:/Windows/Temp/brief.json",
        "--config", cfg,
    ])
    assert code == EXIT_OK
    code = main(["schedule", "tick", "--json", "--config", cfg])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert '"ok": false' in out
