"""File-backed voice repository (Phase 6).

Stdlib only: `<store>/<id>.json` metadata sidecars (transcript text
included — the store is local under `core.data_dir/voice`), plus an
optional `<store>/<id>.wav` for synthesized audio. Utterance ids are
strictly validated (`vtt_<32 hex>`) so a crafted id can never escape
the store directory.
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
from pathlib import Path
from typing import Any

from jarvis.exceptions import VoiceValidationError
from jarvis.voice.models import SpeechResult, Transcript, VoiceBackend
from jarvis.voice.repository import RepositoryHealth, VoiceRepository

log = logging.getLogger("jarvis.voice.repository")

_UTTERANCE_ID_RE = re.compile(r"^vtt_[0-9a-f]{32}$")


def _checked_id(utterance_id: str) -> str:
    if not _UTTERANCE_ID_RE.match(utterance_id):
        raise VoiceValidationError(f"invalid utterance id: {utterance_id!r}")
    return utterance_id


def _transcript_from_dict(data: dict[str, Any]) -> Transcript:
    from datetime import datetime

    try:
        record = Transcript(
            id=str(data["id"]),
            backend=VoiceBackend(str(data["backend"])),
            text=str(data["text"]),
            text_chars=int(data["text_chars"]),
            sha256=str(data["sha256"]),
            duration_ms=float(data.get("duration_ms", 0.0)),
            created_at=datetime.fromisoformat(str(data["created_at"])),
            metadata=dict(data.get("metadata") or {}),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise VoiceValidationError(f"invalid transcript record: {exc}") from exc
    record.validate()
    return record


def _speech_from_dict(data: dict[str, Any]) -> SpeechResult:
    from datetime import datetime

    try:
        record = SpeechResult(
            id=str(data["id"]),
            backend=VoiceBackend(str(data["backend"])),
            text_chars=int(data["text_chars"]),
            sha256=str(data["sha256"]),
            size_bytes=int(data["size_bytes"]),
            format=str(data.get("format", "wav")),
            duration_ms=float(data.get("duration_ms", 0.0)),
            output_path=data.get("output_path"),
            created_at=datetime.fromisoformat(str(data["created_at"])),
            metadata=dict(data.get("metadata") or {}),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise VoiceValidationError(f"invalid speech record: {exc}") from exc
    record.validate()
    return record


class FileVoiceRepository(VoiceRepository):
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

    def _sidecar(self, utterance_id: str) -> Path:
        return self._store / f"{_checked_id(utterance_id)}.json"

    def _audio(self, utterance_id: str) -> Path:
        return self._store / f"{_checked_id(utterance_id)}.wav"

    def _write_sidecar(self, utterance_id: str, payload: dict[str, Any]) -> None:
        target = self._sidecar(utterance_id)
        tmp = Path(
            tempfile.NamedTemporaryFile(delete=False, dir=str(self._store), suffix=".json").name
        )
        try:
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp.replace(target)
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass

    def save_transcript(self, record: Transcript) -> None:
        if self._closed:
            raise VoiceValidationError("voice repository is closed")
        record.validate()
        payload = record.to_dict(include_text=True)
        payload["kind"] = "transcript"
        self._write_sidecar(record.id, payload)

    def save_speech(self, record: SpeechResult, audio: bytes) -> None:
        if self._closed:
            raise VoiceValidationError("voice repository is closed")
        record.validate()
        if len(audio) != record.size_bytes:
            raise VoiceValidationError(
                f"audio is {len(audio)} bytes, record says {record.size_bytes}"
            )
        audio_path = self._audio(record.id)
        tmp = Path(
            tempfile.NamedTemporaryFile(delete=False, dir=str(self._store), suffix=".wav").name
        )
        try:
            tmp.write_bytes(audio)
            tmp.replace(audio_path)
            payload = record.to_dict()
            payload["kind"] = "speech"
            self._write_sidecar(record.id, payload)
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass

    def get_transcript(self, utterance_id: str) -> Transcript | None:
        path = self._sidecar(utterance_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise VoiceValidationError(f"utterance sidecar unreadable: {exc}") from exc
        if data.get("kind") != "transcript":
            return None
        return _transcript_from_dict(data)

    def get_speech(self, utterance_id: str) -> tuple[SpeechResult, bytes | None] | None:
        path = self._sidecar(utterance_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise VoiceValidationError(f"utterance sidecar unreadable: {exc}") from exc
        if data.get("kind") != "speech":
            return None
        record = _speech_from_dict(data)
        audio_path = self._audio(utterance_id)
        audio = audio_path.read_bytes() if audio_path.exists() else None
        return (record, audio)

    def list_transcripts(self, limit: int = 50) -> list[Transcript]:
        if limit <= 0:
            raise VoiceValidationError("list limit must be positive")
        if not self._store.exists():
            return []
        records: list[Transcript] = []
        for sidecar in sorted(self._store.glob("vtt_*.json")):
            try:
                data = json.loads(sidecar.read_text(encoding="utf-8"))
                if data.get("kind") != "transcript":
                    continue
                records.append(_transcript_from_dict(data))
            except (OSError, ValueError, VoiceValidationError):
                continue
        records.sort(key=lambda r: (r.created_at.isoformat(), r.id), reverse=True)
        return records[:limit]

    def count(self) -> int:
        if not self._store.exists():
            return 0
        return len(list(self._store.glob("vtt_*.json")))

    def health(self) -> RepositoryHealth:
        accessible = self._store.exists() and not self._closed
        writable = False
        detail: str | None = None
        if accessible:
            try:
                probe = self._store / ".voice_write_probe"
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
            utterance_count=total,
            detail=detail,
        )

    def close(self) -> None:
        self._closed = True
