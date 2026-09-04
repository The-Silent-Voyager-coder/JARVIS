"""Text-to-speech abstraction (Phase 6).

Stdlib only, zero-cost, local-first. The active backend synthesizes a
deterministic 16-bit mono 16 kHz WAV (a short sine phrase whose length
scales with the input text, capped by the byte limit). No model
download, no cloud API is ever required. A real offline engine may be
added later behind the same `TTSBackend` ABC without changing callers.
"""

from __future__ import annotations

import hashlib
import logging
import math
import struct
import time
from abc import ABC, abstractmethod
from typing import Any

from jarvis.exceptions import VoiceTimeoutError, VoiceValidationError
from jarvis.voice.limits import VoiceLimits, default_limits
from jarvis.voice.models import SpeechResult, VoiceBackend, new_utterance_id

log = logging.getLogger("jarvis.voice.tts")

WAV_SAMPLE_RATE = 16000
WAV_CHANNELS = 1
WAV_BITS = 16
WAV_HEADER_SIZE = 44
_BASE_SECONDS = 0.5
_SECONDS_PER_CHAR = 0.02
_MAX_SYNTH_SECONDS = 8.0
_TONE_HZ = 220.0


def encode_wav(text: str, *, seed: int = 0) -> tuple[bytes, float]:
    """Encode deterministic mono WAV bytes for `text`; returns (bytes, seconds)."""
    seconds = min(_BASE_SECONDS + len(text) * _SECONDS_PER_CHAR, _MAX_SYNTH_SECONDS)
    frames = int(WAV_SAMPLE_RATE * seconds)
    digest = int(hashlib.sha256(f"{seed}:{text}".encode()).hexdigest()[:8], 16)
    phase_offset = (digest % 360) * math.pi / 180.0
    samples = bytearray()
    for i in range(frames):
        phase = 2.0 * math.pi * _TONE_HZ * i / WAV_SAMPLE_RATE + phase_offset
        envelope = 0.5 + 0.5 * math.sin(2.0 * math.pi * i / frames)
        value = int(12000 * envelope * math.sin(phase))
        samples.extend(struct.pack("<h", value))
    data_size = len(samples)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        WAV_CHANNELS,
        WAV_SAMPLE_RATE,
        WAV_SAMPLE_RATE * WAV_CHANNELS * 2,
        WAV_CHANNELS * 2,
        WAV_BITS,
        b"data",
        data_size,
    )
    return (header + bytes(samples), seconds)


class TTSBackend(ABC):
    """Pluggable synthesis source; callers never touch engines directly."""

    name: str = "abstract"
    backend: VoiceBackend = VoiceBackend.MOCK

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def synthesize(self, text: str) -> tuple[bytes, dict[str, Any]]:
        """Synthesize WAV bytes for `text`; returns (wav bytes, meta)."""
        ...


class MockTTSBackend(TTSBackend):
    """Deterministic sine-phrase synth; always available, zero-cost."""

    name = "mock"
    backend = VoiceBackend.MOCK

    def is_available(self) -> bool:
        return True

    def synthesize(self, text: str) -> tuple[bytes, dict[str, Any]]:
        audio, seconds = encode_wav(text)
        return (audio, {"source": "synth", "seconds": round(seconds, 3)})


class OfflineTTSBackend(MockTTSBackend):
    """Offline-engine slot: same deterministic behavior until a local engine lands."""

    name = "offline"
    backend = VoiceBackend.OFFLINE

    def is_available(self) -> bool:
        return False


class TTSManager:
    """Bounded synthesis: char caps, byte caps, wall-clock timeout."""

    def __init__(
        self,
        limits: VoiceLimits | None = None,
        backend: TTSBackend | None = None,
    ) -> None:
        self._limits = limits or default_limits()
        self._backend = backend or MockTTSBackend()

    @property
    def backend_name(self) -> str:
        return self._backend.name

    @property
    def backend_available(self) -> bool:
        try:
            return self._backend.is_available()
        except Exception:
            return False

    def speak(self, text: str) -> tuple[bytes, SpeechResult]:
        """Synthesize bounded WAV bytes for `text`; returns (bytes, metadata)."""
        if not isinstance(text, str) or not text.strip():
            raise VoiceValidationError("speak text must be a non-empty string")
        cleaned = " ".join(text.split())
        if len(cleaned) > self._limits.max_synth_chars:
            raise VoiceValidationError(
                f"speak text is {len(cleaned)} chars, over the "
                f"{self._limits.max_synth_chars}-char limit"
            )
        if not self.backend_available:
            raise VoiceValidationError(f"TTS backend {self._backend.name!r} is not available")
        started = time.perf_counter()
        audio, meta = self._backend.synthesize(cleaned)
        elapsed = time.perf_counter() - started
        if elapsed > self._limits.listen_timeout_seconds:
            raise VoiceTimeoutError(
                f"speak exceeded {self._limits.listen_timeout_seconds}s (took {elapsed:.2f}s)"
            )
        if len(audio) > self._limits.max_audio_bytes:
            raise VoiceValidationError(
                f"synthesized audio is {len(audio)} bytes, over the "
                f"{self._limits.max_audio_bytes}-byte limit"
            )
        record = SpeechResult(
            id=new_utterance_id(),
            backend=self._backend.backend,
            text_chars=len(cleaned),
            sha256=hashlib.sha256(cleaned.encode("utf-8")).hexdigest(),
            size_bytes=len(audio),
            format="wav",
            duration_ms=round(elapsed * 1000, 3),
            metadata={k: v for k, v in meta.items() if k != "text"},
        )
        record.validate()
        log.debug(
            "synthesized speech",
            extra={"component": "voice", "utterance_id": record.id},
        )
        return (audio, record)
