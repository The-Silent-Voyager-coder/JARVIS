"""Voice repository tests: persistence, id scoping, health."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.exceptions import VoiceValidationError
from jarvis.voice.file_repository import FileVoiceRepository
from jarvis.voice.models import new_utterance_id
from jarvis.voice.stt import STTManager
from jarvis.voice.tts import TTSManager


def test_save_and_get_transcript(tmp_path: Path) -> None:
    repo = FileVoiceRepository(tmp_path / "voice")
    repo.initialize()
    record = STTManager().listen_text("hello")
    repo.save_transcript(record)
    found = repo.get_transcript(record.id)
    assert found is not None and found.text == record.text
    assert repo.get_transcript(new_utterance_id()) is None


def test_save_and_get_speech(tmp_path: Path) -> None:
    repo = FileVoiceRepository(tmp_path / "voice")
    repo.initialize()
    audio, record = TTSManager().speak("hi there")
    repo.save_speech(record, audio)
    found = repo.get_speech(record.id)
    assert found is not None
    assert found[0].id == record.id
    assert found[1] == audio


def test_save_speech_rejects_size_mismatch(tmp_path: Path) -> None:
    repo = FileVoiceRepository(tmp_path / "voice")
    repo.initialize()
    _audio, record = TTSManager().speak("hi")
    with pytest.raises(VoiceValidationError):
        repo.save_speech(record, b"short")


def test_crafted_id_cannot_escape(tmp_path: Path) -> None:
    repo = FileVoiceRepository(tmp_path / "voice")
    repo.initialize()
    with pytest.raises(VoiceValidationError):
        repo.get_transcript("../evil")
    with pytest.raises(VoiceValidationError):
        repo.get_transcript("vtt_nothex!!")


def test_list_and_count_and_health(tmp_path: Path) -> None:
    repo = FileVoiceRepository(tmp_path / "voice")
    repo.initialize()
    assert repo.count() == 0
    repo.save_transcript(STTManager().listen_text("one"))
    repo.save_transcript(STTManager().listen_text("two"))
    assert repo.count() == 2
    assert len(repo.list_transcripts(limit=1)) == 1
    health = repo.health()
    assert health.accessible and health.writable
    assert health.utterance_count == 2
    with pytest.raises(VoiceValidationError):
        repo.list_transcripts(limit=0)


def test_closed_repository_rejects_writes(tmp_path: Path) -> None:
    repo = FileVoiceRepository(tmp_path / "voice")
    repo.initialize()
    repo.close()
    with pytest.raises(VoiceValidationError):
        repo.save_transcript(STTManager().listen_text("late"))
