"""Corrupt-file quarantine tests (recovery support)."""

from __future__ import annotations

from pathlib import Path

import pytest

import greatsage.storage.recovery as recovery
from greatsage.storage.recovery import quarantine_corrupt_file


def test_quarantine_copies_and_keeps_original(tmp_path: Path) -> None:
    src = tmp_path / "memory.db"
    src.write_bytes(b"garbage-not-sqlite" * 64)
    dest = quarantine_corrupt_file(src, reason="test")
    assert dest is not None
    assert dest.exists()
    assert dest.read_bytes() == src.read_bytes()
    assert src.exists()  # original never touched
    assert dest.parent.name == "memory.quarantine"
    assert dest.suffixes[-2:] == [".db", ".corrupt"] or dest.name.endswith(".db.corrupt")


def test_quarantine_missing_file_returns_none(tmp_path: Path) -> None:
    assert quarantine_corrupt_file(tmp_path / "absent.db", reason="test") is None


def test_quarantine_never_raises_on_unwritable_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "memory.db"
    src.write_bytes(b"x" * 32)

    def boom(*args: object, **kwargs: object) -> None:
        raise OSError("disk gone")

    monkeypatch.setattr(recovery.shutil, "copy2", boom)
    assert quarantine_corrupt_file(src, reason="test") is None
    assert src.exists()
