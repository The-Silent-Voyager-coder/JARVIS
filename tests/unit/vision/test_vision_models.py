"""Vision model tests: validation, serialization, path guards."""

from __future__ import annotations

import pytest

from greatsage.exceptions import VisionValidationError
from greatsage.vision.models import (
    VisionBackend,
    VisionCapture,
    VisionDescription,
    VisionRegion,
    new_capture_id,
    sanitize_output_path,
)


def make_capture(**overrides: object) -> VisionCapture:
    from datetime import UTC, datetime

    kwargs: dict[str, object] = {
        "id": new_capture_id(),
        "backend": VisionBackend.STUB,
        "width": 320,
        "height": 200,
        "format": "bmp",
        "sha256": "a" * 64,
        "size_bytes": 192054,
        "created_at": datetime.now(UTC),
    }
    kwargs.update(overrides)
    return VisionCapture(**kwargs)  # type: ignore[arg-type]


def test_capture_id_shape() -> None:
    capture_id = new_capture_id()
    assert capture_id.startswith("cap_")
    assert len(capture_id) == 36


def test_capture_validate_ok() -> None:
    make_capture().validate()


def test_capture_rejects_bad_id() -> None:
    with pytest.raises(VisionValidationError):
        make_capture(id="nope").validate()


def test_capture_rejects_non_positive_dims() -> None:
    with pytest.raises(VisionValidationError):
        make_capture(width=0).validate()


def test_capture_rejects_bad_format() -> None:
    with pytest.raises(VisionValidationError):
        make_capture(format="png").validate()


def test_capture_rejects_bad_hash() -> None:
    with pytest.raises(VisionValidationError):
        make_capture(sha256="xyz").validate()


def test_capture_round_trip() -> None:
    record = make_capture()
    clone = VisionCapture.from_dict(record.to_dict())
    assert clone.id == record.id
    assert clone.sha256 == record.sha256
    assert clone.width == record.width


def test_capture_from_dict_rejects_garbage() -> None:
    with pytest.raises(VisionValidationError):
        VisionCapture.from_dict({"id": "cap_nope"})


def test_region_bounds() -> None:
    VisionRegion(label="a", x=0.0, y=0.0, width=1.0, height=1.0, confidence=0.0).validate()
    with pytest.raises(VisionValidationError):
        VisionRegion(label="a", x=1.5, y=0.0, width=0.5, height=0.5, confidence=0.0).validate()
    with pytest.raises(VisionValidationError):
        VisionRegion(label="", x=0.0, y=0.0, width=0.5, height=0.5, confidence=0.0).validate()


def test_description_requires_stub_honesty() -> None:
    from datetime import UTC, datetime

    desc = VisionDescription(
        capture_id=new_capture_id(),
        backend=VisionBackend.STUB,
        summary="[stub-no-ocr] test",
        created_at=datetime.now(UTC),
    )
    desc.validate()
    assert desc.to_dict()["summary"].startswith("[stub-no-ocr]")


def test_sanitize_output_path_requires_bmp() -> None:
    with pytest.raises(VisionValidationError):
        sanitize_output_path("frame.png")
    assert sanitize_output_path("frame.bmp").suffix == ".bmp"
