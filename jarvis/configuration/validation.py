"""Configuration validation and typed construction.

Validation is strict: unknown keys, wrong types, and out-of-range values are
reported as problems that identify section, field, invalid value, and
expectation. Nothing is silently ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from jarvis.configuration.model import (
    AIConfig,
    CoreConfig,
    EventsConfig,
    JarvisConfig,
    LocalProviderConfig,
    LoggingConfig,
    MemoryConfig,
    OpenCodeProviderConfig,
    RiskLevel,
    SecurityConfig,
    SecurityMode,
    SttConfig,
    TasksConfig,
    ToolDefaultsConfig,
    ToolsConfig,
    TtsConfig,
    VoiceConfig,
    WakeWordConfig,
)

LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
PROVIDER_NAMES = frozenset({"local", "opencode"})

Kind = Literal[
    "str", "nonempty_str", "path", "positive_int", "nonneg_int", "positive_number",
    "bool", "enum", "url", "mapping",
]


def _describe(kind: Kind) -> str:
    return {
        "str": "string",
        "nonempty_str": "non-empty string",
        "path": "absolute filesystem path",
        "positive_int": "integer greater than zero",
        "nonneg_int": "integer greater than or equal to zero",
        "positive_number": "number greater than zero",
        "bool": "boolean (true/false)",
        "url": "valid http(s) URL with port in 1-65535",
        "enum": "one of",
        "mapping": "mapping",
    }[kind]


@dataclass(frozen=True)
class Field:
    kind: Kind
    expected: str
    enum_values: frozenset[str] | None = None


@dataclass(frozen=True)
class ConfigProblem:
    """A single validation problem: section, field, invalid value, expectation."""

    section: str
    field: str
    value: object
    expected: str

    @property
    def dotted_path(self) -> str:
        return f"{self.section}.{self.field}" if self.section else self.field

    def format(self) -> str:
        return f"  {self.dotted_path} = {self.value!r}\n  Expected: {self.expected}"


def format_problems(problems: list[ConfigProblem]) -> str:
    parts = ["Configuration error:"] + [p.format() for p in problems]
    return "\n".join(parts)


SCHEMA: dict[str, dict[str, Field]] = {
    "core": {
        "name": Field("nonempty_str", _describe("nonempty_str")),
        "data_dir": Field("path", _describe("path")),
        "cache_dir": Field("path", _describe("path")),
        "logs_dir": Field("path", _describe("path")),
        "runtime_dir": Field("path", _describe("path")),
        "workspaces_dir": Field("path", _describe("path")),
        "models_dir": Field("path", _describe("path")),
        "backups_dir": Field("path", _describe("path")),
        "timezone": Field("nonempty_str", _describe("nonempty_str")),
    },
    "logging": {
        "level": Field("enum", f"log level in {sorted(LOG_LEVELS)}", LOG_LEVELS),
        "format": Field("enum", "log format in ['json']", frozenset({"json"})),
        "retention_days": Field("nonneg_int", _describe("nonneg_int")),
    },
    "events": {
        "queue_maxsize": Field("positive_int", _describe("positive_int")),
        "worker_count": Field("positive_int", _describe("positive_int")),
    },
"ai": {
        "default_provider": Field(
            "enum", f"provider name in {sorted(PROVIDER_NAMES)}", PROVIDER_NAMES
        ),
        "providers": Field("mapping", "providers mapping"),
    },
    "memory": {
        "sqlite_path": Field("path", _describe("path")),
        "auto_save_conversations": Field("bool", _describe("bool")),
    },
    "tasks": {
        "max_iterations": Field("positive_int", _describe("positive_int")),
        "default_timeout_minutes": Field("positive_int", _describe("positive_int")),
        "persist_interval_seconds": Field("positive_int", _describe("positive_int")),
    },
    "tools": {
        "terminal": Field("mapping", "tool defaults mapping"),
        "browser": Field("mapping", "tool defaults mapping"),
    },
    "security": {
        "default_mode": Field(
            "enum", "mode in ['allow', 'ask', 'deny']", frozenset({"allow", "ask", "deny"})
        ),
        "allow_auto_approve_read": Field("bool", _describe("bool")),
        "destructive_confirm": Field("bool", _describe("bool")),
        "audit_log": Field("path", _describe("path")),
    },
    "voice": {
        "wake_word": Field("mapping", "wake word mapping"),
        "stt": Field("mapping", "stt mapping"),
        "tts": Field("mapping", "tts mapping"),
    },
}

TOOLS_DEFAULTS_FIELDS: dict[str, Field] = {
    "default_risk": Field(
        "enum",
        f"risk level in {sorted(r.value for r in RiskLevel)}",
        frozenset(r.value for r in RiskLevel),
    ),
}
VOICE_WAKE_WORD_FIELDS: dict[str, Field] = {
    "enabled": Field("bool", _describe("bool")),
    "model": Field("nonempty_str", _describe("nonempty_str")),
}
VOICE_STT_FIELDS: dict[str, Field] = {
    "engine": Field("nonempty_str", _describe("nonempty_str")),
    "model": Field("nonempty_str", _describe("nonempty_str")),
    "language": Field("nonempty_str", _describe("nonempty_str")),
}
VOICE_TTS_FIELDS: dict[str, Field] = {
    "engine": Field("nonempty_str", _describe("nonempty_str")),
    "voice": Field("nonempty_str", _describe("nonempty_str")),
}

PROVIDER_FIELDS: dict[str, dict[str, Field]] = {
    "local": {
        "type": Field("enum", "provider type in ['local']", frozenset({"local"})),
        "enabled": Field("bool", _describe("bool")),
        "base_url": Field("url", _describe("url")),
        "model": Field("str", _describe("str")),
        "timeout_seconds": Field("positive_number", _describe("positive_number")),
    },
    "opencode": {
        "type": Field("enum", "provider type in ['opencode']", frozenset({"opencode"})),
        "enabled": Field("bool", _describe("bool")),
        "base_url": Field("url", _describe("url")),
        "api_key_env": Field("str", _describe("str")),
        "timeout_seconds": Field("positive_number", _describe("positive_number")),
    },
}

_SCALAR_KINDS: frozenset[Kind] = frozenset(
    {
        "str", "nonempty_str", "path", "positive_int", "nonneg_int",
        "positive_number", "bool", "enum", "url",
    }
)


def _check_unknown_keys(
    section: str, known: set[str], data: dict[str, Any], errors: list[ConfigProblem]
) -> None:
    for key in sorted(data):
        if key not in known:
            errors.append(ConfigProblem(section, key, key, "no such field in this section"))


def _problem_for_field(field: Field, value: Any, section: str, name: str) -> ConfigProblem:
    expected = field.expected
    if field.kind == "enum" and field.enum_values is not None:
        options = f" {sorted(field.enum_values)}"
        if options not in expected:
            expected = f"{expected}{options}"
    return ConfigProblem(section, name, value, expected)


def _check_scalar(
    section: str, name: str, field: Field, value: Any, errors: list[ConfigProblem]
) -> None:
    if field.kind == "enum":
        if value not in (field.enum_values or frozenset()):
            errors.append(_problem_for_field(field, value, section, name))
    elif not _matches(field.kind, value):
        errors.append(_problem_for_field(field, value, section, name))


def _provider_problem(path: str, value: Any, expected: str) -> ConfigProblem:
    return ConfigProblem("ai", f"providers.{path}", value, expected)


def validate(raw: dict[str, Any]) -> list[ConfigProblem]:
    """Validate a merged raw configuration dict against the schema."""
    errors: list[ConfigProblem] = []

    for section in sorted(set(raw) - set(SCHEMA)):
        errors.append(
            ConfigProblem(
                "", section, section,
                f"no such configuration section (known: {sorted(SCHEMA)})",
            )
        )

    for section, known in SCHEMA.items():
        if section not in raw:
            continue
        raw_section = raw[section]
        if not isinstance(raw_section, dict):
            errors.append(ConfigProblem(section, "*", raw_section, "mapping"))
            continue
        _check_unknown_keys(section, set(known), raw_section, errors)
        for name, value in raw_section.items():
            if name not in known:
                continue
            field = known[name]
            if field.kind in _SCALAR_KINDS:
                if isinstance(value, dict):
                    errors.append(_problem_for_field(field, value, section, name))
                else:
                    _check_scalar(section, name, field, value, errors)
            elif field.kind == "mapping" and not isinstance(value, dict):
                errors.append(_problem_for_field(field, value, section, name))

    ai = raw.get("ai")
    if isinstance(ai, dict):
        providers = ai.get("providers")
        if providers is not None:
            if not isinstance(providers, dict):
                errors.append(
                    ConfigProblem(
                        "ai", "providers", providers, "mapping of provider name to provider config"
                    )
                )
            else:
                for provider_name in sorted(providers):
                    if provider_name not in PROVIDER_NAMES:
                        errors.append(
                            _provider_problem(provider_name, provider_name, "unknown provider name")
                        )
                        continue
                    entry = providers[provider_name]
                    if not isinstance(entry, dict):
                        errors.append(_provider_problem(provider_name, entry, "mapping"))
                        continue
                    field_schema = PROVIDER_FIELDS[provider_name]
                    _check_unknown_keys("ai", set(field_schema), entry, errors)
                    for fname, field in field_schema.items():
                        if fname not in entry:
                            errors.append(
                                _provider_problem(
                                    f"{provider_name}.{fname}", "<missing>", field.expected
                                )
                            )
                            continue
                        _check_scalar(
                            "ai", f"providers.{provider_name}.{fname}", field, entry[fname], errors
                        )

    tools = raw.get("tools")
    if isinstance(tools, dict):
        for tool_name in ("terminal", "browser"):
            entry = tools.get(tool_name)
            if entry is None:
                continue
            if not isinstance(entry, dict):
                errors.append(ConfigProblem("tools", tool_name, entry, "mapping"))
                continue
            _check_unknown_keys("tools", set(TOOLS_DEFAULTS_FIELDS), entry, errors)
            if "default_risk" in entry:
                _check_scalar(
                    "tools",
                    f"{tool_name}.default_risk",
                    TOOLS_DEFAULTS_FIELDS["default_risk"],
                    entry["default_risk"],
                    errors,
                )

    voice = raw.get("voice")
    if isinstance(voice, dict):
        for sub_name, sub_schema in (
            ("wake_word", VOICE_WAKE_WORD_FIELDS),
            ("stt", VOICE_STT_FIELDS),
            ("tts", VOICE_TTS_FIELDS),
        ):
            entry = voice.get(sub_name)
            if entry is None:
                continue
            if not isinstance(entry, dict):
                errors.append(ConfigProblem("voice", sub_name, entry, "mapping"))
                continue
            _check_unknown_keys("voice", set(sub_schema), entry, errors)
            for fname, field in sub_schema.items():
                if fname in entry:
                    _check_scalar("voice", f"{sub_name}.{fname}", field, entry[fname], errors)

    return errors


def _matches(kind: Kind, value: Any) -> bool:
    if kind == "str":
        return isinstance(value, str)
    if kind == "bool":
        return isinstance(value, bool)
    if kind in ("positive_int", "nonneg_int"):
        if isinstance(value, bool) or not isinstance(value, int):
            return False
        return value >= 1 if kind == "positive_int" else value >= 0
    if kind == "positive_number":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
    if kind == "nonempty_str":
        return isinstance(value, str) and bool(value.strip())
    if kind == "path":
        return isinstance(value, str) and bool(value.strip()) and Path(value).is_absolute()
    if kind == "url":
        if not isinstance(value, str):
            return False
        try:
            parsed = urlparse(value)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                return False
            if parsed.port is not None and not (1 <= parsed.port <= 65535):
                return False
            return True
        except ValueError:
            return False
    return False


def coerce_env(kind: Kind, raw: str) -> Any:
    """Coerce an environment-variable string to the schema value type."""
    if kind == "bool":
        lowered = raw.strip().lower()
        if lowered in ("true", "1", "yes", "on"):
            return True
        if lowered in ("false", "0", "no", "off"):
            return False
        raise ValueError(f"expected boolean, got {raw!r}")
    if kind in ("positive_int", "nonneg_int"):
        try:
            return int(raw)
        except ValueError as exc:
            raise ValueError(f"expected integer, got {raw!r}") from exc
    if kind == "positive_number":
        try:
            return float(raw)
        except ValueError as exc:
            raise ValueError(f"expected number, got {raw!r}") from exc
    return raw


def env_key_map() -> dict[str, str]:
    """Map documented environment variables to dotted schema paths.

    Only keys present in the schema are recognized; unknown JARVIS_* keys are
    ignored (they may belong to other tooling).
    """
    mapping: dict[str, str] = {}
    for section, fields in SCHEMA.items():
        for name in fields:
            if name in ("providers", "terminal", "browser", "wake_word", "stt", "tts"):
                continue
            mapping[f"JARVIS_{section.upper()}__{name.upper()}"] = f"{section}.{name}"
    for provider in PROVIDER_NAMES:
        for name in PROVIDER_FIELDS[provider]:
            mapping[f"JARVIS_AI__PROVIDERS__{provider.upper()}__{name.upper()}"] = (
                f"ai.providers.{provider}.{name}"
            )
    return mapping


def apply_env(raw: dict[str, Any], environ: dict[str, str]) -> None:
    """Mutate raw in place with recognized environment overrides."""
    for env_name, dotted in env_key_map().items():
        if env_name not in environ:
            continue
        section, _, rest = dotted.partition(".")
        field = SCHEMA[section][rest] if "." not in rest else None
        kind: Kind = "nonempty_str"
        if field is not None:
            kind = field.kind
        elif dotted.startswith("ai.providers."):
            parts = dotted.split(".")
            kind = PROVIDER_FIELDS[parts[2]][parts[3]].kind
        try:
            value = coerce_env(kind, environ[env_name])
        except ValueError as exc:
            raise ValueError(f"{env_name}: {exc}") from exc
        _set_dotted(raw, dotted, value)


def _set_dotted(raw: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    node = raw
    for part in parts[:-1]:
        if not isinstance(node.get(part), dict):
            node[part] = {}
        node = node[part]
    node[parts[-1]] = value


def build_config(raw: dict[str, Any]) -> JarvisConfig:
    """Build the typed, frozen configuration from validated raw data."""

    def p(section: str, name: str) -> Path:
        return Path(str(raw[section][name]))

    core = CoreConfig(
        name=str(raw["core"]["name"]),
        data_dir=p("core", "data_dir"),
        cache_dir=p("core", "cache_dir"),
        logs_dir=p("core", "logs_dir"),
        runtime_dir=p("core", "runtime_dir"),
        workspaces_dir=p("core", "workspaces_dir"),
        models_dir=p("core", "models_dir"),
        backups_dir=p("core", "backups_dir"),
        timezone=str(raw["core"]["timezone"]),
    )

    logging = LoggingConfig(
        level=str(raw["logging"]["level"]).upper(),
        format=str(raw["logging"]["format"]),
        retention_days=int(raw["logging"]["retention_days"]),
    )

    events = EventsConfig(
        queue_maxsize=int(raw["events"]["queue_maxsize"]),
        worker_count=int(raw["events"]["worker_count"]),
    )

    local_data = raw["ai"]["providers"]["local"]
    opencode_data = raw["ai"]["providers"]["opencode"]
    ai = AIConfig(
        default_provider=str(raw["ai"]["default_provider"]),
        local=LocalProviderConfig(
            type=str(local_data["type"]),
            enabled=bool(local_data["enabled"]),
            base_url=str(local_data["base_url"]),
            model=str(local_data["model"]),
            timeout_seconds=float(local_data["timeout_seconds"]),
        ),
        opencode=OpenCodeProviderConfig(
            type=str(opencode_data["type"]),
            enabled=bool(opencode_data["enabled"]),
            base_url=str(opencode_data["base_url"]),
            api_key_env=str(opencode_data["api_key_env"]),
            timeout_seconds=float(opencode_data["timeout_seconds"]),
        ),
    )

    memory = MemoryConfig(
        sqlite_path=p("memory", "sqlite_path"),
        auto_save_conversations=bool(raw["memory"]["auto_save_conversations"]),
    )

    tasks = TasksConfig(
        max_iterations=int(raw["tasks"]["max_iterations"]),
        default_timeout_minutes=int(raw["tasks"]["default_timeout_minutes"]),
        persist_interval_seconds=int(raw["tasks"]["persist_interval_seconds"]),
    )

    tools = ToolsConfig(
        terminal=ToolDefaultsConfig(default_risk=RiskLevel(str(raw["tools"]["terminal"]["default_risk"]))),
        browser=ToolDefaultsConfig(default_risk=RiskLevel(str(raw["tools"]["browser"]["default_risk"]))),
    )

    security = SecurityConfig(
        default_mode=SecurityMode(str(raw["security"]["default_mode"])),
        allow_auto_approve_read=bool(raw["security"]["allow_auto_approve_read"]),
        destructive_confirm=bool(raw["security"]["destructive_confirm"]),
        audit_log=p("security", "audit_log"),
    )

    voice = VoiceConfig(
        wake_word=WakeWordConfig(
            enabled=bool(raw["voice"]["wake_word"]["enabled"]),
            model=str(raw["voice"]["wake_word"]["model"]),
        ),
        stt=SttConfig(
            engine=str(raw["voice"]["stt"]["engine"]),
            model=str(raw["voice"]["stt"]["model"]),
            language=str(raw["voice"]["stt"]["language"]),
        ),
        tts=TtsConfig(
            engine=str(raw["voice"]["tts"]["engine"]),
            voice=str(raw["voice"]["tts"]["voice"]),
        ),
    )

    return JarvisConfig(
        core=core,
        logging=logging,
        events=events,
        ai=ai,
        memory=memory,
        tasks=tasks,
        tools=tools,
        security=security,
        voice=voice,
    )
