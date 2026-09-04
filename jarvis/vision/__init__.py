"""Bounded local-first vision (Phase 8): capture, grounding stubs, service."""

from jarvis.vision.capture import CaptureManager, StubCaptureBackend
from jarvis.vision.file_repository import FileVisionRepository
from jarvis.vision.grounding import GroundingStub
from jarvis.vision.limits import VisionLimits, default_limits, resolve_limits
from jarvis.vision.models import (
    VisionBackend,
    VisionCapture,
    VisionDescription,
    VisionRegion,
)
from jarvis.vision.repository import VisionRepository
from jarvis.vision.service import VisionService
from jarvis.vision.tools import (
    VisionCaptureTool,
    VisionDescribeTool,
    register_vision_tools,
)

__all__ = [
    "CaptureManager",
    "FileVisionRepository",
    "GroundingStub",
    "StubCaptureBackend",
    "VisionBackend",
    "VisionCapture",
    "VisionCaptureTool",
    "VisionDescribeTool",
    "VisionDescription",
    "VisionLimits",
    "VisionRegion",
    "VisionRepository",
    "VisionService",
    "default_limits",
    "register_vision_tools",
    "resolve_limits",
]
