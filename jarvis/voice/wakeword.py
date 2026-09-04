"""Wake-word stub (Phase 6).

Stdlib only, zero-cost, local-first: a deterministic keyword match over
a bounded text window. No audio DSP, no model, no network is ever
required. A real on-device detector may replace the matcher behind the
same `WakeWordDetector` ABC without changing callers.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from jarvis.exceptions import VoiceValidationError
from jarvis.voice.limits import VoiceLimits, default_limits
from jarvis.voice.models import VoiceBackend, WakeResult, redact_text

log = logging.getLogger("jarvis.voice.wakeword")


class WakeWordDetector(ABC):
    """Pluggable wake-word source; callers never touch audio directly."""

    name: str = "abstract"

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def check(self, text: str) -> WakeResult:
        """Check one bounded text window for the wake keyword."""
        ...


class KeywordWakeDetector(WakeWordDetector):
    """Case-insensitive substring match; always available, zero-cost."""

    name = "keyword"

    def __init__(
        self,
        keyword: str = "jarvis",
        *,
        limits: VoiceLimits | None = None,
    ) -> None:
        cleaned = (keyword or "").strip().lower()
        if not cleaned:
            raise VoiceValidationError("wake keyword must not be empty")
        self._keyword = cleaned
        self._limits = limits or default_limits()

    @property
    def keyword(self) -> str:
        return self._keyword

    def is_available(self) -> bool:
        return True

    def check(self, text: str) -> WakeResult:
        """Match the keyword inside a bounded window (chars + word boundary)."""
        if not isinstance(text, str):
            raise VoiceValidationError("wake input must be a string")
        if not text.strip():
            raise VoiceValidationError("wake input must not be empty")
        if len(text) > self._limits.max_wake_text_chars:
            raise VoiceValidationError(
                f"wake input is {len(text)} chars, over the "
                f"{self._limits.max_wake_text_chars}-char limit"
            )
        lowered = text.lower()
        detected = self._keyword in lowered
        result = WakeResult(
            detected=detected,
            keyword=self._keyword,
            confidence=1.0 if detected else 0.0,
            backend=VoiceBackend.MOCK,
        )
        result.validate()
        log.debug(
            "wake check: detected=%s",
            detected,
            extra={"component": "voice", "keyword": self._keyword},
        )
        _ = redact_text(text)
        return result
