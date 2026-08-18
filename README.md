# J.A.R.V.I.S.

**Just A Rather Very Intelligent System**

A modular, local-first, zero-cost personal AI operating system for Windows 11.

J.A.R.V.I.S. is **not** a chatbot. It is an infrastructure-first platform that
will eventually converse naturally (voice + text), remember, plan, run tools,
control the computer safely, delegate coding work to OpenCode, monitor
long-running objectives, and recover from failures.

| | |
|---|---|
| Platform | Windows 11 (ASUS Gaming V16, RTX 4050 6 GB VRAM, 16 GB RAM) |
| Cost | ₹0 / $0 — no paid APIs, no paid hosting, no paid cloud |
| Language | Python 3.11+ |
| Status | **Phase 2 — Intelligence layer** (multi-provider AI abstraction, router, CLI) |

---

## Current Status (Phase 2)

Phase 1 delivers a running core runtime (below); Phase 2 adds the intelligence
layer on top of it:

- **Provider abstraction** (`jarvis.intelligence`): provider-neutral
  `AIRequest`/`AIResponse`/`StreamChunk` models, a capability model
  (`TEXT_GENERATION`, `STREAMING`, `TOOL_CALLING`, `CODE_EXECUTION`, …),
  explicit provider states (READY/DEGRADED/UNAVAILABLE/FAILED), and a
  registry with per-provider health — a failed provider never crashes the
  runtime
- **Adapters**: `local` (Ollama via `/api/chat`, models discovered from
  `/api/tags`, no downloads) and `opencode` (remote code-execution provider,
  Phase 2 = connection only: `/global/health`, `/doc`, sessions, `prompt_async`)
- **Deterministic router**: explicit selection > capability filter >
  availability > policy (coding → code-execution provider) > local-only
  preference. Explicit selection never silently falls back.
- **Mock provider**: deterministic, offline, used by tests and as a safe
  default
- **Read-only benchmark**: CPU/RAM/GPU/VRAM/Ollama diagnostics, nothing
  downloaded, nothing stressed
- **CLI**: `jarvis ai health|providers|benchmark [--config PATH] [--json]`
- **No new dependencies**: stdlib-only HTTP transport; PyYAML remains the
  sole runtime dependency

**Not yet implemented**: memory, tools, voice, vision, autonomy, HUD,
full OpenCode delegation (Phases 3–10).

## Development Phases

| Phase | Goal | Status |
|---|---|---|
| 0 | Architecture & foundation | **Done** |
| 1 | Core runtime (lifecycle, config, events, CLI) | **Done** |
| 2 | Intelligence (AIProvider abstraction, model router) | **Done** |
| 3 | Memory (SQLite, provenance) | Not started |
| 4 | Tools (files, terminal, apps, git, browser) | Not started |
| 5 | OpenCode integration | Not started |
| 6 | Voice (wake word, STT, TTS) | Not started |
| 7 | Autonomy (planner, task graph, verification) | Not started |
| 8 | Vision | Not started |
| 9 | Security hardening | Not started |
| 10 | HUD interface | Not started |

## Repository Layout

```text
jarvis/
├── docs/            → architecture & engineering documents (read first)
├── config/          → example configuration
├── jarvis/          → Python package; one module per subsystem
│   ├── core/            → lifecycle, registry, health, runtime
│   ├── configuration/   → typed config loader + validator
│   ├── events/          → event bus + catalog
│   ├── observability/   → structured logging
│   ├── intelligence/    → providers, models, router, benchmark (Phase 2)
│   └── ...              → memory, tools, voice, autonomy (later phases)
├── tests/           → test suite (per-module subdirectories)
├── .env.example     → secret template (real secrets never committed)
└── pyproject.toml   → project metadata; PyYAML is the only runtime dependency
```

## Quick Start

```powershell
# create the virtual environment and install (editable, with dev tools)
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

# validate the configuration (defaults or your own file)
.\.venv\Scripts\jarvis.exe config validate
.\.venv\Scripts\jarvis.exe config validate --config config\jarvis.example.yaml

# boot the runtime and report component health
.\.venv\Scripts\jarvis.exe health

# inspect the AI provider layer (works with Ollama running or absent)
.\.venv\Scripts\jarvis.exe ai health
.\.venv\Scripts\jarvis.exe ai providers
.\.venv\Scripts\jarvis.exe ai benchmark

# run the test suite, linter, and type checker
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy jarvis
```

Exit codes: `0` success, `1` general failure (e.g. a provider unhealthy),
`2` invalid configuration/input.

The `ai` commands probe configured providers (`ai.providers.*`); Ollama
absent or not running is fine — the provider reports `unavailable` and the
CLI still exits cleanly (exit `1` from `ai health`). No models are ever
downloaded by J.A.R.V.I.S.

## Reading Order

1. `docs/ARCHITECTURE.md` — how J.A.R.V.I.S. is built
2. `docs/DEVELOPMENT_RULES.md` — hard engineering rules for contributors/agents
3. `docs/INTERFACES.md` — core interfaces (AIProvider, events, tasks)
4. `docs/CONFIGURATION.md` — how configuration works
5. `docs/SECURITY_MODEL.md` — permissions and risk levels
6. `docs/OPENCODE_INTEGRATION.md` — how OpenCode is integrated
7. `docs/TESTING.md` — testing strategy
8. `docs/DEPENDENCY_POLICY.md` — dependency rules

## Non-Goals (now)

- UI/HUD, animations, decorative interfaces (Phase 10)
- Voice pipeline (Phase 6)
- Vision (Phase 8)
- Autonomous agents (Phase 7)
- Any paid service integration