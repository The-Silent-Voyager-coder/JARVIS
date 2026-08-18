# Tool System (Phase 4 implementation)

> Status: **implemented** (`jarvis/tools`, Phase 4). This documents the actual
> implementation: the security pipeline, registry, policy, built-in tools, and
> CLI. The Phase 0 tool contract lives in `docs/INTERFACES.md` §4; this file
> describes what shipped.

## 1. The Security Pipeline

Every tool execution — from an AI request or from the CLI — passes through one
pipeline. There is **no bypass path**:

```text
AI → ToolRequest → ToolRegistry → SecurityPolicy → Permission Decision
    → Approval → Tool Execution → ToolResult → Audit Events
```

- The registry resolves the tool by id and validates its input schema.
- The policy evaluates the request against the security mode and hooks,
  returning a decision: `ALLOW`, `ASK`, or `DENY` — never a boolean.
- `ASK` requests approval from the configured approval provider; without one
  the request is denied.
- Every attempt is published as an event, including denials (spec §32-33).

`ToolService` (`jarvis/tools/service.py`) owns the registry, policy, approval
provider, and event publisher. The CLI `tools execute` command drives this
exact service — executing a tool through the CLI and through an agent is the
same code path.

## 2. Core Models (`jarvis/tools/models.py`)

| Type | Purpose |
|---|---|
| `BaseTool` | Class attribute contract: `id`, `name`, `description`, `version`, `risk_level`, `category`, `capabilities`, `input_schema`, `output_schema`; `execute(args, context) -> ToolResult` |
| `ToolRequest` | `request_id`, `tool_id`, `arguments`, `source` (`ai`/`cli`), `session_id`, `task_id` |
| `ToolContext` | `working_directory`, `environment` (scrubbed), `timeout_seconds`, `max_output_bytes` — built by the service from config |
| `ToolResult` | `request_id`, `tool_id`, `success`, `output`, `error`, `metadata`, `duration_ms` |
| `ToolRisk` | `safe` / `low` / `medium` / `high` / `critical` |
| `ToolCategory` | `filesystem`, `process`, `system`, `shell` (implemented); `network`, `browser`, `gui` reserved for later phases |
| `ToolDecision` | `allow` / `ask` / `deny` |
| `ApprovalOutcome` | `approved` / `denied` / `timeout` / `cancelled` |

`validate_arguments(args, schema)` is a small JSON-schema subset validator
(object/string/integer/number/boolean/array, required, min/max lengths and
bounds). Invalid arguments raise `ToolValidationError`.

## 3. Registry (`jarvis/tools/registry.py`)

- `register(tool)` rejects duplicate ids (`ServiceError`) and invalid
  `input_schema`/`output_schema` (`ToolValidationError`).
- `get(tool_id)` raises `ToolNotFoundError` for unknown ids.
- `list_ids()` returns registered ids; `describe(tool_id)` returns the full
  declaration (id, name, description, version, risk_level, category,
  capabilities, input_schema, output_schema).
- `health()` reports `{"status", "tool_count", "tools"}`.

`register_default_tools()` (`jarvis/tools/defaults.py`) registers the Phase 4
foundational set (see §8).

## 4. Policy and Modes (`jarvis/tools/policy.py`)

`SecurityPolicy.from_config(config)` builds the policy from
`security.mode`, `tools.allowed_roots`, `tools.denied_roots`, and the
tool-category default risk levels.

| Mode | Meaning |
|---|---|
| `normal` (default) | risk matrix below (low auto-approved when `allow_auto_approve_read`) |
| `lockdown` | only SAFE tools allowed; everything else denied |
| `development` | as `normal`, plus `medium` tools auto-allowed |

Risk → decision matrix (other modes):

| Risk | `normal` | `development` |
|---|---|---|
| `safe` | ALLOW | ALLOW |
| `low` | ALLOW when `allow_auto_approve_read` (default true), else ASK | ALLOW |
| `medium` | ASK | ALLOW |
| `high` | ASK | ASK |
| `critical` | DENY | DENY |

In `lockdown` mode only `safe` tools are ALLOWed; everything else is DENYed
in every mode.

Rules:

- `critical` tools are denied in **every** mode.
- `lockdown` mode allows only `safe` tools.
- A policy `ASK` with no approval provider configured is denied
  (`ToolPermissionDeniedError`).
- Denials carry a machine-readable reason, e.g. `"lockdown"`, `"allowed
  roots"`, `"denied root"`, `"protected file"`, `"dangerous"`, `"forbidden"`,
  `"requires approval"`, `"credential"`.

### Hooks (they only tighten, never loosen)

- **PathSecurityHook** (`jarvis/tools/pathsecurity.py`): canonicalizes every
  argument named `path` (absolute/relative/`~` expansion), denies paths
  outside `allowed_roots` or inside `denied_roots`, and denies access to
  protected files: `memory.db`, `.env`, `.env.*`, and any path whose stem is
  `secret`/`token`/`credential`/`api_key`/`password`/`private_key`.
  Directories are never treated as protected.
- **ShellCommandHook** (`jarvis/tools/shell_classifier.py`): classifies the
  first token of a `shell.execute` command — `safe` / `restricted` /
  `dangerous` / `forbidden` — case- and `.exe`-insensitive. `safe` commands
  keep the risk, `restricted` escalate to `medium`, `dangerous` escalate to
  `high`, `forbidden` are denied outright (e.g. `format`, `diskpart`, `reg`,
  `bcdedit`, `shutdown`, `del`/`rm`/`rmdir`, `format`).
- **SensitiveArgumentHook**: denies arguments whose keys or values look like
  credentials (`.env`-style markers, `api_key`, `password`, `token`, …).

