# Core Interfaces

> Status: **Phase 1 implementation notes added**. Sections 6 and 7 are now
> implemented (`jarvis.core.registry`, `jarvis.configuration`); the remaining
> sections stay design contracts for later phases. Notation: Python typing +
> dataclass sketches; exact package layout may shift, semantics must not.

## 1. AIProvider Abstraction

```python
class ProviderCapabilities:
    streaming: bool
    tool_calls: bool
    structured_output: bool
    model_ids: list[str]
    context_window: int | None
    max_output_tokens: int | None

class GenerationRequest:
    messages: list[Message]
    model: str | None           # provider-selected if None
    temperature: float | None
    max_tokens: int | None
    tools: list[ToolSpec] | None
    response_schema: dict | None    # structured output
    timeout_seconds: float | None

class GenerationResult:
    text: str
    tool_calls: list[ToolCall] | None
    model: str
    usage: TokenUsage | None
    finish_reason: str

class AIProvider(Protocol):
    def get_capabilities(self) -> ProviderCapabilities: ...
    def generate(self, request: GenerationRequest) -> GenerationResult: ...
    def stream(self, request: GenerationRequest) -> Iterator[StreamChunk]: ...
    def tool_call(self, request: ToolCallRequest) -> ToolCallResult: ...
    def health_check(self) -> ProviderHealth: ...
    def cancel(self, request_id: str) -> None: ...
```

Requirements:

- synchronous + streaming responses
- tool calls
- structured output (`response_schema`)
- model identification and token/context metadata where available
- cancellation (`cancel(request_id)`)
- timeout handling (per-request override)

### Initial providers

| Provider | Uses | Notes |
|---|---|---|
| `LocalModelProvider` | Ollama (or equivalent local engine) | nothing hard-coded until hardware benchmarking |
| `OpenCodeProvider` | OpenCode HTTP server (default `http://127.0.0.1:4096`) | coding/deliberate-agent tasks only; wrapped as an AIProvider so the core never depends on it directly |

Future providers: registration via config (type + factory), no core changes.

### Model router

`intelligence/` exposes a router that selects a provider per request based on
configurable criteria: task class (coding vs reasoning vs quick reply),
provider health, availability, resource budget. Routes are config-driven
(`config/jarvis.example.yaml → ai`), never hard-coded in core.

## 2. Event Envelope

```python
@dataclass(frozen=True)
class Event:
    id: str                    # uuid
    type: str                  # e.g. "TaskCompleted"
    timestamp: datetime
    session_id: str | None
    task_id: str | None
    source: str                # "core", "tools.terminal", "integration.opencode"
    payload: dict              # typed per event type, JSON-serializable
```

Rules: immutable, JSON-serializable, validated against per-type payload
schemas. Consumers subscribe by type; delivery is in-order per emitter source.

## 3. Task Model

```python
@dataclass
class Task:
    id: str
    objective: str
    constraints: list[str]
    priority: int
    state: TaskState            # QUEUED RUNNING PAUSED COMPLETED FAILED CANCELLED
    steps: list[TaskStep]
    active_step: str | None
    dependencies: list[str]     # task ids
    owner: str                  # provider/agent id
    created_at: datetime
    updated_at: datetime
    retry_policy: RetryPolicy   # max_attempts, backoff, retryable_errors
    completion_criteria: list[VerificationCheck]
    metadata: dict

@dataclass
class VerificationCheck:
    kind: Literal["build", "test", "lint", "static", "manual", "custom"]
    command: str | None          # for tool-executed checks
    expected: str | None
    status: Literal["pending", "passed", "failed", "skipped"]
    evidence: list[str]          # logs/artifacts proving the outcome
```

**Persistence rule:** task state lives in SQLite, never only in RAM. Tasks
survive app restarts, provider failures, OpenCode disconnections, and network
failures. `updated_at` changes on every state transition.

## 4. Tool Contract

```python
@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict          # JSON Schema
    output_schema: dict         # JSON Schema
    permission_class: str       # e.g. "filesystem.write"
    risk_level: RiskLevel       # READ LOW_WRITE HIGH_WRITE SYSTEM FORBIDDEN
    timeout_seconds: float
    cancellable: bool

class Tool(Protocol):
    spec: ToolSpec
    def validate(self, args: dict) -> None: ...
    def execute(self, args: dict, context: ToolContext) -> ToolResult: ...
    async def cancel(self) -> None: ...
```

