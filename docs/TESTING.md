# Testing Strategy

## 1. Principles

- Every module requires tests; new code without tests is not merged.
- Dangerous computer-control operations require **explicit safety tests**
  (deny paths, scope checks, audit entries, timeouts).
- Tests must run locally, offline, without paid services. External services
  are mocked at their boundary (provider adapter interfaces).
- Tests must not require administrator privileges or touch real user data.

## 2. Test Layers (directories under `tests/`)

| Layer | Directory | Covers | Real services? |
|---|---|---|---|
| Unit | `tests/unit/` | logic of each module in isolation | No |
| Integration | `tests/integration/` | module-to-module (core ↔ events ↔ config ↔ storage) | Local SQLite only |
| Provider | `tests/providers/` | AIProvider contract conformance, model router behavior | Mocked HTTP servers |
| Tools | `tests/tools/` | each tool: validation, execution, permission enforcement, cancel | Temp dirs only |
| Security | `tests/security/` | risk classification, allow/ask/deny, audit log integrity, TTL expiry, denied-action-retry blocking | No |
| Memory | `tests/memory/` | memory types, provenance, retrieval, expiration, no-auto-save guarantee | Temp SQLite |
| Task lifecycle | `tests/tasks/` | full task state machine + restart persistence | Temp SQLite |
| OpenCode | `tests/opencode/` | client against a **mock OpenCode server** implementing the documented endpoints (OpenAPI 3.1 fixture); permission-request flow, abort, SSE reconnection | Mock server |

## 3. Required Coverage for Every New Module

- happy path
- validation failures (invalid args/schema)
- timeout behavior
- cancellation
- error propagation (typed exceptions, no swallowed failures)
- permission paths: allow / ask / deny, scope mismatch, expired grant
- audit logging present on every risky action

## 4. Safety Test Examples (security layer)

- `HIGH_WRITE` delete outside trusted root → DENY + audit entry, file intact
- grant TTL expiry → expired grant refused
- agent retry of a denied action → blocked, second audit entry
- terminate tool on timeout → child process killed, no zombie processes
- config with invalid schema → refuses startup

## 5. Verification Commands

```text
pytest                     # full suite (dev extra)
pytest -m safety           # safety subset — must pass before any release
pytest tests/opencode      # mock-server OpenCode integration
pytest tests/unit/intelligence   # Phase 2 provider suite
pytest --cov=jarvis --cov-report=term-missing
ruff check .               # linter
mypy jarvis                # type checker (dev extra)
```

Target: ≥80% coverage on `jarvis/` modules; 100% on `security/` decision paths.

## 6. Phase 1 baseline

- 95 tests across `tests/unit/configuration|events|core|observability` and
  `tests/integration/test_cli.py`; coverage 93% (`jarvis/`).
- Key behaviors proven by tests: config precedence + env override + provider
  repair-by-defaults; strict validation output; event ordering, filtering and
  subscriber-failure isolation; topological registry start/stop with rollback;
  lifecycle transitions incl. startup-failure cleanup; idempotent shutdown;
  health aggregation; secret redaction and correlation-ID inheritance in JSON
  logs; CLI help/version/validate/health and exit codes 0/1/2.

## 6a. Phase 2 baseline (intelligence layer)

- 199 tests total (95 → 199). New suites under `tests/unit/intelligence/`:
  models (validation + serialization), provider registry (register/get/
  health/all-states), mock provider (deterministic output, streaming,
  configurable failure/latency), router (10 scenarios, 100% coverage —
  explicit selection never falls back, capability/availability/model filters,
  coding→CODE_EXECUTION preference, local-only preference), Ollama + OpenCode
  adapters against an in-process fake HTTP server (`conftest.py` →
  `ThreadingHTTPServer` with scripted routes), benchmark, and the
  IntelligenceService facade (events, failure isolation, health registration).
  CLI integration tests added: `ai health|providers|benchmark` incl. `--json`
  and exit codes (0 healthy, 1 any-unhealthy, 2 config error).
- **No real services in tests**: fake servers only; no internet, no API keys,
  no model downloads. Mock provider is born READY so unit tests never touch
  the network.
- Provider failure isolation is a concrete test: both adapters pointed at a
  dead endpoint produce UNAVAILABLE health and the service/CLI survive.

## 6b. Phase 3 baseline (memory layer)

- 230 tests total (199 → 230). New suites:

| Directory | Covers |
|---|---|
| `tests/unit/memory/test_memory_models.py` | type/provenance/content/confidence validation invariants, id format, `to_dict` redaction, expiry checks, filter validation |
| `tests/unit/memory/test_memory_repository.py` | schema init/health (30+ migrations, versioning, newer-schema refusal, corrupted DB kept as-is), CRUD round-trips incl. structured content, soft delete, list ordering/filters, FTS5 phrase/case/source matching, LIKE fallback, expire sweep, stats, transactional rollback (duplicate id) |
| `tests/unit/memory/test_memory_working.py` | default TTL, no-expiry (`ttl≤0`), lazy purge, sweep, newest-first ordering, remove/clear, strict session isolation |
| `tests/unit/memory/test_memory_service.py` | recording publisher fixture; start healthy/disabled/unavailable; remember defaults (config `default_confidence`) + validation; record_episode/add_semantic; ranking order + limit/offset totals; search incl. structured content; expired/deleted exclusion + explicit inclusion; update immutability + not-found; forget soft delete; expire events; working memory via service; stats/health; publisher failure swallowed; **events never carry content** (regression-tested) |

- `tests/integration/test_cli.py` gained the full memory CLI matrix: health
  (text/JSON/invalid config), stats, list (empty/JSON/filtered), get/delete
  unknown id (exit 1), delete without filters (exit 2), bulk delete without
  `--yes` (exit 2), full CRUD round-trip, filter-based bulk delete with
  `--yes`, JSON redaction of content without `--content`.
- `tests/unit/configuration/test_validation.py` gained the
  `auto_save_conversations: true` refusal (privacy rule).
- Failure isolation and corruption paths run against real temp SQLite files
  (no mocks): corrupted file → `unavailable` + file intact; unwritable parent
  dir; closed repository operations; transaction rollback leaves no partial
  rows.
- Memory tests are fully offline: no Ollama, no OpenCode, no API keys.

## 7. CI (later)

Phase 1+ adds a local pre-commit hook or GitHub Actions (free tier) running
lint (ruff), type checks (mypy), and the suite. Zero-cost constraint applies:
no paid CI services.

## 8. Rules

- Never weaken a test to make a build pass.
- Never mark a failing test "skipped" without a tracked issue + reason.
- A task is only COMPLETED when its verification steps actually passed —
  tests are the primary evidence (`VerificationCheck.evidence`).