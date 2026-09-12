"""Bounded local-first voice (Phase 6): wake word, STT/TTS stubs, service."""

from greatsage.voice.file_repository import FileVoiceRepository
from greatsage.voice.limits import VoiceLimits, default_limits, resolve_limits
from greatsage.voice.models import (
    SpeechResult,
    Transcript,
    VoiceBackend,
    WakeResult,
)
from greatsage.voice.repository import RepositoryHealth, VoiceRepository
from greatsage.voice.service import VoiceService
from greatsage.voice.stt import MockSTTBackend, OfflineSTTBackend, STTManager
from greatsage.voice.tools import (
    VoiceListenTool,
    VoiceSpeakTool,
    VoiceWakeTool,
    register_voice_tools,
)
from greatsage.voice.tts import MockTTSBackend, OfflineTTSBackend, TTSManager, encode_wav
from greatsage.voice.wakeword import KeywordWakeDetector, WakeWordDetector

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
