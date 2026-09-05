"""Phase 9 security-hardening regression tests.

Covers, without touching existing ALLOW/ASK/DENY semantics:
- protected-file set extensions (`.env.*`, `.envrc`, sqlite sidecars) and
  template exceptions (`.env.example`);
- protected-file denial on *every* declared path argument (incl. shell `cwd`);
- sensitive-value denial (`env` values, `command` argv items);
- shell classifier tightening (OS installers, LOLBins, encoded PowerShell,
  `git config` no longer read-only);
- secret redaction helper (masks formats, leaves prose alone).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.configuration.model import ToolSecurityMode
from jarvis.tools import shell_classifier as sc
from jarvis.tools.models import ToolCategory, ToolDecision, ToolRequest, ToolRisk
from jarvis.tools.pathsecurity import is_protected_path
from jarvis.tools.policy import (
    PathSecurityHook,
    SecurityPolicy,
    SensitiveArgumentHook,
)
from jarvis.tools.redaction import looks_like_secret_value, redact_secrets
from jarvis.tools.shell_classifier import CommandClass, classify_command
from tests.unit.tools.stub_tools import StubProbe


def make_request(tool_id: str, arguments: dict | None = None) -> ToolRequest:
    return ToolRequest(
        request_id="r9",
        tool_id=tool_id,
        arguments=arguments or {},
        source="test",
    )


def probe(
    risk: ToolRisk = ToolRisk.SAFE,
    name: str = "probe.info",
    path_arguments: tuple[str, ...] = (),
) -> StubProbe:
    return StubProbe(
        name=name,
        description=f"{name} probe",
        category=ToolCategory.SYSTEM,
        risk=risk,
        path_arguments=path_arguments,
    )


# --- protected-file set ------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        ".env.local",
        ".env.production",
        ".ENV.STAGING",
        ".envrc",
        "memory.db-wal",
        "memory.db-journal",
        "memory.db-shm",
    ],
)
def test_phase9_protected_names(tmp_path: Path, name: str) -> None:
    assert is_protected_path(tmp_path / name)


@pytest.mark.parametrize(
    "name",
    [".env.example", ".env.sample", ".env.template"],
)
def test_phase9_template_names_not_protected(tmp_path: Path, name: str) -> None:
    assert not is_protected_path(tmp_path / name)


# --- protected check applies to every path argument --------------------------


@pytest.fixture
def roots(tmp_path: Path) -> tuple[Path, Path]:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    denied = tmp_path / "denied"
    denied.mkdir()
    return allowed, denied


def test_phase9_protected_cwd_denied(roots: tuple[Path, Path]) -> None:
    allowed, denied = roots
    policy = SecurityPolicy(
        ToolSecurityMode.NORMAL,
        hooks=(PathSecurityHook((allowed,), (denied,), allowed),),
    )
    shell_tool = probe(ToolRisk.HIGH, "shell.execute", ("cwd",))
    request = make_request("shell.execute", {"cwd": str(allowed / ".env")})
    decision, reason = policy.evaluate(request, shell_tool)
    assert decision is ToolDecision.DENY
    assert "protected file" in reason


def test_phase9_protected_env_variant_denied_via_cwd(
    roots: tuple[Path, Path],
) -> None:
    allowed, denied = roots
    policy = SecurityPolicy(
        ToolSecurityMode.NORMAL,
        hooks=(PathSecurityHook((allowed,), (denied,), allowed),),
    )
    shell_tool = probe(ToolRisk.HIGH, "shell.execute", ("cwd",))
    request = make_request("shell.execute", {"cwd": str(allowed / ".env.local")})
    decision, _ = policy.evaluate(request, shell_tool)
    assert decision is ToolDecision.DENY


# --- sensitive-value denial ---------------------------------------------------


def test_phase9_env_secret_value_denied() -> None:
    hook = SensitiveArgumentHook()
    request = make_request(
        "shell.execute",
        {"command": ["where", "python"], "env": {"MY_SETTING": "sk-live-abcdefghij123456"}},
    )
    decision, reason = hook.check(request, probe(), ToolDecision.ALLOW)
    assert decision is ToolDecision.DENY
    assert "credential" in reason


def test_phase9_env_secret_key_denied() -> None:
    hook = SensitiveArgumentHook()
    request = make_request(
        "shell.execute",
        {"command": ["where", "python"], "env": {"MY_API_KEY": "plain-value"}},
    )
    decision, _ = hook.check(request, probe(), ToolDecision.ALLOW)
    assert decision is ToolDecision.DENY


def test_phase9_command_argv_secret_denied() -> None:
    hook = SensitiveArgumentHook()
    request = make_request(
        "shell.execute",
        {"command": ["curl", "-H", "Authorization: Bearer sk-live-abcdefghij123456"]},
    )
    decision, reason = hook.check(request, probe(), ToolDecision.ALLOW)
    assert decision is ToolDecision.DENY
    assert "credential" in reason


def test_phase9_benign_env_and_argv_allowed() -> None:
    hook = SensitiveArgumentHook()
    request = make_request(
        "shell.execute",
        {"command": ["where", "python"], "env": {"MY_SETTING": "verbose"}},
    )
    decision, _ = hook.check(request, probe(), ToolDecision.ALLOW)
    assert decision is ToolDecision.ALLOW


def test_phase9_prose_with_password_word_allowed() -> None:
    # Ordinary prose must not trip value scanning — only secret *formats*.
    hook = SensitiveArgumentHook()
    request = make_request(
        "probe.write", {"content": "document the password policy for onboarding"}
    )
    decision, _ = hook.check(request, probe(), ToolDecision.ALLOW)
    assert decision is ToolDecision.ALLOW


# --- classifier tightening ----------------------------------------------------


@pytest.mark.parametrize(
    "exe",
    [
        "msiexec",
        "winget",
        "choco",
        "scoop",
        "mshta",
        "wscript",
        "cscript",
        "bitsadmin",
        "schtasks",
        "wevtutil",
        "regsvr32",
        "cmstp",
        "takeown",
    ],
)
def test_phase9_dangerous_commands(exe: str) -> None:
    assert classify_command([exe, "anything"]) is CommandClass.DANGEROUS


@pytest.mark.parametrize(
    "flag",
    ["-EncodedCommand", "-enc", "-ec"],
)
def test_phase9_encoded_powershell_forbidden(flag: str) -> None:
    assert classify_command(["powershell", flag, "aGVsbG8="]) is CommandClass.FORBIDDEN
    assert classify_command(["pwsh", flag, "aGVsbG8="]) is CommandClass.FORBIDDEN


def test_phase9_plain_powershell_stays_dangerous() -> None:
    assert classify_command(["powershell", "-NoProfile", "-File", "x.ps1"]) is (
        CommandClass.DANGEROUS
    )


def test_phase9_git_config_not_read_only() -> None:
    assert classify_command(["git", "config", "--list"]) is CommandClass.RESTRICTED
    assert classify_command(["git", "status"]) is CommandClass.SAFE


def test_phase9_classifier_tables_still_disjoint() -> None:
    tables = [
        sc.FORBIDDEN_COMMANDS,
        sc.DANGEROUS_COMMANDS,
        sc.SAFE_COMMANDS,
        sc.RESTRICTED_COMMANDS,
        sc.SHELL_LAUNCHERS,
    ]
    for i, left in enumerate(tables):
        for right in tables[i + 1 :]:
            assert left.isdisjoint(right)


# --- redaction ----------------------------------------------------------------


def test_phase9_redaction_masks_formats() -> None:
    assert redact_secrets("key=sk-live-abcdefghij123456") == "key=[REDACTED:api_key]"
    assert "AKIAIOSFODNN7EXAMPLE" not in str(redact_secrets("id AKIAIOSFODNN7EXAMPLE here"))
    assert "PRIVATE KEY" not in str(redact_secrets("-----BEGIN RSA PRIVATE KEY-----"))
    assert "ghp_" not in str(redact_secrets("token ghp_abcdefghij1234567890xy here"))


def test_phase9_redaction_leaves_prose() -> None:
    text = "document the password policy; token_dbg is a test placeholder"
    assert redact_secrets(text) == text
    assert redact_secrets(None) is None
    assert redact_secrets("") == ""


def test_phase9_looks_like_secret_value() -> None:
    assert looks_like_secret_value("sk-live-abcdefghij123456")
    assert not looks_like_secret_value("just a normal sentence")
    assert not looks_like_secret_value("")
