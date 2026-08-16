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
| `memory.*` | SQLite path, auto-save policy |
| `tasks.*` | max iterations, default timeout, persist interval |
| `tools.*` | per-category default risk levels |
| `security.*` | default mode (`allow`/`ask`/`deny`), auto-approve rules, audit log path |
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

- Loader: YAML parse → merge env overrides → validate against schema
  (JSON-Schema draft 2020-12 or equivalent) → freeze into immutable `Config`.
- Expose read-only `Config` object via service registry.
- Provide `jarvis config validate` CLI command early (Phase 1).