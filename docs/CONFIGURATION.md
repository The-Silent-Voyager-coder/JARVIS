# Configuration System

## 1. Principles

- **Externalized, never hard-coded.** Model names, paths, ports, OpenCode
  endpoint, voice engines, permissions, storage locations, resource limits —
  all come from configuration.
- **Validated.** Invalid configuration refuses startup; no silent fallbacks.
- **Layered.** Defaults → config file (`config/jarvis.yaml`) → environment
  variables → CLI overrides. Later layers win.
- **Secrets in env, never in files.** API keys/tokens live in `.env`
  (git-ignored) or the process environment. Never in YAML, never in source.

## 2. Sources (priority low → high)

| Layer | Location | Use |
|---|---|---|
| 1. Built-in defaults | `configuration/` package | sane minimums |
| 2. User config | `config/jarvis.yaml` (copy of `jarvis.example.yaml`) | normal settings |
| 3. Environment | `JARVIS_*` variables, `.env` file | machine-specific + secrets |
| 4. CLI flags | `jarvis --...` | per-run overrides |

Convention: env var for config key `security.default_mode` is
`JARVIS_SECURITY__DEFAULT_MODE` (double underscore = nesting).

## 3. Schema (authoritative — `config/jarvis.example.yaml`)

Top-level sections:

| Key | Purpose |
|---|---|
| `core.*` | identity, data/cache/logs/runtime/workspaces/models/backups dirs, timezone |
| `logging.*` | level, format, retention |
| `events.*` | bus queue size, worker count |
| `ai.*` | default provider, provider registry (local/opencode), endpoints, timeouts |
| `memory.*` | SQLite path, enable flag, auto-save policy, default confidence, retention |
| `tasks.*` | max iterations, default timeout, persist interval |
| `tools.*` | working directory, execution timeout, output cap, allowed/denied roots, per-category default risk |
| `security.*` | mode (`normal`/`lockdown`/`development`), auto-approve rules, audit log path |
| `voice.*` | wake word / STT / TTS engine + model selections |

Unknown keys or invalid values → validation errors at startup.

## 4. Secrets Policy

- `.env` / `.env.*` are git-ignored (`.gitignore` enforces this).
- `.env.example` documents variable names only.
- API keys are referenced as `*_env` names, e.g.
  `ai.providers.opencode.api_key_env: "OPENCODE_API_KEY"`; the config loader
  reads the environment at runtime.
- If a configured secret env var is unset and the feature requires it, the
  feature is disabled with a clear log — the core never guesses or fabricates
  credentials.

## 5. Default Paths

Defaults assume `C:\JARVIS\` as the data root (config override supported):

```text
C:\JARVIS\data\         SQLite DBs (memory, tasks), audit log
C:\JARVIS\models\       local models (Ollama files, whisper, piper voices)
C:\JARVIS\workspaces\   active dev workspaces
C:\JARVIS\cache\        transient caches
C:\JARVIS\logs\         structured logs
C:\JARVIS\runtime\      pid/socket/ephemeral
C:\JARVIS\backups\      archives for Google Drive
```

## 6. Implementation Notes (Phase 1)

Phase 1 ships the complete loader, validator, and CLI:

- **Loader** (`jarvis/configuration/loader.py`): deep-merges built-in defaults
  (`defaults.py`, mirroring `config/jarvis.example.yaml`) → YAML file (selected
  by `--config PATH` or `JARVIS_CONFIG_PATH`, else `config/jarvis.yaml` if
  present) → `JARVIS_*` environment variables → validates → freezes into typed
  records.
- **Validation** (`jarvis/configuration/validation.py`): schema-driven; every
  problem is reported as `section.field = value, Expected: …`; unknown
  sections/fields, wrong types, bad enums, non-absolute paths, invalid
  http(s) URLs (port 1–65535), and missing provider fields are refused with
  `ConfigurationError` — no silent fallbacks, no secrets in messages.
- **Typed config** (`jarvis/configuration/model.py`): frozen dataclasses
  (`JarvisConfig` + per-section records, `SecurityMode`/`RiskLevel` StrEnums);
  raw dicts never escape the loader.
- **Env vars**: only schema-documented keys are recognized
  (`JARVIS_SECTION__FIELD`, `JARVIS_AI__PROVIDERS__<NAME>__<FIELD>`);
  unknown `JARVIS_*` keys are ignored, and unparseable values fail with a
  `ConfigurationError` naming the variable.
- **CLI**: `jarvis config validate [--config PATH]` prints `Configuration
  valid.` + `Source:` (resolved path or `built-in defaults`), exits `0`/`2`.
- The `Config` object is exposed via the runtime: `Runtime.config
  (jarvis.configuration.model.JarvisConfig)`.

## 7. AI Provider Configuration (Phase 2)

The `ai.*` schema drives the intelligence layer (`jarvis.intelligence`):

```yaml
ai:
  default_provider: local                      # explicit selection when no
                                               # hint in the request
  providers:
    local:
      type: local                              # Ollama adapter
      enabled: true
      base_url: http://127.0.0.1:11434
      model: ""                                # provider decides
      timeout_seconds: 60
    opencode:
      type: opencode
      enabled: false                           # off by default
      base_url: http://127.0.0.1:4096
      api_key_env: ""                          # e.g. "OPENCODE_API_KEY"
      timeout_seconds: 120
