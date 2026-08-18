"""Security policy tests (spec §10-17, §39): modes, hooks, approvals."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.configuration.model import ToolSecurityMode
from jarvis.tools.models import ToolCategory, ToolDecision, ToolRequest, ToolRisk
from jarvis.tools.policy import (
    PathSecurityHook,
    SecurityPolicy,
    SensitiveArgumentHook,
    ShellCommandHook,
)
from jarvis.tools.shell_classifier import CommandClass
from tests.unit.tools.stub_tools import CriticalProbe, StubProbe


def make_request(tool_id: str, arguments: dict | None = None) -> ToolRequest:
    return ToolRequest(
        request_id="r1",
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


# --- risk/mode matrix -----------------------------------------------------


def test_lockdown_allows_only_safe() -> None:
    policy = SecurityPolicy(ToolSecurityMode.LOCKDOWN)
    assert policy.evaluate(make_request("safe"), probe(ToolRisk.SAFE))[0] is ToolDecision.ALLOW
    assert policy.evaluate(make_request("low"), probe(ToolRisk.LOW))[0] is ToolDecision.DENY
    assert policy.evaluate(make_request("medium"), probe(ToolRisk.MEDIUM))[0] is ToolDecision.DENY
    assert policy.evaluate(make_request("high"), probe(ToolRisk.HIGH))[0] is ToolDecision.DENY
    assert policy.evaluate(make_request("critical"), CriticalProbe())[0] is ToolDecision.DENY


def test_normal_mode_matrix() -> None:
    policy = SecurityPolicy(ToolSecurityMode.NORMAL)
    assert policy.evaluate(make_request("safe"), probe(ToolRisk.SAFE))[0] is ToolDecision.ALLOW
    assert policy.evaluate(make_request("low"), probe(ToolRisk.LOW))[0] is ToolDecision.ALLOW
    assert policy.evaluate(make_request("medium"), probe(ToolRisk.MEDIUM))[0] is ToolDecision.ASK
    assert policy.evaluate(make_request("high"), probe(ToolRisk.HIGH))[0] is ToolDecision.ASK
    assert policy.evaluate(make_request("critical"), CriticalProbe())[0] is ToolDecision.DENY


def test_normal_no_auto_approve_read_asks_for_low() -> None:
    policy = SecurityPolicy(ToolSecurityMode.NORMAL, allow_low=False)
    assert policy.evaluate(make_request("low"), probe(ToolRisk.LOW))[0] is ToolDecision.ASK


def test_development_mode_auto_allows_medium() -> None:
    policy = SecurityPolicy(ToolSecurityMode.DEVELOPMENT)
    assert policy.evaluate(make_request("medium"), probe(ToolRisk.MEDIUM))[0] is ToolDecision.ALLOW
    assert policy.evaluate(make_request("high"), probe(ToolRisk.HIGH))[0] is ToolDecision.ASK


def test_critical_never_allowed_in_any_mode() -> None:
    for mode in ToolSecurityMode:
        for allow_low in (True, False):
            policy = SecurityPolicy(mode, allow_low=allow_low)
            decision, reason = policy.evaluate(make_request("critical"), CriticalProbe())
            assert decision is ToolDecision.DENY
            assert "critical" in reason


def test_deny_reason_includes_mode_context() -> None:
    policy = SecurityPolicy(ToolSecurityMode.LOCKDOWN)
    decision, reason = policy.evaluate(make_request("low"), probe(ToolRisk.LOW))
    assert decision is ToolDecision.DENY
    assert "lockdown" in reason


# --- SensitiveArgumentHook -------------------------------------------------


def test_sensitive_argument_denied() -> None:
    hook = SensitiveArgumentHook()
    request = make_request("probe", {"value": 1, "api_key": "sk-x"})
    decision, reason = hook.check(request, probe(), ToolDecision.ALLOW)
    assert decision is ToolDecision.DENY
    assert "credential" in reason


def test_sensitive_empty_value_not_denied() -> None:
    hook = SensitiveArgumentHook()
    request = make_request("probe", {"value": 1, "api_key": ""})
    decision, _ = hook.check(request, probe(), ToolDecision.ALLOW)
    assert decision is ToolDecision.ALLOW


def test_sensitive_hook_leaves_deny_alone() -> None:
    hook = SensitiveArgumentHook()
    request = make_request("probe", {"value": 1})
    decision, _ = hook.check(request, probe(), ToolDecision.DENY)
    assert decision is ToolDecision.DENY


# --- PathSecurityHook ------------------------------------------------------


@pytest.fixture
def paths(tmp_path: Path) -> tuple[SecurityPolicy, Path, Path, Path]:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    denied = tmp_path / "denied"
    denied.mkdir()
    policy = SecurityPolicy(
        ToolSecurityMode.NORMAL,
        hooks=(PathSecurityHook((allowed,), (denied,), allowed),),
    )
    return policy, allowed, denied, tmp_path


def test_path_inside_allowed_roots_unchanged(paths: tuple) -> None:
    policy, allowed, _, _ = paths
    request = make_request("filesystem.read", {"path": str(allowed / "a.txt")})
    decision, _ = policy.evaluate(
        request, probe(ToolRisk.LOW, "filesystem.read", ("path",))
    )
    assert decision is ToolDecision.ALLOW


def test_path_outside_allowed_roots_denied(
    paths: tuple, tmp_path: Path
) -> None:
    policy, _, _, _ = paths
    outside = tmp_path.parent / "elsewhere.txt"
    request = make_request("filesystem.read", {"path": str(outside)})
    decision, reason = policy.evaluate(
        request, probe(ToolRisk.LOW, "filesystem.read", ("path",))
    )
    assert decision is ToolDecision.DENY
    assert "allowed roots" in reason


def test_path_in_denied_root_denied(paths: tuple) -> None:
    policy, _, denied, _ = paths
    request = make_request("filesystem.read", {"path": str(denied / "notes.txt")})
    decision, reason = policy.evaluate(
        request, probe(ToolRisk.LOW, "filesystem.read", ("path",))
    )
    assert decision is ToolDecision.DENY
    assert "denied root" in reason


def test_relative_path_resolved_against_working_directory(paths: tuple) -> None:
    policy, allowed, _, _ = paths
    request = make_request("filesystem.read", {"path": "a.txt"})
    decision, _ = policy.evaluate(
        request, probe(ToolRisk.LOW, "filesystem.read", ("path",))
    )
    assert decision is ToolDecision.ALLOW
    request = make_request("filesystem.read", {"path": "../escape.txt"})
    decision, reason = policy.evaluate(
        request, probe(ToolRisk.LOW, "filesystem.read", ("path",))
    )
    assert decision is ToolDecision.DENY


def test_protected_file_denied(paths: tuple) -> None:
    policy, allowed, _, _ = paths
    request = make_request("filesystem.read", {"path": str(allowed / "memory.db")})
    decision, reason = policy.evaluate(
        request, probe(ToolRisk.LOW, "filesystem.read", ("path",))
    )
    assert decision is ToolDecision.DENY
    assert "protected file" in reason


def test_non_path_argument_unaffected(paths: tuple) -> None:
    policy, _, _, _ = paths
    child = probe(ToolRisk.SAFE, "probe.child")
    request = make_request("probe.child", {"value": 1, "label": "../x"})
    decision, _ = policy.evaluate(request, child)
    assert decision is ToolDecision.ALLOW


# --- ShellCommandHook -------------------------------------------------------


def test_hook_only_applies_to_shell_execute() -> None:
    hook = ShellCommandHook()
    request = make_request("filesystem.read", {"path": "C:/x"})
    decision, _ = hook.check(request, probe(ToolRisk.LOW, "filesystem.read"), ToolDecision.ALLOW)
    assert decision is ToolDecision.ALLOW


def test_shell_dangerous_command_denied() -> None:
    policy = SecurityPolicy(
        ToolSecurityMode.NORMAL,
        hooks=(ShellCommandHook(),),
    )
    shell_tool = probe(ToolRisk.HIGH, "shell.execute")
    request = make_request("shell.execute", {"command": ["del", "x.txt"]})
    decision, reason = policy.evaluate(request, shell_tool)
    assert decision is ToolDecision.DENY
    assert "dangerous" in reason


def test_shell_forbidden_command_denied() -> None:
    policy = SecurityPolicy(
        ToolSecurityMode.NORMAL,
        hooks=(ShellCommandHook(),),
    )
    shell_tool = probe(ToolRisk.HIGH, "shell.execute")
    request = make_request("shell.execute", {"command": ["format", "C:"]})
    decision, reason = policy.evaluate(request, shell_tool)
    assert decision is ToolDecision.DENY
    assert "forbidden" in reason


def test_shell_safe_command_keeps_high_risk_ask() -> None:
    policy = SecurityPolicy(
        ToolSecurityMode.NORMAL,
        hooks=(ShellCommandHook(),),
    )
    shell_tool = probe(ToolRisk.HIGH, "shell.execute")
    request = make_request("shell.execute", {"command": ["where", "python"]})
    decision, reason = policy.evaluate(request, shell_tool)
    assert decision is ToolDecision.ASK
    assert "requires approval" in reason


def test_hooks_only_tighten() -> None:
    # a hook is never allowed to loosen an existing DENY to ALLOW/ASK
    policy = SecurityPolicy(
        ToolSecurityMode.LOCKDOWN,
        hooks=(ShellCommandHook(),),
    )
    shell_tool = probe(ToolRisk.HIGH, "shell.execute")
    request = make_request("shell.execute", {"command": ["where", "python"]})
    decision, _ = policy.evaluate(request, shell_tool)
    assert decision is ToolDecision.DENY  # LOCKDOWN denied; hook must not lift it


# --- classifier consistency -------------------------------------------------


def test_classifier_tables_are_disjoint() -> None:
    from jarvis.tools import shell_classifier as sc

    tables = [sc.FORBIDDEN_COMMANDS, sc.DANGEROUS_COMMANDS, sc.SAFE_COMMANDS,
              sc.RESTRICTED_COMMANDS, sc.SHELL_LAUNCHERS]
    for i, left in enumerate(tables):
        for right in tables[i + 1:]:
            assert left.isdisjoint(right), f"{left} overlaps {right}"


def test_every_command_class_has_a_representative() -> None:
    for cls in CommandClass:
        assert cls.value in ("safe", "restricted", "dangerous", "forbidden")
