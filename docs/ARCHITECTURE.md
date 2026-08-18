# Architecture

> Status: **Phase 2 — intelligent provider layer implemented**. This is the
> contract that all modules must honor. It may be refined by the architect,
> but not silently violated by implementation. Phase 2 adds full detail for
> the intelligence section that Phase 0 sketched and Phase 1 listed.

## 1. Mission

J.A.R.V.I.S. is a modular, local-first, zero-cost personal AI operating system.
It understands objectives, plans, acts through permissioned tools, remembers
useful facts, delegates coding to OpenCode, monitors long-running work, and
verifies results before claiming success.

## 2. Absolute Rules

1. **Zero cost** — no paid APIs, subscriptions, hosting, databases, or SaaS.
   External services are optional, never required.
2. **Local-first** — every capability that can run locally (STT, TTS, wake word,
   memory, embeddings, control, state, logs, config) runs locally.
3. **Provider independence** — the core depends on the `AIProvider`
   abstraction, never on OpenCode or any specific model vendor. Removing
   OpenCode must not break the core.
4. **OpenCode is an agent/tool, not J.A.R.V.I.S.** — J.A.R.V.I.S. owns
   understanding, planning, state, delegation, monitoring, permissions,
   verification, and reporting. OpenCode does implementation work only, through
   its supported HTTP server/API (never screen scraping or UI automation).
5. **No unrestricted computer access** — every action passes the security
   layer. An LLM asking for a shell does not get one.
6. **Infrastructure first, UI later** — no premature animation/HUD work.

## 3. High-Level Diagram

```text
                         USER
                          │
                ┌─────────▼─────────┐
                │  J.A.R.V.I.S.     │
                │  CORE RUNTIME     │   lifecycle, config, events,
                └─────────┬─────────┘   sessions, task coordination
                          │
        ┌─────────────────┼──────────────────┐
        │                 │                  │
        ▼                 ▼                  ▼
    Intelligence       Memory             Planning
   (AIProvider)     (working/long-term/   (tasks, steps,
     abstraction      episodic/semantic)    retries)
        │                 │                  │
        └─────────────────┼──────────────────┘
                          ▼
                  ┌───────────────┐
                  │ Tool System   │  typed, risk-rated, permission-aware
                  └───────┬───────┘
      ┌──────────┬────────┼────────┬──────────┐
      ▼          ▼        ▼        ▼          ▼
   Windows     Files   Terminal  Browser     Git
      │          │        │        │          │
      └──────────┴────────┼────────┴──────────┘
                          ▼
                  ┌───────────────┐
                  │ Security Layer│  allow / ask / deny + risk levels
                  └───────────────┘

        Voice / Text / Future Vision
                    ▼
               JARVIS CORE
                    │
              OpenCode Integration
                    │
             Coding Specialist (DeepSeek V4 Flash)
```

## 4. Module Map

| Module | Responsibility | Phase |
|---|---|---|
| `core/` | Lifecycle, service registry, session coordination, startup/shutdown | 1 |
| `events/` | Event bus, structured serializable events | 1 |
| `configuration/` | Validated config loading (file + env), secrets handling | 1 |
| `observability/` | Structured logs, spans, activity reconstruction | 1 |
| `interface/` | CLI, terminal/simple web/voice entry points | 1 |
| `intelligence/` | `AIProvider` abstraction, local provider, model router, structured output, streaming | 2 |
| `memory/` | SQLite storage, memory types, retrieval, provenance | 3 |
| `tools/` | Typed tool registry (files, terminal, apps, screenshot, clipboard, git, browser) | 4 |
| `integration/` | OpenCode client: health, sessions, events, delegation, results | 5 |
| `voice/` | Wake word, STT, TTS, voice session management | 6 |
| `planning/` | Planner, task graph, execution loop, retries, verification, persistence | 7 |
| `agents/` | Composable agents (research, general) built on planning +
  intelligence | 7+ |
