"""Tool system models: categories, risks, decisions, schemas, requests, results.

Provider-neutral by design (spec §38): every tool declares a JSON-mappable
input/output schema; the security pipeline (registry → policy → approval →
execution) is the single path for all tool use.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from jarvis.exceptions import ToolValidationError

SCHEMA_TYPES = frozenset({"string", "integer", "number", "boolean", "array", "object"})


class ToolCategory(StrEnum):
    """Tool categories (spec §7). Only implemented ones are instantiated."""

    FILESYSTEM = "filesystem"
    PROCESS = "process"
    SYSTEM = "system"
    SHELL = "shell"
    NETWORK = "network"  # reserved for a later phase
    BROWSER = "browser"  # reserved for a later phase
    GUI = "gui"  # reserved for a later phase


class ToolRisk(StrEnum):
    """Risk declared by every tool (spec §8); no tool may omit it."""

    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ToolDecision(StrEnum):
    """Permission decisions (spec §9) — never a bare boolean."""

    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class ApprovalOutcome(StrEnum):
    """Approval provider responses (spec §12)."""

    APPROVED = "approved"
    DENIED = "denied"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@runtime_checkable
class Tool(Protocol):
    """The tool contract (spec §3): discoverable metadata + execute()."""

    id: str
    name: str
    description: str
    version: str
    risk_level: ToolRisk
    category: ToolCategory
    capabilities: tuple[str, ...]
    input_schema: dict[str, object]
    output_schema: dict[str, object]
    PATH_ARGUMENTS: tuple[str, ...] = ()

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        ...


class BaseTool:
    """Shared defaults for concrete tools (fields may be overridden)."""

    id: str = ""
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    risk_level: ToolRisk = ToolRisk.SAFE
    category: ToolCategory = ToolCategory.FILESYSTEM
    capabilities: tuple[str, ...] = ()
    PATH_ARGUMENTS: tuple[str, ...] = ()
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    output_schema: dict[str, object] = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        raise NotImplementedError(f"tool {self.id} does not implement execute")


@dataclass(frozen=True)
class ToolRequest:
    """A validated, auditable request for a single tool execution."""

    request_id: str
    tool_id: str
    arguments: dict[str, Any]
    session_id: str | None = None
    task_id: str | None = None
    source: str = "ai"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolResult:
    """Execution outcome (spec §5). success is never fabricated."""

    request_id: str
    tool_id: str
    success: bool
    output: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolContext:
    """Execution context granted by the security layer (spec §30-31).

    Tools never receive the raw process environment; `environment` is the
    scrubbed, allowlisted subset and `working_directory` is explicit.
    """

    working_directory: Path
    environment: dict[str, str]
    timeout_seconds: float
    max_output_bytes: int


# --- schema helpers -----------------------------------------------------


def validate_tool_schema(schema: object) -> None:
    """Validate a tool's input/output schema shape (spec §38, §39)."""
    if not isinstance(schema, dict):
        raise ToolValidationError("schema must be a mapping")
    if schema.get("type") != "object":
        raise ToolValidationError("schema.type must be 'object'")
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        raise ToolValidationError("schema.properties must be a mapping")
    for name, prop in properties.items():
        if not isinstance(prop, dict) or "type" not in prop:
            raise ToolValidationError(
                f"property {name!r} must declare a 'type'"
            )
        if prop["type"] not in SCHEMA_TYPES:
            raise ToolValidationError(
                f"property {name!r} has unsupported type {prop['type']!r}"
            )
    required = schema.get("required", [])
    if not isinstance(required, list) or not all(
        isinstance(item, str) for item in required
    ):
        raise ToolValidationError("schema.required must be a list of strings")
    unknown = [item for item in required if item not in properties]
    if unknown:
        raise ToolValidationError(
            f"schema.required references unknown properties: {sorted(unknown)}"
        )


def validate_arguments(arguments: Mapping[str, Any], schema: dict[str, object]) -> None:
    """Validate request arguments against the tool's input schema.

    Strict by design (spec §39): unknown arguments are rejected, required
    arguments must be present, and values must match the declared type.
    """
    if not isinstance(arguments, Mapping):
        raise ToolValidationError("arguments must be a mapping")
    properties = schema.get("properties", {})
    assert isinstance(properties, dict)
    required = schema.get("required", [])
    assert isinstance(required, list)

    unknown = sorted(set(arguments) - set(properties))
    if unknown:
        raise ToolValidationError(f"unknown arguments: {unknown}")
    for name in required:
        if name not in arguments:
            raise ToolValidationError(f"missing required argument: {name}")
    for name, value in arguments.items():
        prop = properties[name]
        assert isinstance(prop, dict)
        declared = prop["type"]
        if not _matches_json_type(declared, value):
            raise ToolValidationError(
                f"argument {name!r}: expected {declared}, got "
                f"{type(value).__name__}"
            )
        if declared == "array" and not isinstance(value, list):
            raise ToolValidationError(f"argument {name!r}: expected array")
        if declared == "array":
            items = prop.get("items")
            if isinstance(items, dict) and items.get("type"):
                for item in value:
                    if not _matches_json_type(items["type"], item):
                        raise ToolValidationError(
                            f"argument {name!r}: array items must be "
                            f"{items['type']}"
                        )


def _matches_json_type(declared: str, value: Any) -> bool:
    if declared == "boolean":
        return isinstance(value, bool)
    if declared == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if declared == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if declared == "string":
        return isinstance(value, str)
    if declared == "array":
        return isinstance(value, list)
    if declared == "object":
        return isinstance(value, dict)
    return False
