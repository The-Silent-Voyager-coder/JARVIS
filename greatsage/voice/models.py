"""Voice models: wake results, transcripts, speech results (Phase 6).

Local-first and bounded by design: records carry metadata + content
hashes; events and logs carry ids/lengths only — never raw audio bytes
and never full transcript text (privacy rule, mirroring the memory
subsystem). The CLI prints transcript text explicitly because the user
invoked it; nothing else does.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from greatsage.exceptions import VoiceValidationError

_SECRET_LIKE_RE = re.compile(
    r"(?i)(api[_-]?key|password|token|secret|authorization|bearer)\s*[:=]\s*\S+"
)


def redact_text(value: str) -> str:
    """Mask secret-shaped fragments before text reaches logs."""
    return _SECRET_LIKE_RE.sub(r"\1=***", value)


def transcript_digest(text: str) -> str:
    """Stable sha256 over transcript text (for records, not events)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class VoiceBackend(StrEnum):
    """STT/TTS backends. Only local, zero-cost backends are permitted."""

    MOCK = "mock"
    OFFLINE = "offline"


def new_utterance_id() -> str:
    """Generate a non-sequential utterance id."""
    return f"vtt_{uuid.uuid4().hex}"


@dataclass(frozen=True)
class WakeResult:
    """Outcome of one bounded wake-word check."""

    detected: bool
    keyword: str
    confidence: float
    backend: VoiceBackend = VoiceBackend.MOCK
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def validate(self) -> None:
        if not self.keyword:
            raise VoiceValidationError("wake keyword must not be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise VoiceValidationError(f"wake confidence must be in 0..1, got {self.confidence}")
        if self.created_at.tzinfo is None:
            raise VoiceValidationError("wake created_at must be timezone-aware")

    def to_dict(self) -> dict[str, Any]:
        return {
            "detected": self.detected,
            "keyword": self.keyword,
            "confidence": self.confidence,
            "backend": self.backend.value,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class Transcript:
    """One bounded speech-to-text result.

    Full text lives in the repository / CLI output only; events and logs
    carry `id`, `backend`, `text_chars`, and `sha256` — never `text`.
    """

    id: str
    backend: VoiceBackend
    text: str
    text_chars: int
    sha256: str
    duration_ms: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.id.startswith("vtt_") or len(self.id) != 36:
            raise VoiceValidationError(f"invalid utterance id: {self.id!r}")
        if not self.text:
            raise VoiceValidationError("transcript text must not be empty")
        if self.text_chars != len(self.text):
            raise VoiceValidationError("transcript text_chars does not match text length")
        if len(self.sha256) != 64 or any(c not in "0123456789abcdef" for c in self.sha256):
            raise VoiceValidationError("transcript sha256 must be 64 lowercase hex chars")
        if self.duration_ms < 0:
            raise VoiceValidationError("transcript duration_ms must be non-negative")
        if self.created_at.tzinfo is None:
            raise VoiceValidationError("transcript created_at must be timezone-aware")

    def to_dict(self, *, include_text: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "backend": self.backend.value,
            "text_chars": self.text_chars,
            "sha256": self.sha256,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at.isoformat(),
            "metadata": dict(self.metadata),
        }
        if include_text:
            data["text"] = self.text
        return data


@dataclass(frozen=True)
class SpeechResult:
    """One bounded text-to-speech result (metadata; audio bytes stay in files)."""

    id: str
    backend: VoiceBackend
    text_chars: int
    sha256: str
    size_bytes: int
    format: str = "wav"
    duration_ms: float = 0.0
    output_path: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.id.startswith("vtt_") or len(self.id) != 36:
            raise VoiceValidationError(f"invalid utterance id: {self.id!r}")
        if self.text_chars <= 0:
            raise VoiceValidationError("speech text_chars must be positive")
        if len(self.sha256) != 64 or any(c not in "0123456789abcdef" for c in self.sha256):
            raise VoiceValidationError("speech sha256 must be 64 lowercase hex chars")
        if self.size_bytes <= 0:
            raise VoiceValidationError("speech size_bytes must be positive")
        if self.format != "wav":
            raise VoiceValidationError(f"unsupported speech format: {self.format!r}")
        if self.duration_ms < 0:
            raise VoiceValidationError("speech duration_ms must be non-negative")
        if self.created_at.tzinfo is None:
            raise VoiceValidationError("speech created_at must be timezone-aware")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "backend": self.backend.value,
            "text_chars": self.text_chars,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "format": self.format,
            "duration_ms": self.duration_ms,
            "output_path": self.output_path,
            "created_at": self.created_at.isoformat(),
            "metadata": dict(self.metadata),
        }


def sanitize_audio_path(value: str | Path, *, suffix: str = ".wav") -> Path:
    """Validate an explicit audio file path (no secrets, fixed suffix)."""
    path = Path(value)
    if path.suffix.lower() != suffix:
        raise VoiceValidationError(f"audio path must be a {suffix} path, got {path.suffix!r}")
    return path