| `security/` | Permission manager, risk levels, audit, secrets policy | 9 |
| `vision/` | Screenshot analysis, UI understanding (optional) | 8 |
| `storage/` | Local filesystem layout, archive policy (Google Drive = external archive only) | 1 |
| `tests/` | Unit, integration, provider, tool, security, memory, task, OpenCode tests | all |

### Dependency direction

`core` → `events`, `configuration`, `observability` (always available)
`core` → `intelligence`, `memory`, `planning`, `tools`, `security` (subsystems)
`core` → `integration` (OpenCode) — **only via provider abstraction; never direct**

Rules:

- Modules may depend on `events`, `configuration`, `observability` freely.
- No module may depend on `core` internals (inject service handles instead).
- `integration` depends on `intelligence` interfaces, not the reverse.
- `voice`, `vision`, `interface` are leaves: they consume, never get consumed.

## 5. Core Runtime

Responsibilities: initialize services in dependency order, load validated
config, start event bus, register services, run health checks, route events,
maintain active sessions, coordinate tasks, expose internal service
interfaces, shut down cleanly (flush state, revoke permissions, stop loops).

The core **must not** contain provider-specific code:

```text
Bad:      core -> OpenCode
Good:     core -> AIProvider ──└──→ OpenCodeProvider
```

### Phase 1 implementation

Lifecycle states (`jarvis/core/lifecycle.py`):

```text
CREATED → INITIALIZING → RUNNING → STOPPING → STOPPED
                │                        ▲
                └──▶ STOPPING (failure cleanup only)
```

- Every transition is validated; invalid transitions raise `LifecycleError`.
- `Runtime.start()` (async): load config → configure logging → create
  registry/bus/storage/health → register all four as services → health checks
  → `StorageManager.ensure_directories()` → start the Intelligence service →
  dependency-ordered `registry.start_all()` → publish `RuntimeStarted` →
  `RUNNING`. Any failure runs cleanup (stop started services, close bus, flush
  logs) and ends in `STOPPED`, never `RUNNING`.
- `Runtime.stop()` is idempotent and safe before start: stop services in
  reverse dependency order → publish `RuntimeStopping` and `RuntimeStopped` →
  close the bus → flush logs → `STOPPED`.
- Health (`jarvis/core/health.py`): six checks — `core` (lifecycle state),
  `configuration` (loaded + validated), `event_bus` (open and accepting),
  `service_registry` (registered + started), `storage` (data root writable),
  and `intelligence` (at least one provider healthy — added in Phase 2).
  Overall status = HEALTHY only when every check is HEALTHY, DEGRADED when at
  least one is DEGRADED, otherwise UNHEALTHY.

## 5.1 Intelligence Layer (Phase 2)

The intelligence layer (`jarvis/intelligence/`) implements the Phase 0
`AIProvider` abstraction: provider-neutral models, a provider interface,
registry, deterministic router, adapters, mock provider, read-only benchmark,
and the service facade the runtime owns.

### Package layout

```text
jarvis/intelligence/
├── models.py      provider-neutral AIRequest/AIResponse/StreamChunk/Message/
│                  TokenUsage/ToolCall - the only types the core sees
├── provider.py    ProviderState, ProviderCapabilities, AIProvider ABC,
│                  ProviderHealth; failures become states, never crashed loops
├── registry.py    ProviderRegistry: register (dup-id rejected), get,
│                  enumerate, health, initialize/shutdown, snapshot
├── router.py      deterministic Router + Route record
├── transport.py   stdlib urllib JSON/text helpers (PyYAML stays the only
│                  third-party runtime dependency)
├── ollama.py      OllamaProvider (local) - /api/tags health + /api/chat
├── opencode.py    OpenCodeProvider (remote) - /global/health, /doc, session,
│                  prompt_async - connection only in Phase 2, no delegation
├── mock.py        MockProvider - deterministic, born READY, configurable
│                  failure/latency/capabilities, used heavily in tests
├── benchmark.py   read-only hardware diagnostics (CPU/RAM/GPU/VRAM/Ollama)
│                  - no downloads, no GPU stress, stdlib only
└── service.py     IntelligenceService facade owned by the Runtime
```

