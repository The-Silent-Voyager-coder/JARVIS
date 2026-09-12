"""Voice repository contract (Phase 6).

The service depends on this ABC, never on files. File layout
(`<id>.json` sidecar + optional `<id>.wav` audio) lives in
file_repository.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from greatsage.voice.models import SpeechResult, Transcript


@dataclass(frozen=True)
class RepositoryHealth:
    accessible: bool
    writable: bool
    store_dir: str
    utterance_count: int
    detail: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "accessible": self.accessible,
            "writable": self.writable,
            "store_dir": self.store_dir,
            "utterance_count": self.utterance_count,
            "detail": self.detail,
        }


class VoiceRepository(ABC):
    """Persistence contract for transcripts + synthesized audio metadata."""

    @abstractmethod
    def initialize(self) -> None: ...

    @abstractmethod
    def save_transcript(self, record: Transcript) -> None: ...

    @abstractmethod
    def save_speech(self, record: SpeechResult, audio: bytes) -> None: ...

    @abstractmethod
    def get_transcript(self, utterance_id: str) -> Transcript | None: ...

    @abstractmethod
    def get_speech(self, utterance_id: str) -> tuple[SpeechResult, bytes | None] | None: ...

    @abstractmethod
    def list_transcripts(self, limit: int = 50) -> list[Transcript]: ...

    @abstractmethod
    def count(self) -> int: ...

    @abstractmethod
    def health(self) -> RepositoryHealth: ...

    @abstractmethod
    def close(self) -> None: ...
