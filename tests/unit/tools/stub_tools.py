"""Shared stubs for tools tests (dummy Tool implementations)."""

from __future__ import annotations

from jarvis.tools.models import (
    ApprovalOutcome,
    BaseTool,
    ToolCategory,
    ToolContext,
    ToolRequest,
    ToolResult,
    ToolRisk,
)

INPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"value": {"type": "integer"}},
    "required": ["value"],
}

OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"value": {"type": "integer"}},
    "required": ["value"],
}


class StubProbe(BaseTool):
    """Minimal deterministic tool that echoes its argument."""

    def __init__(
        self,
        name: str,
        description: str,
        category: ToolCategory,
        risk: ToolRisk = ToolRisk.SAFE,
        path_arguments: tuple[str, ...] = (),
    ) -> None:
        self.id = name
        self.name = name
        self.description = description
        self.category = category
        self.risk_level = risk
        self.capabilities = ("probe",)
        self.PATH_ARGUMENTS = path_arguments
        self.input_schema = INPUT_SCHEMA
        self.output_schema = OUTPUT_SCHEMA
        self._executions: list[tuple[ToolContext, dict]] = []

    def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        self._executions.append((context, dict(arguments)))
        return ToolResult(self.id, self.id, True, output={"value": arguments.get("value")})


class FailingProbe(BaseTool):
    """Probe that always raises an unexpected exception."""

    def __init__(self, name: str = "probe.failing") -> None:
        self.id = name
        self.name = name
        self.description = "failing probe"
        self.category = ToolCategory.SYSTEM
        self.risk_level = ToolRisk.SAFE
        self.capabilities = ("probe",)
        self.input_schema = INPUT_SCHEMA
        self.output_schema = OUTPUT_SCHEMA

    def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        raise RuntimeError("boom")


class CriticalProbe(BaseTool):
    """CRITICAL-risk probe used to prove critical tools are never allowed."""

    def __init__(self, name: str = "probe.critical") -> None:
        self.id = name
        self.name = name
        self.description = "critical probe"
        self.category = ToolCategory.SYSTEM
        self.risk_level = ToolRisk.CRITICAL
        self.capabilities = ("probe",)
        self.input_schema = INPUT_SCHEMA
        self.output_schema = OUTPUT_SCHEMA

    def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        return ToolResult(self.id, self.id, True, output={"value": 1})


class RecordingApprovalProvider:
    """Approval provider with configurable outcome + recorded decisions."""

    def __init__(self, outcome: ApprovalOutcome = ApprovalOutcome.APPROVED) -> None:
        self._outcome = outcome
        self.decisions: list[ToolRequest] = []

    def request_approval(
        self, request: ToolRequest, tool: object, reason: str | None = None
    ) -> ApprovalOutcome:
        self.decisions.append(request)
        return self._outcome


class EventRecorder:
    """Captures events published by ToolService."""

    def __init__(self) -> None:
        self.events: list[object] = []
        self.types: list[str] = []

    def __call__(self, event: object) -> None:
        self.events.append(event)
        self.types.append(getattr(event, "type", "?"))

    def count(self, event_type: str) -> int:
        return sum(1 for t in self.types if t == event_type)