### Core models (`models.py`)

`AIRequest`: `messages`, `request_id`, `system_prompt`, `model`,
`temperature`, `max_tokens`, `tools`, `metadata`, `timeout`. Validation:
non-empty messages, tool messages need `tool_call_id`, temperature in
0.0..2.0, positive `max_tokens`/`timeout`. Messages carry `Role`
(system/user/assistant/tool) and either plain text or structured content
parts (`TextPart`/`ToolCallPart`).

`AIResponse`: `request_id`, `provider`, `model`, `content`, `finish_reason`,
`usage`, `tool_calls`, `metadata`. `TokenUsage` fields are `None` when the
provider does not report them — counts are **never fabricated**.

Streaming contract: `async for chunk in provider.stream(request)` yields
`StreamChunk` with kind `text` | `tool_call` | `metadata` | `completion` |
`error`. Streaming is capability-gated: requesting it from a non-streaming
provider is an explicit `ProviderCapabilityError`, never a silent fallback.

### Capabilities and states (`provider.py`)

`Capability`: TEXT_GENERATION, STREAMING, TOOL_CALLING, VISION,
STRUCTURED_OUTPUT, CANCELLATION, LOCAL, REMOTE, CODE_EXECUTION. Every
provider declares its set; the router filters on it.

`ProviderState`: UNINITIALIZED → INITIALIZING → READY | DEGRADED |
UNAVAILABLE | FAILED → STOPPING → STOPPED. `init()` never raises: an
unreachable target ends UNAVAILABLE, a malformed service ends DEGRADED, and
`health()` is a fail-safe probe that also never raises. A stopped provider
reports not-ok.

### Registry (`registry.py`)

Duplicate provider ids are rejected with `ServiceError`. Registry-level
iteration is failure-isolated: `health_all()` probes every provider and
reports per-provider results without raising on any single failure.

### Deterministic router (`router.py`)

Pipeline: request → capability filter → availability filter → policy →
selected provider. Ordered rules:

1. Explicit selection (request metadata `provider`, else the configured
   default) is **never** overridden — an unavailable explicitly-selected
   provider is a hard error, no fallback.
2. Capability filter: required set = TEXT_GENERATION + STREAMING (if
   requested) + TOOL_CALLING (if tools declared) + CODE_EXECUTION (for
   `task_kind: coding`); providers missing any are dropped.
3. Availability filter: only READY providers.
4. Model filter: a request `model` outside a provider's advertised
   `model_ids` drops it.
5. Policy: coding tasks prefer the remote code-execution provider; otherwise
   a local-only provider is preferred; otherwise the first capable candidate.

Every `Route` records `request_id`, `requested_provider`, `selected_provider`,
`reason`, and `alternatives` — routing decisions are always observable and
published as `AIProviderSelected`.

### Service facade (`service.py`)

`IntelligenceService` owns the registry + router, constructs adapters from
`ai.providers` config, exposes `generate` / `stream` / `cancel`, publishes
the `AI*` event stream, and registers the `intelligence` runtime health check
(HEALTHY when at least one provider is healthy). Provider failures surface as
events + states; they never crash the runtime, the bus, or other providers.

### Adapters

- **OllamaProvider** (`local`): probes `/api/tags`, generates via
  `/api/chat`, streams newline-delimited JSON, never downloads models. When
  Ollama is absent the provider reports UNAVAILABLE and the runtime keeps
  working.
- **OpenCodeProvider** (`opencode`): `/global/health` + `/doc` (OpenAPI 3.1)
  for connectivity, `/session/*` for session lifecycle, `prompt_async` for
  generation. Phase 2 scope is provider connection only — no authority
  delegation, no agent loop. API key (when configured) is read from the
  environment variable named by `api_key_env`, never from source.

## 6. Event System

All module-to-module coupling that is not a direct service call goes through
the event bus. Events are structured and JSON-serializable:

