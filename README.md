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
| Status | **Phase 4 — Secure tool system** (files, processes, shell, system) |

---

## Current Status (Phase 4)

Phases 1–3 delivered the core runtime, the intelligence layer, and the memory
foundation; Phase 4 adds the permissioned tool system on top of all three:

- **One security pipeline, no bypass**: AI → `ToolRequest` → registry →
  security policy (ALLOW/ASK/DENY) → approval → execution → audit events.
  The CLI `tools execute` command drives the identical code path.
- **Typed tool registry**: 9 built-in tools (`filesystem.list|stat|read|
  mkdir|write`, `process.list|info`, `system.info`, `shell.execute`) with
  declared risk levels and JSON-schema validation; duplicate ids and invalid
  schemas are rejected at registration
- **Risk levels + modes**: `safe`/`low`/`medium`/`high`/`critical` with a
  per-mode decision matrix (`normal`/`lockdown`/`development`); `critical`
  tools are denied in every mode; `lockdown` allows only `safe`; policy `ASK`
  without an approval provider is denied (fail-closed)
- **Policy hooks that only tighten**: path security (allowed/denied roots,
  protected files like `memory.db`/`.env`, secret-stemmed names), shell
  command classifier (`safe`/`restricted`/`dangerous`/`forbidden`, case- and
  `.exe`-insensitive), and sensitive-argument detection (credentials denied)
- **Execution bounds**: no `shell=True` anywhere; every run has a timeout,
  bounded output (truncation marker), a scrubbed environment (JARVIS secrets
  never reach tools), and an explicit working directory
- **Intentional absences**: no `filesystem.delete` and no `process.terminate`
  tool; `network`/`browser`/`gui` categories reserved for later phases
- **Audit events**: every attempt (including denials) published with
  `request_id`/`tool_id`/`risk_level`/`session_id`/`task_id`; sensitive
  argument values are never included
- **Failure isolation**: a broken tool configuration degrades the subsystem
  to `unavailable` while the rest of the runtime keeps working
- **CLI**: `jarvis tools list|info|health|execute [--json] [--approve]`
- **No new dependencies**: stdlib only; PyYAML remains the sole runtime
  dependency

**Not yet implemented**: AI tool-calling loop and OpenCode delegation
(Phase 5), voice, vision, autonomy, HUD, and semantic-memory ingestion.

## Development Phases

| Phase | Goal | Status |
|---|---|---|
| 0 | Architecture & foundation | **Done** |
| 1 | Core runtime (lifecycle, config, events, CLI) | **Done** |
| 2 | Intelligence (AIProvider abstraction, model router) | **Done** |
| 3 | Memory (SQLite, provenance) | **Done** |
| 4 | Tools (files, terminal, processes, system) | **Done** |
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
│   ├── tools/           → tool registry, security policy, built-in tools (Phase 4)
│   └── ...              → voice, autonomy (later phases)
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

# inspect and drive the secure tool system (files/processes/shell/system)
.\.venv\Scripts\jarvis.exe tools list
.\.venv\Scripts\jarvis.exe tools info filesystem.write
.\.venv\Scripts\jarvis.exe tools health
.\.venv\Scripts\jarvis.exe tools execute system.info
.\.venv\Scripts\jarvis.exe tools execute shell.execute --approve \
    'command=["python", "--version"]'
# medium/high-risk tools need --approve; dangerous commands and paths
# outside allowed roots are denied by policy either way

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
7. `docs/TOOLS.md` — the Phase 4 tool system (pipeline, policy, CLI)
8. `docs/OPENCODE_INTEGRATION.md` — how OpenCode is integrated
9. `docs/TESTING.md` — testing strategy
10. `docs/DEPENDENCY_POLICY.md` — dependency rules

## Non-Goals (now)

- UI/HUD, animations, decorative interfaces (Phase 10)
- Voice pipeline (Phase 6)
- Vision (Phase 8)
- Autonomous agents (Phase 7)
- Any paid service integration