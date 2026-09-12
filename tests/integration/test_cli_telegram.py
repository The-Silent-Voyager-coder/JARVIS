"""CLI integration tests: telegram health (disabled by default)."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.cli import EXIT_FAILURE, EXIT_INVALID, main


def test_telegram_health_disabled_by_default(
    valid_config_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["telegram", "health", "--config", str(valid_config_yaml)])
    assert code == EXIT_FAILURE  # disabled by default config -> available False
    out = capsys.readouterr().out
    assert "Great Sage Telegram Health" in out
    assert "disabled" in out


def test_telegram_health_json_disabled(
    valid_config_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["telegram", "health", "--json", "--config", str(valid_config_yaml)])
    assert code == EXIT_FAILURE
    assert '"status": "disabled"' in capsys.readouterr().out


def test_telegram_listen_rejects_bad_budget(
    valid_config_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["telegram", "listen", "--for", "0", "--config", str(valid_config_yaml)])
    assert code == EXIT_INVALID
    assert "--for" in capsys.readouterr().err


def test_telegram_listen_unconfigured_reports_failure(
    valid_config_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        ["telegram", "listen", "--once", "--config", str(valid_config_yaml)]
    )
    assert code == EXIT_FAILURE
    assert "telegram" in capsys.readouterr().err


def test_telegram_health_with_invalid_config(
    invalid_config_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["telegram", "health", "--config", str(invalid_config_yaml)])
    assert code == EXIT_INVALID
