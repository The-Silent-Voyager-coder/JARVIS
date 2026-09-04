"""Speech-to-text abstraction (Phase 6).

Stdlib only, zero-cost, local-first. The active backend is a
deterministic mock: text input is echoed with a `[mock-stt]` marker and
WAV input yields a deterministic placeholder transcript derived from
the audio bytes. No model download, no cloud API is ever required. A
real offline engine (e.g. a local whisper.cpp binary) may be added
later behind the same `STTBackend` ABC without changing callers.
"""

from __future__ import annotations

import hashlib
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from jarvis.exceptions import VoiceTimeoutError, VoiceValidationError
from jarvis.voice.limits import VoiceLimits, default_limits
from jarvis.voice.models import Transcript, VoiceBackend, new_utterance_id, transcript_digest

log = logging.getLogger("jarvis.voice.stt")

STT_MOCK_PREFIX = "[mock-stt]"
WAV_MIN_BYTES = 44


def is_wav_bytes(data: bytes) -> bool:
    """Accept RIFF/WAVE headers only; everything else is rejected."""
    return len(data) >= WAV_MIN_BYTES and data[0:4] == b"RIFF" and data[8:12] == b"WAVE"


class STTBackend(ABC):
    """Pluggable transcription source; callers never touch engines directly."""

    name: str = "abstract"
    backend: VoiceBackend = VoiceBackend.MOCK

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def transcribe_text(self, text: str) -> tuple[str, dict[str, Any]]:
        """Transcribe caller-provided text (dictation stub); returns (text, meta)."""
        ...

    @abstractmethod
    def transcribe_audio(self, audio: bytes) -> tuple[str, dict[str, Any]]:
        """Transcribe WAV bytes; returns (text, meta)."""
        ...


class MockSTTBackend(STTBackend):
    """Deterministic stub; always available, zero-cost, honest about it."""

    name = "mock"
    backend = VoiceBackend.MOCK

    def is_available(self) -> bool:
        return True

    def transcribe_text(self, text: str) -> tuple[str, dict[str, Any]]:
        cleaned = " ".join(text.split())
        return (f"{STT_MOCK_PREFIX} {cleaned}", {"source": "text"})

    def transcribe_audio(self, audio: bytes) -> tuple[str, dict[str, Any]]:
        if not is_wav_bytes(audio):
            raise VoiceValidationError("STT audio must be WAV (RIFF/WAVE) bytes")
        digest = hashlib.sha256(audio).hexdigest()[:12]
        seconds = max(1, len(audio) // 32000)
        text = f"{STT_MOCK_PREFIX} audio frame {len(audio)} bytes ~{seconds}s id={digest}"
        return (text, {"source": "wav", "audio_bytes": len(audio)})


class OfflineSTTBackend(MockSTTBackend):
    """Offline-engine slot: same deterministic behavior until a local engine lands."""

    name = "offline"
    backend = VoiceBackend.OFFLINE

    def is_available(self) -> bool:
        return False


class STTManager:
    """Bounded transcription: text/audio caps plus a wall-clock timeout."""

    def __init__(
        self,
        limits: VoiceLimits | None = None,
        backend: STTBackend | None = None,
    ) -> None:
        self._limits = limits or default_limits()
        self._backend = backend or MockSTTBackend()

    @property
    def backend_name(self) -> str:
        return self._backend.name

    @property
    def backend_available(self) -> bool:
        try:
            return self._backend.is_available()
        except Exception:
            return False

    def _finish(self, text: str, meta: dict[str, Any], started: float) -> Transcript:
        elapsed = time.perf_counter() - started
        if elapsed > self._limits.listen_timeout_seconds:
            raise VoiceTimeoutError(
                f"listen exceeded {self._limits.listen_timeout_seconds}s (took {elapsed:.2f}s)"
            )
        if len(text) > self._limits.max_text_chars:
            raise VoiceValidationError(
                f"transcript is {len(text)} chars, over the "
                f"{self._limits.max_text_chars}-char limit"
            )
        record = Transcript(
            id=new_utterance_id(),
            backend=self._backend.backend,
            text=text,
            text_chars=len(text),
            sha256=transcript_digest(text),
            duration_ms=round(elapsed * 1000, 3),
            metadata={k: v for k, v in meta.items() if k != "text"},
        )
        record.validate()
        log.debug(
            "transcribed utterance",
            extra={"component": "voice", "utterance_id": record.id},
        )
        return record

    def listen_text(self, text: str) -> Transcript:
        """Transcribe caller-provided text through the bounded mock pipeline."""
        if not isinstance(text, str) or not text.strip():
            raise VoiceValidationError("listen text must be a non-empty string")
        if len(text) > self._limits.max_text_chars:
            raise VoiceValidationError(
                f"listen text is {len(text)} chars, over the "
                f"{self._limits.max_text_chars}-char limit"
            )
        if not self.backend_available:
            raise VoiceValidationError(f"STT backend {self._backend.name!r} is not available")
        started = time.perf_counter()
        out, meta = self._backend.transcribe_text(text.strip())
        return self._finish(out, meta, started)

    def listen_audio(self, audio: bytes) -> Transcript:
        """Transcribe WAV bytes through the bounded mock pipeline."""
        if not isinstance(audio, bytes) or not audio:
            raise VoiceValidationError("listen audio must be non-empty bytes")
        if len(audio) > self._limits.max_audio_bytes:
            raise VoiceValidationError(
                f"listen audio is {len(audio)} bytes, over the "
                f"{self._limits.max_audio_bytes}-byte limit"
            )
        if not self.backend_available:
            raise VoiceValidationError(f"STT backend {self._backend.name!r} is not available")
        started = time.perf_counter()
        out, meta = self._backend.transcribe_audio(audio)
        return self._finish(out, meta, started)
