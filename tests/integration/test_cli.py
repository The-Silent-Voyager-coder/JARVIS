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


# --- memory -------------------------------------------------------------


def _seed_memories(config_path: Path) -> dict[str, str]:
    from jarvis.configuration.loader import load_config
    from jarvis.memory.service import MemoryService

    service = MemoryService()
    service.start(load_config(config_path).config)
    first = service.remember("the quick brown fox", source="cli-seed")
    second = service.remember(
        "preferred coffee is espresso",
        source="cli-seed",
        provenance="user_explicit",
        confidence=0.95,
    )
    service.shutdown()
    return {"fox": first.id, "coffee": second.id}


def test_memory_health_command(valid_config_yaml: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["memory", "health", "--config", str(valid_config_yaml)])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "J.A.R.V.I.S. Memory Health" in out
    assert "status" in out
    assert "healthy" in out
    assert "memory.db" in out


def test_memory_health_json(valid_config_yaml: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["memory", "health", "--config", str(valid_config_yaml), "--json"])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert '"available": true' in out
    assert '"status": "healthy"' in out


def test_memory_health_with_invalid_config(
    invalid_config_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["memory", "health", "--config", str(invalid_config_yaml)])
    assert code == EXIT_INVALID
    assert "Configuration error:" in capsys.readouterr().err


def test_memory_stats_empty(valid_config_yaml: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["memory", "stats", "--config", str(valid_config_yaml)])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "J.A.R.V.I.S. Memory Stats" in out
    assert "total" in out
    assert "long_term" in out


def test_memory_list_empty(valid_config_yaml: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["memory", "list", "--config", str(valid_config_yaml)])
    assert code == EXIT_OK
    assert "(none)" in capsys.readouterr().out


def test_memory_get_unknown(valid_config_yaml: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["memory", "get", "mem_absent", "--config", str(valid_config_yaml)])
    assert code == EXIT_FAILURE
    assert "not found" in capsys.readouterr().err


def test_memory_delete_unknown(valid_config_yaml: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["memory", "delete", "mem_absent", "--config", str(valid_config_yaml)])
    assert code == EXIT_FAILURE
    assert "not found" in capsys.readouterr().err


def test_memory_delete_requires_id_or_filter(
    valid_config_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["memory", "delete", "--config", str(valid_config_yaml)])
    assert code == EXIT_INVALID
    assert "at least one filter" in capsys.readouterr().err


def test_memory_bulk_delete_requires_yes(
    valid_config_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        ["memory", "delete", "--type", "long_term", "--config", str(valid_config_yaml)]
    )
    assert code == EXIT_INVALID
    assert "--yes" in capsys.readouterr().err


def test_memory_crud_via_cli(valid_config_yaml: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ids = _seed_memories(valid_config_yaml)

    code = main(["memory", "list", "--config", str(valid_config_yaml)])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "cli-seed" not in out  # content hidden by default
    assert ids["coffee"][:24] in out
    assert "conf=0.95" in out

    code = main(["memory", "search", "espresso", "--config", str(valid_config_yaml)])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert ids["coffee"][:24] in out
    assert "query match: espresso" in out
    assert "preferred coffee" not in out  # content hidden by default

    code = main(["memory", "search", "espresso", "--content", "--config", str(valid_config_yaml)])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "preferred coffee is espresso" in out

    code = main(["memory", "get", ids["coffee"], "--config", str(valid_config_yaml)])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "hidden; pass --content to show" in out
    assert "espresso" not in out

    code = main(["memory", "get", ids["coffee"], "--content", "--config", str(valid_config_yaml)])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "preferred coffee is espresso" in out

    code = main(["memory", "delete", ids["fox"], "--config", str(valid_config_yaml)])
    assert code == EXIT_OK
    assert "Deleted 1 memory" in capsys.readouterr().out

    code = main(["memory", "get", ids["fox"], "--config", str(valid_config_yaml)])
    assert code == EXIT_FAILURE


def test_memory_bulk_delete_with_yes(
    valid_config_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _seed_memories(valid_config_yaml)
    code = main(
        [
            "memory", "delete",
            "--source", "cli-seed",
            "--yes",
            "--config", str(valid_config_yaml),
        ]
    )
    assert code == EXIT_OK
    assert "Deleted 2 memory" in capsys.readouterr().out
    code = main(["memory", "list", "--config", str(valid_config_yaml)])
    assert code == EXIT_OK
    assert "(none)" in capsys.readouterr().out


def test_memory_list_json(valid_config_yaml: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _seed_memories(valid_config_yaml)
    code = main(["memory", "list", "--json", "--config", str(valid_config_yaml)])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert '"total": 2' in out
    assert '"items"' in out
    assert "content" not in out  # hidden in JSON without --content
