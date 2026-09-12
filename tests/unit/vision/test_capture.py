"""Capture tests: deterministic BMP, bounds, timeout plumbing."""

from __future__ import annotations

import pytest

from greatsage.exceptions import VisionValidationError
from greatsage.vision.capture import (
    CaptureManager,
    StubCaptureBackend,
    encode_bmp,
    parse_bmp_dimensions,
)
from greatsage.vision.limits import VisionLimits, default_limits


def test_stub_always_available() -> None:
    assert StubCaptureBackend().is_available()


def test_encode_bmp_magic_and_dims() -> None:
    image = encode_bmp(32, 20)
    assert image[0:2] == b"BM"
    assert parse_bmp_dimensions(image) == (32, 20)


def test_encode_bmp_deterministic() -> None:
    assert encode_bmp(16, 10, seed=3) == encode_bmp(16, 10, seed=3)
    assert encode_bmp(16, 10, seed=3) != encode_bmp(16, 10, seed=4)


def test_parse_rejects_non_bmp() -> None:
    with pytest.raises(VisionValidationError):
        parse_bmp_dimensions(b"not an image at all..............................")


def test_manager_enforces_dim_caps() -> None:
    manager = CaptureManager(limits=default_limits())
    with pytest.raises(VisionValidationError):
        manager.capture(100000, 10)
    with pytest.raises(VisionValidationError):
        manager.capture(0, 10)
    with pytest.raises(VisionValidationError):
        manager.capture(-4, 10)


def test_manager_enforces_byte_cap() -> None:
    tiny = VisionLimits(max_image_bytes=100)
    manager = CaptureManager(limits=tiny)
    with pytest.raises(VisionValidationError):
        manager.capture(64, 64)


def test_manager_returns_metadata() -> None:
    manager = CaptureManager(limits=default_limits())
    image, meta = manager.capture(64, 40)
    assert meta["width"] == 64
    assert meta["height"] == 40
    assert meta["size_bytes"] == len(image)
    assert meta["backend"] == "stub"


def test_manager_rejects_unavailable_backend() -> None:
    class Dead(StubCaptureBackend):
        name = "dead"

        def is_available(self) -> bool:
            return False

    manager = CaptureManager(limits=default_limits(), backend=Dead())
    with pytest.raises(VisionValidationError):
        manager.capture(32, 20)