## 5. Environment and Execution Bounds (`jarvis/tools/environment.py`)

- `scrub_environment(environ)` removes J.A.R.V.I.S. secret variables
  (`JARVIS_*_KEY`, `*_TOKEN`, `*_SECRET`, `*_PASSWORD`, `.env` markers) from
  the environment tools see. Secret-shaped keys are matched with a
  case-insensitive marker check (including plural forms like `credentials`).
- `merge_environment(base, overrides)` rejects non-string values and
  secret-shaped keys — a tool can never smuggle secrets into its own
  environment.
- No tool ever uses `shell=True`; subprocesses are launched with explicit
  argument lists (`subprocess.run(..., shell=False)`).
- Every execution carries a timeout (`tools.execution_timeout_seconds`,
  default 30 s) and bounded output (`tools.max_output_bytes`, default 64 KiB);
  oversized results are replaced with a truncated marker and flagged in
  `result.metadata`.
- `system.info` output is serialized through the env scrubber before it can
  leak environment values.

## 6. Approvals (`jarvis/tools/approval.py`)

`ApprovalProvider` is an abstract base: `request_approval(request, tool,
reason) -> ApprovalOutcome`. The CLI installs a provider that grants approval
only when `--approve` is passed; the runtime leaves it to the caller (UI,
agent harness) to install a provider. With no provider and an `ASK` decision,
the request is denied — a fail-closed default.

## 7. Built-in Tools (Phase 4 set)

| Tool | Risk | Purpose |
|---|---|---|
| `filesystem.list` | safe | list directory entries (optionally recursive, bounded) |
| `filesystem.stat` | safe | file/directory metadata |
| `filesystem.read` | low | read a text file, bounded by output limit |
| `filesystem.mkdir` | low | create a directory tree (idempotent, never removes) |
| `filesystem.write` | medium | atomic write (or non-atomic with `atomic=false`), content capped, parent required |
| `process.list` | safe | running processes via `tasklist` |
| `process.info` | safe | single-process state by pid (read-only) |
| `system.info` | safe | OS/CPU/RAM/storage/GPU/JARVIS version (read-only) |
| `shell.execute` | high* | run a command with explicit argv; `*` final risk after classifier |

Intentional absences: **no `filesystem.delete`/`remove` tool** and **no
`process.terminate`/`kill` tool** (spec §20, §22). `network`/`browser`/`gui`
categories are reserved for later phases.

## 8. Configuration

```yaml
security:
  mode: normal                    # normal | lockdown | development
  allow_auto_approve_read: true   # auto-approve `low` risk (default true)
tools:
  working_directory: C:/JARVIS/workspaces   # explicit cwd for every tool
  execution_timeout_seconds: 30.0
  max_output_bytes: 65536
  allowed_roots: [C:/JARVIS/workspaces]     # path checks apply here
  denied_roots: []                          # explicit denials win
  terminal:
    default_risk: LOW_WRITE                 # base risk for shell.execute
  browser:
    default_risk: READ                      # reserved category
```

Environment overrides use the double-underscore convention, e.g.
`JARVIS_TOOLS__ALLOWED_ROOTS`, `JARVIS_SECURITY__MODE`.

## 9. CLI (`jarvis tools`)

```text
jarvis tools list [--config PATH] [--json]      → every registered tool
jarvis tools info ID [--config PATH] [--json]   → one tool declaration
jarvis tools health [--config PATH] [--json]    → service health + mode
jarvis tools execute ID [--json] [--approve]    → run one tool through the
        [--session-id SID] [--config PATH]      →   full security pipeline
        [key=value ...]
```

- `tools execute` uses `ToolService.execute` — the identical pipeline agents
  use. Medium/high-risk tools without `--approve` fail with "no approval
  provider configured" (exit 1); denied commands/paths exit 1 with the denial
  reason; invalid arguments or unknown tools exit 2.
- `--json` prints the full `ToolResult` (including `metadata` and
  `duration_ms`); text mode prints a summary.
- Audit events for CLI executions are published exactly like AI executions.

## 10. Audit Events (spec §32-33)

Published by the service on the event bus (source `tools`); payloads carry
`request_id`, `tool_id`, `risk_level`, `source`, `session_id`, `task_id` —
and never complete sensitive arguments:

| Event | Meaning |
|---|---|
| `TOOL_REQUESTED` | attempt starts (unknown tool → immediately `TOOL_FAILED`) |
| `TOOL_ALLOWED` | policy allowed (directly or after approval) |
| `TOOL_APPROVAL_REQUESTED` | policy asked; awaiting approval |
| `TOOL_APPROVED` / `TOOL_REJECTED` | approval provider outcome |
| `TOOL_STARTED` | execution began |
| `TOOL_COMPLETED` / `TOOL_FAILED` | execution outcome (+ `duration_ms`, `error`) |
| `TOOL_DENIED` | every denial, with reason |

Publisher failures are logged and never break execution; without a publisher
nothing is emitted (CLI/unit tests), but the decision flow is unchanged.

## 11. Failure Isolation

`ToolService.start()` never raises: configuration problems leave the service
`unavailable` with a detail string while the rest of the runtime keeps
working. The service registers a `tools` runtime health check — HEALTHY when
healthy or disabled, UNHEALTHY when unavailable. A `system.info`-style crash
inside a tool becomes a failed result with `error`, never a crashed process.

## 12. Out of Scope (Phase 4)

The AI tool-calling loop (model chooses tools from `AIRequest.tools`) and
OpenCode delegation of tool calls are Phase 5+. Network/browser/GUI tools and
autonomous agents remain future work. Deleting files and killing processes
are intentionally impossible through the tool system.
