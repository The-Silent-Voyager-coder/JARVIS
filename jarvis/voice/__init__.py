"""Bounded local-first voice (Phase 6): wake word, STT/TTS stubs, service."""

from jarvis.voice.file_repository import FileVoiceRepository
from jarvis.voice.limits import VoiceLimits, default_limits, resolve_limits
from jarvis.voice.models import (
    SpeechResult,
    Transcript,
    VoiceBackend,
    WakeResult,
)
from jarvis.voice.repository import RepositoryHealth, VoiceRepository
from jarvis.voice.service import VoiceService
from jarvis.voice.stt import MockSTTBackend, OfflineSTTBackend, STTManager
from jarvis.voice.tools import (
    VoiceListenTool,
    VoiceSpeakTool,
    VoiceWakeTool,
    register_voice_tools,
)
from jarvis.voice.tts import MockTTSBackend, OfflineTTSBackend, TTSManager, encode_wav
from jarvis.voice.wakeword import KeywordWakeDetector, WakeWordDetector

__all__ = [
    "FileVoiceRepository",
    "KeywordWakeDetector",
    "MockSTTBackend",
    "MockTTSBackend",
    "OfflineSTTBackend",
    "OfflineTTSBackend",
    "RepositoryHealth",
    "SpeechResult",
    "STTManager",
    "TTSManager",
    "Transcript",
    "VoiceBackend",
    "VoiceLimits",
    "VoiceListenTool",
    "VoiceRepository",
    "VoiceService",
    "VoiceSpeakTool",
    "VoiceWakeTool",
    "WakeResult",
    "WakeWordDetector",
    "default_limits",
    "encode_wav",
    "register_voice_tools",
    "resolve_limits",
]
