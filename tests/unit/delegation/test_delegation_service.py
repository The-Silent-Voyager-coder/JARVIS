"""DelegationService facade tests: lifecycle, health, gating, and routing.

Offline and deterministic: the fake provider is pure in-process and the
approval provider is scripted. Proves the facade wires the DelegationManager
to the Phase 4 security pipeline exactly like the agent and CLI do.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from jarvis.configuration.loader import load_config
from jarvis.core.health import HealthRegistry, HealthStatus
from jarvis.delegation.models import (
    DelegationEvent,
    DelegationEventKind,
    DelegationRequest,
    DelegationState,
)
from jarvis.delegation.service import DelegationService
from jarvis.exceptions import (
    DelegationUnavailableError,
    DelegationValidationError,
)
from jarvis.intelligence.registry import ProviderRegistry
from jarvis.tools.approval import DeterministicApprovalProvider
from jarvis.tools.models import ApprovalOutcome
from tests.unit.delegation.test_delegation_manager import (
    FakeDelegationProvider,
    approved_wd,
    write_delegation_config,
)


class FakeIntelligenceService:
    """Minimal IntelligenceService surface: just the provider registry."""

    def __init__(self, registry: ProviderRegistry) -> None:
        self.registry = registry


class FakeToolService:
    """Minimal ToolService surface: the Phase 4 approval provider."""

    def __init__(self, approval: Any = None) -> None:
        self.approval = approval


def _service(
    tmp_path: Path,
    *,
    enabled: bool = True,
    wired: bool = True,
    provider: FakeDelegationProvider | None = None,
) -> DelegationService:
    config = load_config(
        write_delegation_config(tmp_path, enabled=enabled)
    ).config
    if not wired:
        return DelegationService()
    agent = FakeIntelligenceService(ProviderRegistry())
    service = DelegationService(intelligence=agent, tools=FakeToolService())
    service.start(config)
    return service


def test_unavailable_before_start(tmp_path: Path) -> None:
    service = DelegationService()
    health = service.health()
    assert health["status"] == "unavailable"
    assert health["available"] is False
    with pytest.raises(DelegationUnavailableError, match="not started"):
        service.delegate(
            DelegationRequest(prompt="fix", working_directory=approved_wd(tmp_path))
        )
    with pytest.raises(DelegationUnavailableError):
        service.cancel("task-1")
    with pytest.raises(DelegationUnavailableError):
        service.get("task-1")
    with pytest.raises(DelegationUnavailableError):
        service.list_tasks()


def test_disabled_by_config(tmp_path: Path) -> None:
    service = _service(tmp_path, enabled=False)
    health = service.health()
    assert health["status"] == "disabled"
    assert health["available"] is False
    assert health["enabled"] is False
    with pytest.raises(DelegationUnavailableError, match="disabled"):
        service.delegate(
            DelegationRequest(prompt="fix", working_directory=approved_wd(tmp_path))
        )


def test_unwired_dependencies_unavailable(tmp_path: Path) -> None:
    config = load_config(write_delegation_config(tmp_path)).config
    service = DelegationService()
    service.start(config)  # deps are None -> unavailable
    assert service.health()["status"] == "unavailable"


def test_start_without_config_unavailable() -> None:
    service = DelegationService()
    service.start(None)
    assert service.health()["status"] == "unavailable"


def test_healthy_lifecycle_and_health_shape(tmp_path: Path) -> None:
    provider = FakeDelegationProvider(
        events=[DelegationEvent(kind=DelegationEventKind.COMPLETED, message="x")]
    )
    config = load_config(write_delegation_config(tmp_path)).config
    registry = ProviderRegistry()
    registry.register(provider)
    service = DelegationService(
        intelligence=FakeIntelligenceService(registry), tools=FakeToolService()
    )
    service.start(config)
    health = service.health()
    assert health["available"] is True
    assert health["status"] == "healthy"
    assert health["enabled"] is True
    assert health["default_provider"] == "opencode-fake"
    assert "max_delegation_depth" in health["limits"]

    result = service.delegate(
        DelegationRequest(prompt="fix", working_directory=approved_wd(tmp_path))
    )
    assert result.state is DelegationState.COMPLETED

    tasks = service.list_tasks()
    assert tasks and tasks[0]["state"] == "completed"

    snapshot = service.get(result.task_id)
    assert snapshot["state"] == "completed"

    service.shutdown()
    assert service.health()["status"] == "disabled"
    with pytest.raises(DelegationUnavailableError, match="stopped"):
        service.delegate(
            DelegationRequest(prompt="fix", working_directory=approved_wd(tmp_path))
        )


def test_delegate_routes_permissions_through_tool_approval(tmp_path: Path) -> None:
    # The facade must use the ToolService's approval provider for permission
    # decisions (the same one the agent/CLI use), never its own policy.
    recorder_approval = DeterministicApprovalProvider(ApprovalOutcome.APPROVED)
    provider = FakeDelegationProvider(
        events=[
            DelegationEvent(
                kind=DelegationEventKind.PERMISSION_REQUESTED,
                metadata={
                    "permission_id": "perm-1",
                    "action": "bash",
                    "path": None,
                },
                message="run a command",
            ),
            DelegationEvent(kind=DelegationEventKind.COMPLETED, message="done"),
        ]
    )
    config = load_config(write_delegation_config(tmp_path)).config
    registry = ProviderRegistry()
    registry.register(provider)
    tools = FakeToolService(approval=recorder_approval)
    service = DelegationService(intelligence=FakeIntelligenceService(registry), tools=tools)
    service.start(config)
    result = service.delegate(
        DelegationRequest(prompt="fix", working_directory=approved_wd(tmp_path))
    )
    assert result.state is DelegationState.COMPLETED
    assert provider.responded == [("sess-fake-1", "perm-1", True)]


def test_register_health_check(tmp_path: Path) -> None:
    registry = HealthRegistry()
    service = _service(tmp_path)
    service.register_health_check(registry)
    assert registry.check("delegation").status is HealthStatus.HEALTHY

    unstarted = DelegationService()
    unstarted.register_health_check(registry)
    assert registry.check("delegation").status is HealthStatus.UNHEALTHY


def test_unknown_task_raises(tmp_path: Path) -> None:
    service = _service(tmp_path)
    # The facade is healthy but no tasks exist: get/cancel on an unknown id
    # must surface the manager's validation error, not a facade error.
    with pytest.raises(DelegationValidationError, match="unknown"):
        service.get("nope")
    with pytest.raises(DelegationValidationError, match="unknown"):
        service.cancel("nope")
