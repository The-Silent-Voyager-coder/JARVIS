"""Built-in default configuration.

Values mirror config/jarvis.example.yaml from Phase 0.
The Windows C:\\JARVIS root is a documented default (docs/CONFIGURATION.md),
never a hard-coded path in code.
"""

from __future__ import annotations

DEFAULTS: dict[str, object] = {
    "core": {
        "name": "J.A.R.V.I.S.",
        "data_dir": "C:/JARVIS/data",
        "cache_dir": "C:/JARVIS/cache",
        "logs_dir": "C:/JARVIS/logs",
        "runtime_dir": "C:/JARVIS/runtime",
        "workspaces_dir": "C:/JARVIS/workspaces",
        "models_dir": "C:/JARVIS/models",
        "backups_dir": "C:/JARVIS/backups",
        "timezone": "Asia/Kolkata",
    },
    "logging": {
        "level": "INFO",
        "format": "json",
        "retention_days": 30,
    },
    "events": {
        "queue_maxsize": 1000,
        "worker_count": 4,
    },
    "ai": {
        "default_provider": "local",
        "providers": {
            "local": {
                "type": "local",
                "enabled": True,
                "base_url": "http://127.0.0.1:11434",
                "model": "",
                "timeout_seconds": 120.0,
            },
            "opencode": {
                "type": "opencode",
                "enabled": False,
                "base_url": "http://127.0.0.1:4096",
                "api_key_env": "",
                "timeout_seconds": 300.0,
            },
        },
    },
    "memory": {
        "sqlite_path": "C:/JARVIS/data/memory.db",
        "auto_save_conversations": False,
    },
    "tasks": {
        "max_iterations": 10,
        "default_timeout_minutes": 30,
        "persist_interval_seconds": 5,
    },
    "tools": {
        "terminal": {"default_risk": "LOW_WRITE"},
        "browser": {"default_risk": "READ"},
    },
    "security": {
        "default_mode": "ask",
        "allow_auto_approve_read": True,
        "destructive_confirm": True,
        "audit_log": "C:/JARVIS/data/audit.log",
    },
    "voice": {
        "wake_word": {"enabled": False, "model": "openwakeword"},
        "stt": {"engine": "faster-whisper", "model": "small", "language": "en"},
        "tts": {"engine": "piper", "voice": "en_US-lessac-medium"},
    },
}
