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
| Status | **Phase 3 — Memory foundation** (SQLite persistence, provenance, CLI) |

---

## Current Status (Phase 3)

Phase 1 delivers the core runtime, Phase 2 the intelligence layer; Phase 3
adds the memory foundation on top of both:

- **Four memory categories**: `working` (session RAM), `long_term` (stable
  facts/preferences), `episodic` (records of J.A.R.V.I.S. actions),
  `semantic` (storage/retrieval foundation — no ingestion pipeline yet)
- **Typed `Memory` model**: `mem_<hex>` UUID ids, structured JSON or plain
  text content, `source` + `provenance` tracking, confidence 0.0–1.0,
  timezone-aware UTC timestamps, optional `expires_at`, per-session scoping,
  auditable soft delete
- **SQLite persistence** (`jarvis.memory`): schema-versioned migrations
  (stdlib only), WAL mode, FTS5 full-text search with a safe LIKE fallback,
  repository abstraction so storage can be swapped without touching business
  rules
- **Deterministic retrieval**: filters (type/source/provenance/time/
  confidence/session) + pagination, ranked by
  `0.5·relevance + 0.3·confidence + 0.2·recency` with a documented match
  reason — no embeddings, no LLM search
- **Lifecycle**: `remember()` requires a deliberate save decision (never
  automatic), default confidence and per-type retention from config,
  expiration sweep, `forget()` soft delete — nothing is ever hard-deleted
- **Memory events**: `MemoryCreated/Updated/Deleted/Expired/Retrieved` carry
  only ids/types/sources — never content
- **Failure isolation**: a corrupted/unreachable database degrades the memory
  subsystem to `unavailable` (file kept as-is) while the rest of the runtime
  keeps working
- **CLI**: `jarvis memory health|list|get|delete|stats|search [--json]`
- **No new dependencies**: stdlib `sqlite3` + FTS5; PyYAML remains the sole
  runtime dependency

**Not yet implemented**: tools, voice, vision, autonomy, HUD, full OpenCode
delegation (Phases 4–10), and semantic-memory ingestion (embeddings/vector
search are explicitly a later enhancement).

## Development Phases

| Phase | Goal | Status |
|---|---|---|
| 0 | Architecture & foundation | **Done** |
| 1 | Core runtime (lifecycle, config, events, CLI) | **Done** |
| 2 | Intelligence (AIProvider abstraction, model router) | **Done** |
| 3 | Memory (SQLite, provenance) | **Done** |
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
│   ├── memory/          → memory models, SQLite persistence, retrieval (Phase 3)
│   └── ...              → tools, voice, autonomy (later phases)
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

# inspect the memory subsystem (persistent SQLite; database created on first use)
.\.venv\Scripts\jarvis.exe memory health
.\.venv\Scripts\jarvis.exe memory stats
.\.venv\Scripts\jarvis.exe memory search "api key" --content
.\.venv\Scripts\jarvis.exe memory list --type long_term
.\.venv\Scripts\jarvis.exe memory get mem_<id> --content
.\.venv\Scripts\jarvis.exe memory delete mem_<id>   # auditable soft delete

# run the test suite, linter, and type checker
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy jarvis
```

Exit codes: `0` success, `1` general failure (e.g. a provider unhealthy or a
memory not found), `2` invalid configuration/input.

The `ai` commands probe configured providers (`ai.providers.*`); Ollama
absent or not running is fine — the provider reports `unavailable` and the
CLI still exits cleanly (exit `1` from `ai health`). No models are ever
downloaded by J.A.R.V.I.S. The `memory` commands need no AI services at all:
they read/write the local SQLite database configured under `memory.*`.
Memory content is shown only with `--content`; every command supports
`--json`.

## Reading Order

1. `docs/ARCHITECTURE.md` — how J.A.R.V.I.S. is built
2. `docs/DEVELOPMENT_RULES.md` — hard engineering rules for contributors/agents
3. `docs/INTERFACES.md` — core interfaces (AIProvider, memory, events, tasks)
4. `docs/CONFIGURATION.md` — how configuration works
5. `docs/MEMORY.md` — memory schema, lifecycle, retrieval, privacy
6. `docs/SECURITY_MODEL.md` — permissions and risk levels
7. `docs/OPENCODE_INTEGRATION.md` — how OpenCode is integrated
8. `docs/TESTING.md` — testing strategy
9. `docs/DEPENDENCY_POLICY.md` — dependency rules

## Non-Goals (now)

- UI/HUD, animations, decorative interfaces (Phase 10)
- Voice pipeline (Phase 6)
- Vision (Phase 8)
- Autonomous agents (Phase 7)
- Any paid service integration