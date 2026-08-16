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
| Status | **Phase 0 — Architecture** (foundation only, no runtime features yet) |

---

## Current Status (Phase 0)

Phase 0 delivers the foundation only:

- Git repository with `main` branch
- Module directory structure (`jarvis/`)
- Architecture, interfaces, configuration, security, OpenCode integration,
  testing, and dependency policy documents (`docs/`)
- Zero runtime dependencies (see `pyproject.toml`)

**No runtime features have been implemented yet.** Voice, vision, autonomy,
memory, tools, and HUD are designed but deliberately not built.

## Development Phases

| Phase | Goal | Status |
|---|---|---|
| 0 | Architecture & foundation | **In progress** |
| 1 | Core runtime (lifecycle, config, events, CLI) | Not started |
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
└── pyproject.toml   → project metadata; zero runtime dependencies
```

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