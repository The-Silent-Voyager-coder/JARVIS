"""Tool registry (spec §6): registration, lookup, enumeration, inspection.

Duplicate ids are rejected at registration; schemas are validated when a tool
is registered so a broken tool can never be discovered as healthy.
"""

from __future__ import annotations

from typing import Any

from jarvis.exceptions import ToolNotFoundError, ToolValidationError
from jarvis.tools.models import Tool, validate_tool_schema


class ToolRegistry:
    """Owns the set of registered tools and their metadata."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if not tool.id:
            raise ToolValidationError("tool id must be a non-empty string")
        if tool.id in self._tools:
            raise ToolValidationError(f"duplicate tool id: {tool.id}")
        if not isinstance(tool, Tool):
            raise ToolValidationError(
                f"tool {tool.id!r} does not implement the Tool contract"
            )
        validate_tool_schema(tool.input_schema)
        validate_tool_schema(tool.output_schema)
        self._tools[tool.id] = tool

    def unregister(self, tool_id: str) -> bool:
        return self._tools.pop(tool_id, None) is not None

    def get(self, tool_id: str) -> Tool:
        try:
            return self._tools[tool_id]
        except KeyError as exc:
            raise ToolNotFoundError(f"unknown tool: {tool_id}") from exc

    def list_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def enumerate(self) -> tuple[Tool, ...]:
        return tuple(self._tools[tool_id] for tool_id in self.list_ids())

    def describe(self, tool_id: str) -> dict[str, Any]:
        """Full metadata for a tool (schemas included); never secrets."""
        tool = self.get(tool_id)
        return {
            "id": tool.id,
            "name": tool.name,
            "description": tool.description,
            "version": tool.version,
            "risk_level": tool.risk_level.value,
            "category": tool.category.value,
            "capabilities": list(tool.capabilities),
            "input_schema": tool.input_schema,
            "output_schema": tool.output_schema,
        }

    def health(self) -> dict[str, Any]:
        return {
            "status": "healthy",
            "tool_count": len(self._tools),
            "tools": self.list_ids(),
        }
