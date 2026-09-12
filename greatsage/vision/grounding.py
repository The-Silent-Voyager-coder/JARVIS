"""OCR-free grounding stubs (Phase 8).

No OCR engine, no model inference, no network: grounding returns a
deterministic layout grid over the frame with normalized coordinates.
Every label and summary is explicitly marked as a stub so downstream
consumers can never mistake it for real screen understanding.
"""

from __future__ import annotations

import logging
import math

from greatsage.vision.limits import VisionLimits, default_limits
from greatsage.vision.models import VisionBackend, VisionDescription, VisionRegion

log = logging.getLogger("greatsage.vision.grounding")

STUB_MARKER = "[stub-no-ocr]"
TRUNCATION_SUFFIX = "…[truncated]"


def _grid_dims(count: int) -> tuple[int, int]:
    """Near-square grid holding at least `count` cells."""
    cols = max(1, math.ceil(math.sqrt(count)))
    rows = max(1, math.ceil(count / cols))
    return (rows, cols)


class GroundingStub:
    """Deterministic layout grounding; honest about being a stub."""

    def __init__(self, limits: VisionLimits | None = None) -> None:
        self._limits = limits or default_limits()

    def describe(
        self,
        capture_id: str,
        width: int,
        height: int,
        *,
        max_regions: int | None = None,
        max_chars: int | None = None,
    ) -> VisionDescription:
        """Build a bounded stub description for a capture."""
        region_cap = min(
            max_regions if max_regions is not None else self._limits.max_regions,
            self._limits.max_regions,
        )
        char_cap = min(
            max_chars if max_chars is not None else self._limits.max_description_chars,
            self._limits.max_description_chars,
        )
        region_cap = max(1, region_cap)
        rows, cols = _grid_dims(region_cap)
        regions: list[VisionRegion] = []
        index = 0
        for row in range(rows):
            for col in range(cols):
                if index >= region_cap:
                    break
                regions.append(
                    VisionRegion(
                        label=f"stub-cell-r{row}c{col}",
                        x=round(col / cols, 4),
                        y=round(row / rows, 4),
                        width=round(1.0 / cols, 4),
                        height=round(1.0 / rows, 4),
                        confidence=0.0,
                    )
                )
                index += 1
        summary = (
            f"{STUB_MARKER} {width}x{height} bmp frame split into "
            f"{len(regions)} layout cells ({rows}x{cols} grid); "
            "no text was recognized and no model inference ran."
        )
        truncated = False
        if len(summary) > char_cap:
            summary = summary[: max(0, char_cap - len(TRUNCATION_SUFFIX))] + TRUNCATION_SUFFIX
            truncated = True
        description = VisionDescription(
            capture_id=capture_id,
            backend=VisionBackend.STUB,
            summary=summary,
            regions=tuple(regions),
            truncated=truncated,
        )
        description.validate()
        log.debug(
            "grounded capture",
            extra={"component": "vision", "capture_id": capture_id},
        )
        return description
