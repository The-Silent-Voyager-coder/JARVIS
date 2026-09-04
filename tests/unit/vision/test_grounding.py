"""Grounding stub tests: honest labels, normalized coords, truncation."""

from __future__ import annotations

from jarvis.vision.grounding import STUB_MARKER, GroundingStub
from jarvis.vision.limits import VisionLimits, default_limits
from jarvis.vision.models import new_capture_id


def test_stub_summary_marked() -> None:
    desc = GroundingStub(limits=default_limits()).describe(new_capture_id(), 320, 200)
    assert desc.summary.startswith(STUB_MARKER)
    assert "no text was recognized" in desc.summary
    assert len(desc.regions) == 8


def test_regions_normalized_and_zero_confidence() -> None:
    desc = GroundingStub(limits=default_limits()).describe(
        new_capture_id(), 320, 200, max_regions=4
    )
    assert len(desc.regions) == 4
    for region in desc.regions:
        region.validate()
        assert region.confidence == 0.0
        assert region.label.startswith("stub-cell-")


def test_max_regions_clamped_to_limit() -> None:
    tiny = VisionLimits(max_regions=2)
    desc = GroundingStub(limits=tiny).describe(new_capture_id(), 320, 200, max_regions=99)
    assert len(desc.regions) == 2


def test_truncation_flag() -> None:
    tiny = VisionLimits(max_description_chars=40)
    desc = GroundingStub(limits=tiny).describe(new_capture_id(), 320, 200)
    assert desc.truncated
    assert desc.summary.endswith("…[truncated]")
    assert len(desc.summary) <= 40
