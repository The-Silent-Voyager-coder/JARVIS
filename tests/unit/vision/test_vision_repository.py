"""File repository tests: round-trip, traversal guard, listing."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from greatsage.exceptions import VisionValidationError
from greatsage.vision.capture import encode_bmp
from greatsage.vision.file_repository import FileVisionRepository
from greatsage.vision.models import VisionBackend, VisionCapture, new_capture_id


def make_record() -> tuple[VisionCapture, bytes]:
    image = encode_bmp(32, 20)
    import hashlib

    record = VisionCapture(
        id=new_capture_id(),
        backend=VisionBackend.STUB,
        width=32,
        height=20,
        format="bmp",
        sha256=hashlib.sha256(image).hexdigest(),
        size_bytes=len(image),
        created_at=datetime.now(UTC),
    )
    return (record, image)


def test_save_get_round_trip(tmp_path: Path) -> None:
    repo = FileVisionRepository(tmp_path / "vision")
    repo.initialize()
    record, image = make_record()
    repo.save(record, image)
    found = repo.get(record.id)
    assert found is not None
    assert found[0].id == record.id
    assert found[1] == image
    assert repo.count() == 1


def test_get_missing_returns_none(tmp_path: Path) -> None:
    repo = FileVisionRepository(tmp_path / "vision")
    repo.initialize()
    assert repo.get(new_capture_id()) is None


def test_rejects_traversal_id(tmp_path: Path) -> None:
    repo = FileVisionRepository(tmp_path / "vision")
    repo.initialize()
    with pytest.raises(VisionValidationError):
        repo.get("../evil")
    with pytest.raises(VisionValidationError):
        repo.get("cap_short")


def test_rejects_size_mismatch(tmp_path: Path) -> None:
    repo = FileVisionRepository(tmp_path / "vision")
    repo.initialize()
    record, _image = make_record()
    with pytest.raises(VisionValidationError):
        repo.save(record, b"too short")


def test_list_newest_first(tmp_path: Path) -> None:
    repo = FileVisionRepository(tmp_path / "vision")
    repo.initialize()
    for _ in range(3):
        record, image = make_record()
        repo.save(record, image)
    items = repo.list(limit=2)
    assert len(items) == 2
    assert items[0].created_at >= items[1].created_at


def test_health_reports_store(tmp_path: Path) -> None:
    repo = FileVisionRepository(tmp_path / "vision")
    repo.initialize()
    health = repo.health()
    assert health.accessible
    assert health.writable
    assert health.capture_count == 0
