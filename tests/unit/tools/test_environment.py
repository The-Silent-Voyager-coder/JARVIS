"""Controlled environment tests (spec §30, §39)."""

from __future__ import annotations

import pytest

from greatsage.exceptions import ToolValidationError
from greatsage.tools.environment import (
    is_secret_name,
    merge_environment,
    scrub_environment,
)


def test_scrub_keeps_only_allowlisted_keys() -> None:
    source = {
        "PATH": "C:/Windows/System32",
        "SYSTEMROOT": "C:/Windows",
        "OPENAI_API_KEY": "sk-secret",
        "MY_CUSTOM_VAR": "x",
        "HOME": "",
    }
    scrubbed = scrub_environment(source)
    assert set(scrubbed) == {"PATH", "SYSTEMROOT"}


def test_is_secret_name_tokens() -> None:
    assert is_secret_name("OPENAI_API_KEY")
    assert is_secret_name("my-token")
    assert is_secret_name("secret_file")
    assert is_secret_name("db_password")
    assert is_secret_name("credentials")
    assert not is_secret_name("monkey")
    assert not is_secret_name("author")
    assert not is_secret_name("PATH")
    assert not is_secret_name("working_directory")


def test_merge_rejects_nonsecret_values() -> None:
    with pytest.raises(ToolValidationError):
        merge_environment({}, {"PATH": 5})


def test_merge_rejects_secret_keys() -> None:
    with pytest.raises(ToolValidationError, match="not allowed"):
        merge_environment({}, {"OPENAI_API_KEY": "sk-secret"})
    with pytest.raises(ToolValidationError, match="not allowed"):
        merge_environment({}, {"db_password": "pw"})


def test_merge_accepts_valid_additions() -> None:
    merged = merge_environment({"PATH": "C:/"}, {"FOO": "bar", "LANG": "en"})
    assert merged == {"PATH": "C:/", "FOO": "bar", "LANG": "en"}


def test_merge_none_returns_copy() -> None:
    base = {"PATH": "C:/"}
    merged = merge_environment(base, None)
    assert merged == {"PATH": "C:/"}
    assert merged is not base


def test_payloads_never_contain_secret_values() -> None:
    # spec §32: sensitive arguments must never appear in logs or events
    secret = "sk-very-secret-value"
    scrubbed = scrub_environment({"PATH": "C:/", "OPENAI_API_KEY": secret})
    assert secret not in str(scrubbed)
