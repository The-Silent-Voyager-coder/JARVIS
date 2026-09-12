"""Corrupt-file quarantine (recovery support).

Policy (extends the Phase 3 rule — a corrupted database is never deleted to
repair): when a SQLite repository detects corruption it degrades as before,
but first quarantines a timestamped copy of the damaged file next to it
(`<name>.quarantine/`). The original is never modified or removed, so a
human (or a future repair pass) can always inspect or restore it.

Quarantine never raises: if the copy fails, degradation proceeds with the
original kept as-is.
"""

from __future__ import annotations

import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger("greatsage.storage.recovery")


def quarantine_corrupt_file(path: str | Path, *, reason: str) -> Path | None:
    """Copy a suspect database file into `<stem>.quarantine/` next to it.

    Returns the quarantine copy path, or None when there is nothing to copy
    (missing file) or the copy itself failed. The source file is never
    touched.
    """
    src = Path(path)
    if not src.is_file():
        return None
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dest = src.parent / f"{src.stem}.quarantine" / f"{src.stem}-{stamp}{src.suffix}.corrupt"
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    except OSError as exc:
        log.warning(
            "quarantine copy failed for %s (%s); original kept as-is",
            src,
            exc,
            extra={"component": "storage"},
        )
        return None
    log.warning(
        "quarantined suspect database %s -> %s (%s)",
        src,
        dest,
        reason,
        extra={"component": "storage"},
    )
    return dest
