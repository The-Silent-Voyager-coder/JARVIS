"""Approval abstraction (spec §12-13).

No GUI approval exists yet: Phase 4 ships a deterministic provider for CLI
and tests. A dangerous operation without an approval provider is DENIED —
the system never assumes yes.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from greatsage.tools.models import ApprovalOutcome, Tool, ToolRequest


@runtime_checkable
class ApprovalProvider(Protocol):
    def request_approval(
        self, request: ToolRequest, tool: Tool, reason: str
    ) -> ApprovalOutcome:
        """Ask a human/policy authority; never blocks forever."""
        ...


class DeterministicApprovalProvider:
    """Scripted approval responses for CLI and deterministic tests (§12).

    The default response is DENIED so callers that forget to opt in fail
    closed.
    """

    def __init__(self, outcome: ApprovalOutcome = ApprovalOutcome.DENIED) -> None:
        self._outcome = outcome

    def request_approval(
        self, request: ToolRequest, tool: Tool, reason: str
    ) -> ApprovalOutcome:
        return self._outcome