```

Semantics:

- `providers.<name>.type` is an enum: `local` (Ollama adapter) or `opencode`
  (remote). Unknown or disabled types are not registered.
- `base_url` must be a valid http(s) URL (validated with port range).
- `api_key_env` names an environment variable; the value is read once at
  start and used for Bearer auth. Never put the key itself in YAML.
- `model` is the default model hint for the provider; the provider decides
  when empty (`/api/tags` for Ollama) and the router drops providers whose
  advertised models exclude an explicit request model.
- The default config (`config/jarvis.example.yaml`, `configuration/defaults.py`)
  enables the local provider only; opencode is disabled until the operator
  flips it on. A missing `ai:` section is valid — defaults apply.
- `default_provider` is a fallback, not a pin: explicit request metadata
  (`metadata.provider`) wins, and an explicitly selected provider that is
  unhealthy is a routing error — never a silent switch to another provider.

CLI: `jarvis ai health|providers|benchmark [--config PATH] [--json]`.
`ai health` exits `1` when any provider is unhealthy (or both are
unavailable — the CLI survives and reports), `2` on config errors.

## 8. Memory Configuration (Phase 3)

The `memory.*` schema drives the memory subsystem (`jarvis.memory`):

```yaml
memory:
  enabled: true                          # false → subsystem disabled (health: healthy no-op)
  database_path: C:/JARVIS/data/memory.db
  auto_save_conversations: false         # ALWAYS false in Phase 3 (privacy rule)
  default_confidence: 0.8                # 0.0..1.0 when remember() omits confidence
  retention_days: 365                    # default expiry for working/episodic entries
```

Semantics:

- `enabled` gates the whole subsystem. When `false`, `jarvis health` reports
  the memory component as HEALTHY (a deliberate no-op, not an error), memory
  commands fail cleanly with an "unavailable" message, and no database file
  is created.
- `database_path` is the SQLite file; the parent directory is created on
  first use. Must be an absolute path.
- `auto_save_conversations` exists in the schema but is **forbidden to
  enable** in Phase 3: memory writes require a deliberate save decision
  (`remember()`). Validation enforces `false`.
- `default_confidence` is the confidence applied when a `remember()` call
  does not specify one; values outside 0.0–1.0 are refused.
- `retention_days` sets the default expiration for WORKING and EPISODIC
  memories created without an explicit `expires_at`. LONG_TERM and SEMANTIC
  memories are persistent unless an explicit expiration is given.

Environment overrides use the double-underscore convention:
`JARVIS_MEMORY__DATABASE_PATH`, `JARVIS_MEMORY__DEFAULT_CONFIDENCE`,
`JARVIS_MEMORY__RETENTION_DAYS`.

CLI: `jarvis memory health|stats|list|get|delete|search [--config PATH]
[--json]`. `memory health` exits `1` when the subsystem is unavailable
(e.g. corrupted database — the file is kept as-is), `2` on config errors.

## 9. Tool Security Configuration (Phase 4)

The `security.*` + `tools.*` schema drives the tool system (`jarvis.tools`):

```yaml
security:
  mode: normal                        # normal | lockdown | development
  allow_auto_approve_read: true       # development mode: `low` risk allowed
tools:
  working_directory: C:/JARVIS/workspaces   # explicit cwd for every tool
  execution_timeout_seconds: 30.0           # per-run subprocess timeout
  max_output_bytes: 65536                   # output truncation bound
  allowed_roots: [C:/JARVIS/workspaces]     # path policy applies here
  denied_roots: []                          # explicit denials win
  terminal:
    default_risk: LOW_WRITE                 # base risk for shell.execute
  browser:
    default_risk: READ                      # reserved category
```

Semantics:

- `security.mode` selects the policy matrix: `normal` (safe → allow; low →
  allow when `allow_auto_approve_read` is true — the default — else ask;
  medium/high → ask; critical → deny everywhere), `lockdown` (only `safe`
  tools), `development` (as `normal`, plus `medium` tools allowed).
- `tools.working_directory` is the explicit working directory for every
  tool; `execution_timeout_seconds` bounds every subprocess; output above
  `max_output_bytes` is replaced by a truncation marker.
- `allowed_roots`/`denied_roots` feed the path security hook: reads/writes
  outside the roots are denied; denied roots are denied even when listed as
  allowed. Protected files (`memory.db`, `.env`, secret-stemmed names) are
  always denied.
- `tools.<category>.default_risk` sets the base risk for a category's tools
  (the shell classifier can only raise it).

Environment overrides use the double-underscore convention:
`JARVIS_SECURITY__MODE`, `JARVIS_TOOLS__ALLOWED_ROOTS`,
`JARVIS_TOOLS__EXECUTION_TIMEOUT_SECONDS`.

CLI: `jarvis tools list|info|health|execute [--config PATH] [--json]
[--approve]`. See `docs/TOOLS.md` for the full tool-system contract.