`ToolContext` carries session, task, and an **approved-permissions token** —
tools refuse to run without the security layer's approval for their
`permission_class` + path/scope.

## 5. Security Interfaces

```python
class PermissionDecision(Enum):
    ALLOW = "allow"
    ASK = "ask"          # requires explicit user confirmation
    DENY = "deny"

class PermissionManager(Protocol):
    def decide(self, action: SecurityAction) -> PermissionDecision: ...
    def grant(self, decision: PermissionDecision, scope: str, ttl: float | None) -> PermissionGrant: ...
    def revoke(self, grant_id: str) -> None: ...
    def audit(self, entry: AuditEntry) -> None: ...   # append-only
```

All `HIGH_WRITE` / `SYSTEM` / previously-denied actions must be recorded in
the audit log with: timestamp, session, task, action, decision, user response.

## 6. Service Registry

```python
class ServiceRegistry(Protocol):
    def register(self, name: str, service: object, dependencies: list[str]) -> None: ...
    def resolve(self, name: str) -> object: ...
    def health(self) -> dict[str, HealthStatus]: ...   # per-service
    def start_all(self) -> None: ...
    def stop_all(self) -> None: ...
```

Startup order is derived from the dependency graph; shutdown is reverse order.

### Phase 1 implementation (`jarvis/core/registry.py`)

`ServiceRegistry` matches the contract with one deviation: services are
registered with **positional dependencies** (`register(name, service,
dependencies=("...",))`) and `resolve()` is `get()`-like; there is no
per-service `health()` yet — component health is centralized in the runtime's
health registry. `start_all()` topologically orders services (cycles and
missing dependencies are rejected at registration), calls `start()` if
present, and rolls back (reverse stop) the services already started if any
service fails to start.

## 7. Configuration Surface

```python
class Config(Protocol):
    def get(self, dotted_key: str, default: Any = MISSING) -> Any: ...
    def as_dict(self) -> dict: ...
    def validate(self) -> list[ConfigError]: ...
```

Validated on load against the documented schema (`docs/CONFIGURATION.md`).
Invalid config = refused startup, never silent fallback.

### Phase 1 implementation (`jarvis/configuration/`)

The Phase 0 dotted-get surface became executable as typed records instead:

```python
load_config(config_path: str | Path | None = None,
            environ: Mapping[str, str] | None = None) -> LoadedConfig
# LoadedConfig(config: JarvisConfig, source: str, config_path: Path | None)
```

- Precedence (low → high): built-in defaults → YAML file → `JARVIS_*`
  environment variables. CLI `--config PATH` selects the file; env
  `JARVIS_CONFIG_PATH` also selects it; otherwise `config/jarvis.yaml` in the
  repo root is used if present.
- `JarvisConfig` (frozen dataclasses: `core, logging, events, ai, memory,
  tasks, tools, security, voice`) is typed and immutable — raw dicts are
  never exposed after loading.
- `validate(raw)` reports every schema problem as
  `ConfigProblem(section, field, value, expected)`; missing provider fields,
  unknown fields/sections, wrong types, and out-of-range values are all
  refused. `apply_env` only recognizes schema-documented `JARVIS_SECTION__FIELD`
  variables (double underscore), e.g. `JARVIS_LOGGING__LEVEL`,
  `JARVIS_AI__PROVIDERS__OPENCODE__BASE_URL`, `JARVIS_SECURITY__DEFAULT_MODE`.
- Invalid configuration raises `ConfigurationError`; the CLI never starts the
  runtime on invalid config and never logs secret values.

The Phase 1 CLI surface (`jarvis` console script, `jarvis/cli.py`):

```text
jarvis --version                     → "jarvis 0.2.0", exit 0
jarvis --help
jarvis config validate [--config PATH]   → "Configuration valid." + "Source: …"
jarvis health [--config PATH]            → per-component + Overall health table
```

Exit codes: `0` success, `1` general failure (e.g. runtime failed to start),
`2` invalid configuration/input.

## 8. Provider Health Contract

```python
@dataclass
class ProviderHealth:
    provider_id: str
    ok: bool
    latency_ms: float | None
    model_loaded: str | None
    detail: str | None
    last_check: datetime
```

The router uses this for failover decisions: unhealthy opencode → route
elsewhere or report, never hang indefinitely.