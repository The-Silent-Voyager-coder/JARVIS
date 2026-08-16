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
| Status | **Phase 1 — Core Runtime** (lifecycle, configuration, events, CLI) |

---

## Current Status (Phase 1)

Phase 1 delivers a running core runtime:

- **Types-first configuration**: defaults → `config/jarvis.yaml` →
  `JARVIS_*` environment variables, validated against a schema and frozen into
  typed records (`jarvis.configuration`)
- **Event bus**: ordered dispatch, subscriber failure isolation, graceful
  close (`jarvis.events`)
- **Lifecycle**: `CREATED → INITIALIZING → RUNNING → STOPPING → STOPPED` with
  startup-failure cleanup (`jarvis.core`)
- **Service registry**: dependency-ordered start/stop with rollback on
  failure
- **Health**: component health checks + overall status
- **Structured logging**: JSON on stdout and `<logs_dir>/jarvis.log`
  (rotating), correlation IDs, secret redaction (`jarvis.observability`)
- **CLI**: `jarvis config validate`, `jarvis health`, `--help`, `--version`

**Not yet implemented**: AI providers, OpenCode integration, memory, tools,
voice, vision, autonomy, HUD (Phases 2–10).

## Development Phases

| Phase | Goal | Status |
|---|---|---|
| 0 | Architecture & foundation | **Done** |
| 1 | Core runtime (lifecycle, config, events, CLI) | **Done** |
| 2 | Intelligence (AIProvider abstraction, model router) | Not started |
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

# run the test suite, linter, and type checker
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy jarvis
```

Exit codes: `0` success, `1` general failure, `2` invalid configuration/input.

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