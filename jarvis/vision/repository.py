"""Vision repository contract (Phase 8).

The service depends on this ABC, never on files. File layout
(`<id>.bmp` + `<id>.json` sidecar) lives in file_repository.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from jarvis.vision.models import VisionCapture


@dataclass(frozen=True)
class RepositoryHealth:
    accessible: bool
    writable: bool
    store_dir: str
    capture_count: int
    detail: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "accessible": self.accessible,
            "writable": self.writable,
            "store_dir": self.store_dir,
            "capture_count": self.capture_count,
            "detail": self.detail,
        }


class VisionRepository(ABC):
    """Persistence contract for captures + pixel bytes."""

    @abstractmethod
    def initialize(self) -> None: ...

    @abstractmethod
    def save(self, capture: VisionCapture, image: bytes) -> None: ...

    @abstractmethod
    def get(self, capture_id: str) -> tuple[VisionCapture, bytes] | None: ...

    @abstractmethod
    def list(self, limit: int = 50) -> list[VisionCapture]: ...

    @abstractmethod
    def count(self) -> int: ...

    @abstractmethod
    def health(self) -> RepositoryHealth: ...

    @abstractmethod
    def close(self) -> None: ...
