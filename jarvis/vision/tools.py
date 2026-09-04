"""Permissioned vision tools (Phase 8).

`vision.capture` / `vision.describe` run through the standard ToolService
security pipeline like every other tool: registry → policy → approval →
execution → audit events. Risk is SAFE (READ-class); path arguments are
declared in PATH_ARGUMENTS so allowed/denied roots are enforced by policy
before execution. Outputs are metadata only — pixel bytes never flow
through tool results, events, or logs.

Wire-up (for integration-qa): `register_vision_tools(registry)`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jarvis.exceptions import VisionError
from jarvis.tools.models import BaseTool, ToolCategory, ToolContext, ToolResult, ToolRisk
from jarvis.tools.registry import ToolRegistry
from jarvis.vision.capture import CaptureManager, StubCaptureBackend, parse_bmp_dimensions
from jarvis.vision.grounding import GroundingStub
from jarvis.vision.limits import (
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    MAX_HEIGHT,
    MAX_WIDTH,
    VisionLimits,
    default_limits,
)
from jarvis.vision.models import sanitize_output_path


def _failure(tool_id: str, error: str) -> ToolResult:
    return ToolResult(request_id="", tool_id=tool_id, success=False, error=error[:500])


class VisionCaptureTool(BaseTool):
    """Capture a bounded local frame; returns metadata, never pixels."""

    id = "vision.capture"
    name = "Vision capture"
    description = "Capture a bounded local screen frame (stub backend, BMP)."
    version = "1.0.0"
    risk_level = ToolRisk.SAFE
    category = ToolCategory.SYSTEM
    capabilities = ("observe",)
    PATH_ARGUMENTS = ("output_path",)
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "width": {"type": "integer"},
            "height": {"type": "integer"},
            "output_path": {"type": "string"},
        },
        "required": [],
    }
    output_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "backend": {"type": "string"},
            "width": {"type": "integer"},
            "height": {"type": "integer"},
            "format": {"type": "string"},
            "size_bytes": {"type": "integer"},
            "output_path": {"type": "string"},
        },
        "required": ["backend", "width", "height", "format", "size_bytes"],
    }

    def __init__(self, limits: VisionLimits | None = None) -> None:
        self._limits = limits or default_limits()

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        width = int(arguments.get("width", DEFAULT_WIDTH))
        height = int(arguments.get("height", DEFAULT_HEIGHT))
        manager = CaptureManager(limits=self._limits, backend=StubCaptureBackend())
        try:
            image, meta = manager.capture(width, height)
        except VisionError as exc:
            return _failure(self.id, str(exc))
        output: dict[str, Any] = {
            "backend": meta["backend"],
            "width": meta["width"],
            "height": meta["height"],
            "format": meta["format"],
            "size_bytes": meta["size_bytes"],
        }
        raw_path = arguments.get("output_path")
        if raw_path is not None:
            try:
                target = sanitize_output_path(str(raw_path))
            except VisionError as exc:
                return _failure(self.id, str(exc))
            if not target.is_absolute():
                return _failure(self.id, "output_path must be absolute")
            if not target.parent.exists():
                return _failure(
                    self.id,
                    "output directory does not exist; create it first through the file tools",
                )
            try:
                target.write_bytes(image)
            except OSError as exc:
                return _failure(self.id, f"cannot write output_path: {exc}")
            output["output_path"] = str(target)
        _ = context
        return ToolResult(request_id="", tool_id=self.id, success=True, output=output)


class VisionDescribeTool(BaseTool):
    """OCR-free stub description of a stored BMP frame."""

    id = "vision.describe"
    name = "Vision describe"
    description = "Describe a BMP frame with deterministic layout stubs (no OCR)."
    version = "1.0.0"
    risk_level = ToolRisk.SAFE
    category = ToolCategory.SYSTEM
    capabilities = ("observe",)
    PATH_ARGUMENTS = ("capture_path",)
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "capture_path": {"type": "string"},
            "max_regions": {"type": "integer"},
        },
        "required": ["capture_path"],
    }
    output_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "regions": {"type": "array"},
            "truncated": {"type": "boolean"},
        },
        "required": ["summary", "regions", "truncated"],
    }

    def __init__(self, limits: VisionLimits | None = None) -> None:
        self._limits = limits or default_limits()

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        _ = context
        raw = arguments.get("capture_path")
        if not isinstance(raw, str) or not raw:
            return _failure(self.id, "capture_path must be a non-empty string")
        path = Path(raw)
        if path.suffix.lower() != ".bmp":
            return _failure(self.id, "capture_path must point at a .bmp file")
        try:
            image = path.read_bytes()
        except OSError as exc:
            return _failure(self.id, f"cannot read capture_path: {exc}")
        if len(image) > self._limits.max_image_bytes:
            return _failure(
                self.id,
                f"frame is {len(image)} bytes, over the {self._limits.max_image_bytes}-byte limit",
            )
        try:
            width, height = parse_bmp_dimensions(image)
        except VisionError as exc:
            return _failure(self.id, str(exc))
        if width > MAX_WIDTH or height > MAX_HEIGHT:
            return _failure(self.id, f"frame {width}x{height} exceeds {MAX_WIDTH}x{MAX_HEIGHT}")
        max_regions = arguments.get("max_regions")
        if max_regions is not None and (not isinstance(max_regions, int) or max_regions <= 0):
            return _failure(self.id, "max_regions must be a positive integer")
        description = GroundingStub(limits=self._limits).describe(
            "cap_" + "0" * 32,
            width,
            height,
            max_regions=max_regions,
        )
        return ToolResult(
            request_id="",
            tool_id=self.id,
            success=True,
            output={
                "summary": description.summary,
                "regions": [r.to_dict() for r in description.regions],
                "truncated": description.truncated,
            },
        )


VISION_TOOL_CLASSES: tuple[type, ...] = (
    VisionCaptureTool,
    VisionDescribeTool,
)


def register_vision_tools(registry: ToolRegistry) -> None:
    """Register Phase 8 vision tools into `registry` (duplicates raise)."""
    for tool_class in VISION_TOOL_CLASSES:
        registry.register(tool_class())