```text
UserMessageReceived        ToolRequested          TaskCreated
VoiceWakeDetected          ToolStarted            TaskStarted
SpeechTranscribed          ToolCompleted          TaskPaused
AIResponseStarted          ToolFailed             TaskCompleted
AIResponseCompleted        PermissionRequested    TaskFailed
OpenCodeConnected          PermissionGranted      MemoryCreated
OpenCodeDisconnected       PermissionDenied       MemoryRetrieved
OpenCodeEventReceived      RuntimeStarted         RuntimeStopping
RuntimeStopped             ...
```

Phase 2 added the intelligence event family (all published by the
IntelligenceService, payloads are JSON-safe and never include prompts or
secrets):

```text
AIRequestStarted         AIProviderSelected      AIStreamStarted
AIRequestCompleted       AIProviderUnavailable   AIStreamCompleted
AIRequestFailed                                  AIStreamFailed
```

Event envelope: `{id, type, timestamp, session_id?, task_id?, source, payload}`.
The bus must support publish/subscribe, per-type routing, and ordered
delivery per source. Persisted event logs are part of observability.

### Phase 1 implementation

`jarvis/events/models.py` defines the immutable `Event` envelope (above) and
the catalog of event-type constants; `RuntimeStarted`/`RuntimeStopping`/
`RuntimeStopped` were added in Phase 1 to report lifecycle transitions on the
bus. `jarvis/events/bus.py` implements `EventBus`:

- `subscribe(type | None, handler)` / `unsubscribe` / `clear`; handlers may be
  sync callables or coroutines.
- `publish(event)` is ordered (subscribers run in subscription order) and
  isolated: one failing subscriber is logged, never aborts the bus.
- `publish_nowait` schedules without awaiting; `close()` is idempotent and
  rejects further publishes with `EventError`.

## 7. Storage Layout (Windows)

```text
C:\JARVIS\
├── app\          → installed code (repo)
├── data\         → SQLite DBs, task state, memory
├── models\       → local model files (STT/TTS/embeddings)
├── workspaces\   → active dev workspaces (git repos)
├── cache\        → transient caches
├── logs\         → structured logs
├── backups\      → archives destined for Google Drive
└── runtime\      → PID files, sockets, ephemeral state
```

Host platform names (`C:\JARVIS`) are **defaults in config**, never hard-coded.

### Google Drive

Google Drive is an **external archive/backup** destination only. Active
development never happens inside a synced Drive workspace. J.A.R.V.I.S. must
not assume Drive is mounted or synced.

## 8. Observability

Structured logs (JSON) with fields: `timestamp, session_id, task_id, component,
event, action, result, duration, error`. Goal: the user can ask "what were you
doing for the last two hours?" and J.A.R.V.I.S. can reconstruct its activity
from logs + task history.

### Phase 1 implementation

`jarvis/observability/logging.py`:

- `setup_logging(cfg, logs_dir, console=True)` configures the `jarvis`
  logger: one JSON record per line to stdout and a rotating
  `<logs_dir>/jarvis.log` (10 MB, `backupCount = retention_days`).
- Records carry `timestamp, level, logger, message, component, event_id,
  session_id, task_id` plus any extra context; correlation IDs are bound via
  `correlation()` context manager (context variables), so logs inside a
  task/session inherit them automatically.
- Redaction: values under secret-shaped keys (`apiKey`, `password`, `token`,
  `secret`, `authorization`, …) and URL userinfo are masked (`***`) in JSON
  output as defense in depth — logging code must still never log credentials.

## 9. Verification (Definition of "done")

J.A.R.V.I.S. distinguishes *"I think it worked"* from *"the test/build/check
actually succeeded."* Coding tasks follow:

```text
implementation → build → tests → static checks → review → final report
```

If verification fails at any stage, the task remains incomplete. Completion
criteria are explicit fields of every task (see `docs/INTERFACES.md`).

## 10. Autonomy Guardrails

Autonomy is *goal → plan → act → observe → verify → adjust*, never "LLM gets
unrestricted computer access." Every autonomous loop requires: max iteration
count, timeout, resource limit, permission enforcement, failure handling,
cancellation, and audit logging.