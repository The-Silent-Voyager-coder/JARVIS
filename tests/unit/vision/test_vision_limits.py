"""Vision limit tests: defaults, ceilings, smaller-wins resolution."""

from __future__ import annotations

import pytest

from greatsage.vision import limits


def test_defaults_within_ceilings() -> None:
    defaults = limits.default_limits()
    assert defaults.max_image_bytes <= limits.MAX_IMAGE_BYTES_CEILING
    assert defaults.max_description_chars <= limits.MAX_DESCRIPTION_CHARS_CEILING
    assert defaults.max_regions <= limits.MAX_REGIONS_CEILING
    assert defaults.max_captures_per_session <= limits.MAX_CAPTURES_PER_SESSION_CEILING
    assert defaults.capture_timeout_seconds <= limits.CAPTURE_TIMEOUT_SECONDS_CEILING


def test_check_bounded_rejects_over_ceiling() -> None:
    with pytest.raises(ValueError):
        limits.check_bounded("x", limits.MAX_REGIONS_CEILING + 1, limits.MAX_REGIONS_CEILING)


def test_resolve_clamps_above_ceiling() -> None:
    resolved = limits.resolve_limits(
        max_regions=limits.MAX_REGIONS_CEILING + 100,
        max_image_bytes=limits.MAX_IMAGE_BYTES_CEILING + 1,
        max_description_chars=limits.MAX_DESCRIPTION_CHARS_CEILING + 1,
        max_captures_per_session=limits.MAX_CAPTURES_PER_SESSION_CEILING + 1,
        capture_timeout_seconds=limits.CAPTURE_TIMEOUT_SECONDS_CEILING + 1.0,
    )
    assert resolved.max_regions == limits.MAX_REGIONS_CEILING
    assert resolved.max_image_bytes == limits.MAX_IMAGE_BYTES_CEILING
    assert resolved.max_description_chars == limits.MAX_DESCRIPTION_CHARS_CEILING
    assert resolved.max_captures_per_session == limits.MAX_CAPTURES_PER_SESSION_CEILING
    assert resolved.capture_timeout_seconds == limits.CAPTURE_TIMEOUT_SECONDS_CEILING


def test_resolve_honors_tighter_override() -> None:
    resolved = limits.resolve_limits(max_regions=2)
    assert resolved.max_regions == 2
