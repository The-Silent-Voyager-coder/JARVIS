"""Typed configuration model.

Mirrors config/jarvis.example.yaml, the Phase 0 source of truth.
All records are immutable: values are validated before construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class SecurityMode(StrEnum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class RiskLevel(StrEnum):
    READ = "READ"
    LOW_WRITE = "LOW_WRITE"
    HIGH_WRITE = "HIGH_WRITE"
    SYSTEM = "SYSTEM"
    FORBIDDEN = "FORBIDDEN"


@dataclass(frozen=True)
class CoreConfig:
    name: str
    data_dir: Path
    cache_dir: Path
    logs_dir: Path
    runtime_dir: Path
    workspaces_dir: Path
    models_dir: Path
    backups_dir: Path
    timezone: str

    @property
    def directories(self) -> tuple[Path, ...]:
        return (
            self.data_dir,
            self.cache_dir,
            self.logs_dir,
            self.runtime_dir,
            self.workspaces_dir,
            self.models_dir,
            self.backups_dir,
        )


@dataclass(frozen=True)
class LoggingConfig:
    level: str
    format: str
    retention_days: int


@dataclass(frozen=True)
class EventsConfig:
    queue_maxsize: int
    worker_count: int


@dataclass(frozen=True)
class LocalProviderConfig:
    type: str
    enabled: bool
    base_url: str
    model: str
    timeout_seconds: float


@dataclass(frozen=True)
class OpenCodeProviderConfig:
    type: str
    enabled: bool
    base_url: str
    api_key_env: str
    timeout_seconds: float


@dataclass(frozen=True)
class AIConfig:
    default_provider: str
    local: LocalProviderConfig
    opencode: OpenCodeProviderConfig

    @property
    def provider_names(self) -> tuple[str, ...]:
        return ("local", "opencode")


@dataclass(frozen=True)
class MemoryConfig:
    enabled: bool
    database_path: Path
    auto_save_conversations: bool
    default_confidence: float
    retention_days: int


@dataclass(frozen=True)
class TasksConfig:
    max_iterations: int
    default_timeout_minutes: int
    persist_interval_seconds: int


@dataclass(frozen=True)
class ToolDefaultsConfig:
    default_risk: RiskLevel


@dataclass(frozen=True)
class ToolsConfig:
    terminal: ToolDefaultsConfig
    browser: ToolDefaultsConfig


@dataclass(frozen=True)
class SecurityConfig:
    default_mode: SecurityMode
    allow_auto_approve_read: bool
    destructive_confirm: bool
    audit_log: Path


@dataclass(frozen=True)
class WakeWordConfig:
    enabled: bool
    model: str


@dataclass(frozen=True)
class SttConfig:
    engine: str
    model: str
    language: str


@dataclass(frozen=True)
class TtsConfig:
    engine: str
    voice: str


@dataclass(frozen=True)
class VoiceConfig:
    wake_word: WakeWordConfig
    stt: SttConfig
    tts: TtsConfig


@dataclass(frozen=True)
class JarvisConfig:
    """Root immutable configuration object."""

    core: CoreConfig
    logging: LoggingConfig
    events: EventsConfig
    ai: AIConfig
    memory: MemoryConfig
    tasks: TasksConfig
    tools: ToolsConfig
    security: SecurityConfig
    voice: VoiceConfig
