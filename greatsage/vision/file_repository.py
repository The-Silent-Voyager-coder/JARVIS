"""File-backed vision repository (Phase 8).

Stdlib only: `<store>/<id>.bmp` pixel bytes plus a `<store>/<id>.json`
metadata sidecar. Capture ids are strictly validated (`cap_<32 hex>`) so a
crafted id can never escape the store directory.
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
from pathlib import Path

from greatsage.exceptions import VisionValidationError
from greatsage.vision.models import VisionCapture
from greatsage.vision.repository import RepositoryHealth, VisionRepository

log = logging.getLogger("greatsage.vision.repository")

_CAPTURE_ID_RE = re.compile(r"^cap_[0-9a-f]{32}$")


def _checked_id(capture_id: str) -> str:
    if not _CAPTURE_ID_RE.match(capture_id):
        raise VisionValidationError(f"invalid capture id: {capture_id!r}")
    return capture_id


class FileVisionRepository(VisionRepository):
    """File-backed store; small, local, inspectable without AI services."""

    def __init__(self, store_dir: str | Path) -> None:
        self._store = Path(store_dir)
        self._closed = False

    @property
    def store_dir(self) -> Path:
        return self._store

    def initialize(self) -> None:
        self._store.mkdir(parents=True, exist_ok=True)
        self._closed = False

    def _paths(self, capture_id: str) -> tuple[Path, Path]:
        checked = _checked_id(capture_id)
        return (self._store / f"{checked}.bmp", self._store / f"{checked}.json")

    def save(self, capture: VisionCapture, image: bytes) -> None:
        if self._closed:
            raise VisionValidationError("vision repository is closed")
        capture.validate()
        if len(image) != capture.size_bytes:
            raise VisionValidationError(
                f"image is {len(image)} bytes, record says {capture.size_bytes}"
            )
        bmp_path, json_path = self._paths(capture.id)
        tmp_bmp = Path(
            tempfile.NamedTemporaryFile(delete=False, dir=str(self._store), suffix=".bmp").name
        )
        try:
            tmp_bmp.write_bytes(image)
            tmp_bmp.replace(bmp_path)
            json_path.write_text(json.dumps(capture.to_dict(), indent=2), encoding="utf-8")
        finally:
            try:
                if tmp_bmp.exists():
                    tmp_bmp.unlink()
            except OSError:
                pass

    def get(self, capture_id: str) -> tuple[VisionCapture, bytes] | None:
        bmp_path, json_path = self._paths(capture_id)
        if not bmp_path.exists() or not json_path.exists():
            return None
        try:
            record = VisionCapture.from_dict(json.loads(json_path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            log.warning(
                "unreadable capture sidecar",
                extra={"component": "vision", "capture_id": capture_id},
            )
            raise VisionValidationError(f"capture sidecar unreadable: {exc}") from exc
        try:
            image = bmp_path.read_bytes()
        except OSError as exc:
            raise VisionValidationError(f"capture pixels unreadable: {exc}") from exc
        return (record, image)

    def list(self, limit: int = 50) -> list[VisionCapture]:
        if limit <= 0:
            raise VisionValidationError("list limit must be positive")
        if not self._store.exists():
            return []
        records: list[VisionCapture] = []
        for sidecar in sorted(self._store.glob("cap_*.json")):
            try:
                records.append(
                    VisionCapture.from_dict(json.loads(sidecar.read_text(encoding="utf-8")))
                )
            except (OSError, ValueError, VisionValidationError):
                continue
        records.sort(key=lambda c: (c.created_at.isoformat(), c.id), reverse=True)
        return records[:limit]

    def count(self) -> int:
        if not self._store.exists():
            return 0
        return len(list(self._store.glob("cap_*.bmp")))

    def health(self) -> RepositoryHealth:
        accessible = self._store.exists() and not self._closed
        writable = False
        detail: str | None = None
        if accessible:
            try:
                probe = self._store / ".vision_write_probe"
                probe.write_bytes(b"ok")
                probe.unlink()
                writable = True
            except OSError as exc:
                detail = f"store not writable: {exc}"
        else:
            detail = "store directory missing or repository closed"
        try:
            total = self.count()
        except OSError:
            total = 0
        return RepositoryHealth(
            accessible=accessible,
            writable=writable,
            store_dir=str(self._store),
            capture_count=total,
            detail=detail,
        )

    def close(self) -> None:
        self._closed = True
