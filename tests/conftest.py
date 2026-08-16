"""Shared test fixtures: temporary configuration files."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def valid_config_yaml(tmp_path: Path) -> Path:
    """A minimal, valid configuration file pointing at the tmp data root."""
    path = tmp_path / "jarvis.yaml"
    d = str(tmp_path).replace("\\", "/")
    path.write_text(
        f"""
core:
  name: "J.A.R.V.I.S. Test"
  data_dir: "{d}/data"
  cache_dir: "{d}/cache"
  logs_dir: "{d}/logs"
  runtime_dir: "{d}/runtime"
  workspaces_dir: "{d}/workspaces"
  models_dir: "{d}/models"
  backups_dir: "{d}/backups"
  timezone: "UTC"
logging:
  level: "DEBUG"
  retention_days: 7
""",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def invalid_config_yaml(tmp_path: Path) -> Path:
    """A configuration file that fails validation."""
    path = tmp_path / "invalid.yaml"
    path.write_text(
        """
logging:
  level: "VERBOSE"
""",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def malformed_config_yaml(tmp_path: Path) -> Path:
    """A file that is not valid YAML."""
    path = tmp_path / "malformed.yaml"
    path.write_text("logging: [unclosed\n  level: ", encoding="utf-8")
    return path
