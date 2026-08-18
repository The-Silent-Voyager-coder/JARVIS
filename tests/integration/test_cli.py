"""CLI integration tests: help, version, config validate, health, exit codes."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.cli import EXIT_FAILURE, EXIT_INVALID, EXIT_OK, main


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "usage: jarvis" in out


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "jarvis 0.3.0" in capsys.readouterr().out


def test_config_validate_valid(valid_config_yaml: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["config", "validate", "--config", str(valid_config_yaml)])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "Configuration valid." in out
    assert str(valid_config_yaml) in out


def test_config_validate_defaults(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("JARVIS_CONFIG_PATH", raising=False)
    code = main(["config", "validate"])
    assert code == EXIT_OK
    assert "built-in defaults" in capsys.readouterr().out


def test_config_validate_invalid(
    invalid_config_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["config", "validate", "--config", str(invalid_config_yaml)])
    assert code == EXIT_INVALID
    err = capsys.readouterr().err
    assert "Configuration error:" in err
    assert "logging.level" in err


def test_config_validate_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["config", "validate", "--config", str(tmp_path / "absent.yaml")])
    assert code == EXIT_INVALID
    assert "configuration file not found" in capsys.readouterr().err


def test_health_command(valid_config_yaml: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["health", "--config", str(valid_config_yaml)])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "J.A.R.V.I.S. Health" in out
    assert "Core" in out and "HEALTHY" in out
    assert "Configuration" in out
    assert "Event Bus" in out
    assert "Service Registry" in out
    assert "Storage" in out
    assert "Overall" in out


def test_health_with_invalid_config(
    invalid_config_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["health", "--config", str(invalid_config_yaml)])
    assert code == EXIT_INVALID
    assert "Configuration error:" in capsys.readouterr().err


def test_health_unhealthy_storage_returns_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # data_dir collides with an existing file: the runtime cannot start.
    collide = tmp_path / "data-blocked"
    collide.write_text("nope", encoding="utf-8")
    config_path = tmp_path / "bad-storage.yaml"
    d = str(tmp_path).replace("\\", "/")
    config_path.write_text(
        f"core:\n  data_dir: \"{d}/data-blocked\"\n  logs_dir: \"{d}/logs\"\n",
        encoding="utf-8",
    )
    code = main(["health", "--config", str(config_path)])
    assert code == EXIT_FAILURE
    err = capsys.readouterr().err
    assert "runtime startup failed" in err


def test_no_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    code = main([])
    assert code == EXIT_OK
    assert "usage: jarvis" in capsys.readouterr().out


def test_unknown_subcommand_errors() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["config", "frobnicate"])
    assert exc.value.code == EXIT_INVALID


def test_ai_benchmark_command(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["ai", "benchmark"])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "Hardware benchmark" in out
    assert "platform" in out
    assert "cpu" in out


def test_ai_benchmark_json(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["ai", "benchmark", "--json"])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert '"platform"' in out


def test_ai_health_command_reports_providers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    d = str(tmp_path).replace("\\", "/")
    config_path = tmp_path / "ai-config.yaml"
    config_path.write_text(
        f"""
core:
  name: "ai cli test"
  data_dir: "{d}/data"
  cache_dir: "{d}/cache"
  logs_dir: "{d}/logs"
  runtime_dir: "{d}/runtime"
  workspaces_dir: "{d}/workspaces"
  models_dir: "{d}/models"
  backups_dir: "{d}/backups"
  timezone: "UTC"
logging:
  level: "INFO"
  retention_days: 1
ai:
  default_provider: "local"
  providers:
    local:
      type: "local"
      enabled: true
      base_url: "http://127.0.0.1:1"
      model: ""
      timeout_seconds: 1
    opencode:
      type: "opencode"
      enabled: false
      base_url: "http://127.0.0.1:4096"
      api_key_env: ""
      timeout_seconds: 1
""",
        encoding="utf-8",
    )
    code = main(["ai", "health", "--config", str(config_path)])
    assert code == EXIT_FAILURE  # configured provider is unreachable
    out = capsys.readouterr().out
    assert "AI Provider Health" in out
    assert "local" in out


def test_ai_providers_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    d = str(tmp_path).replace("\\", "/")
    config_path = tmp_path / "ai-config.yaml"
    config_path.write_text(
        f"""
core:
  name: "ai cli test"
  data_dir: "{d}/data"
  cache_dir: "{d}/cache"
  logs_dir: "{d}/logs"
  runtime_dir: "{d}/runtime"
  workspaces_dir: "{d}/workspaces"
  models_dir: "{d}/models"
  backups_dir: "{d}/backups"
  timezone: "UTC"
logging:
  level: "INFO"
  retention_days: 1
ai:
  default_provider: "local"
  providers:
    local:
      type: "local"
      enabled: true
      base_url: "http://127.0.0.1:1"
      model: ""
      timeout_seconds: 1
    opencode:
      type: "opencode"
      enabled: true
      base_url: "http://127.0.0.1:1"
      api_key_env: ""
      timeout_seconds: 1
""",
        encoding="utf-8",
    )
    code = main(["ai", "providers", "--config", str(config_path)])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "local" in out
    assert "opencode" in out
    assert "text_generation" in out


def test_ai_health_with_invalid_config(
    invalid_config_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["ai", "health", "--config", str(invalid_config_yaml)])
    assert code == EXIT_INVALID
    assert "Configuration error:" in capsys.readouterr().err
