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
        "enabled": True,
        "database_path": "C:/JARVIS/data/memory.db",
        "auto_save_conversations": False,
        "default_confidence": 0.8,
        "retention_days": 365,
    },
    "tasks": {
        "max_iterations": 10,
        "default_timeout_minutes": 30,
        "persist_interval_seconds": 5,
    },
    "tools": {
        "working_directory": "C:/JARVIS/workspaces",
        "execution_timeout_seconds": 30.0,
        "max_output_bytes": 65536,
        "allowed_roots": ["C:/JARVIS/workspaces"],
        "denied_roots": [],
        "terminal": {"default_risk": "LOW_WRITE"},
        "browser": {"default_risk": "READ"},
    },
    "agent": {
        "enabled": True,
        "max_steps": 12,
        "max_tool_calls": 8,
        "max_wall_time_seconds": 300.0,
        "max_single_tool_calls": 3,
        "max_total_tool_output_bytes": 2097152,
        "loop_detection_threshold": 3,
    },
    "delegation": {
        "enabled": False,
        "default_provider": "opencode",
        "max_wall_time_seconds": 1800.0,
        "max_output_bytes": 4194304,
        "max_permission_requests": 50,
        "max_session_count": 3,
        "max_delegation_depth": 1,
    },
    "workspace": {
        "enabled": True,
        "max_scan_depth": 3,
        "max_entries": 500,
        "scan_timeout_seconds": 10.0,
        "database_path": "C:/JARVIS/data/workspace.db",
    },
    "planning": {
        "enabled": True,
        "max_plan_steps": 25,
        "database_path": "C:/JARVIS/data/plans.db",
    },
    "task": {
        "enabled": True,
        "max_steps": 25,
        "per_step_timeout_seconds": 30.0,
        "total_timeout_seconds": 600.0,
        "database_path": "C:/JARVIS/data/tasks.db",
    },
    "security": {
        "mode": "normal",
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
