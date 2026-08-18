"""Structured, serializable event envelope and canonical event types.

Event type constants follow the Phase 0 documented catalog. Payloads are
JSON-serializable dictionaries.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# --- Canonical event types (Phase 0 catalog + Phase 1 lifecycle events) ---

USER_MESSAGE_RECEIVED = "UserMessageReceived"
VOICE_WAKE_DETECTED = "VoiceWakeDetected"
SPEECH_TRANSCRIBED = "SpeechTranscribed"
AI_RESPONSE_STARTED = "AIResponseStarted"
AI_RESPONSE_COMPLETED = "AIResponseCompleted"
TOOL_REQUESTED = "ToolRequested"
TOOL_STARTED = "ToolStarted"
TOOL_COMPLETED = "ToolCompleted"
TOOL_FAILED = "ToolFailed"
TASK_CREATED = "TaskCreated"
TASK_STARTED = "TaskStarted"
TASK_PAUSED = "TaskPaused"
TASK_COMPLETED = "TaskCompleted"
TASK_FAILED = "TaskFailed"
OPENCODE_CONNECTED = "OpenCodeConnected"
OPENCODE_DISCONNECTED = "OpenCodeDisconnected"
OPENCODE_EVENT_RECEIVED = "OpenCodeEventReceived"
MEMORY_CREATED = "MemoryCreated"
MEMORY_RETRIEVED = "MemoryRetrieved"
PERMISSION_REQUESTED = "PermissionRequested"
PERMISSION_GRANTED = "PermissionGranted"
PERMISSION_DENIED = "PermissionDenied"

RUNTIME_STARTED = "RuntimeStarted"
RUNTIME_STOPPING = "RuntimeStopping"
RUNTIME_STOPPED = "RuntimeStopped"

# Phase 2 — intelligence layer
AI_REQUEST_STARTED = "AIRequestStarted"
AI_REQUEST_COMPLETED = "AIRequestCompleted"
AI_REQUEST_FAILED = "AIRequestFailed"
AI_PROVIDER_SELECTED = "AIProviderSelected"
AI_PROVIDER_UNAVAILABLE = "AIProviderUnavailable"
AI_STREAM_STARTED = "AIStreamStarted"
AI_STREAM_COMPLETED = "AIStreamCompleted"
AI_STREAM_FAILED = "AIStreamFailed"

DOCUMENTED_EVENT_TYPES: frozenset[str] = frozenset(
    {
        USER_MESSAGE_RECEIVED,
        VOICE_WAKE_DETECTED,
        SPEECH_TRANSCRIBED,
        AI_RESPONSE_STARTED,
        AI_RESPONSE_COMPLETED,
        TOOL_REQUESTED,
        TOOL_STARTED,
        TOOL_COMPLETED,
        TOOL_FAILED,
        TASK_CREATED,
        TASK_STARTED,
        TASK_PAUSED,
        TASK_COMPLETED,
        TASK_FAILED,
        OPENCODE_CONNECTED,
        OPENCODE_DISCONNECTED,
        OPENCODE_EVENT_RECEIVED,
        MEMORY_CREATED,
        MEMORY_RETRIEVED,
        PERMISSION_REQUESTED,
        PERMISSION_GRANTED,
        PERMISSION_DENIED,
        RUNTIME_STARTED,
        RUNTIME_STOPPING,
        RUNTIME_STOPPED,
        AI_REQUEST_STARTED,
        AI_REQUEST_COMPLETED,
        AI_REQUEST_FAILED,
        AI_PROVIDER_SELECTED,
        AI_PROVIDER_UNAVAILABLE,
        AI_STREAM_STARTED,
        AI_STREAM_COMPLETED,
        AI_STREAM_FAILED,
    }
)


@dataclass(frozen=True)
class Event:
    """Immutable, JSON-serializable event envelope."""

    type: str
    source: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    session_id: str | None = None
    task_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        return cls(
            id=str(data["id"]),
            type=str(data["type"]),
            timestamp=datetime.fromisoformat(str(data["timestamp"])),
            source=str(data["source"]),
            session_id=data.get("session_id"),
            task_id=data.get("task_id"),
            payload=dict(data.get("payload") or {}),
        )
