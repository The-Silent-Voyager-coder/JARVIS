# Security Model

## 1. Principle

J.A.R.V.I.S. must **never** give an LLM unrestricted computer access. Every
action passes through the permission layer. An agent asking for a shell, a
delete, or a registry change is evaluated like any other action.

## 2. Risk Levels (every tool/action gets one)

| Level | Examples | Default handling |
|---|---|---|
| `READ` | list/inspect files, screenshot, system info | auto-allow (respecting scope) |
| `LOW_WRITE` | create/modify normal project files | allow within approved workspaces; ask elsewhere |
| `HIGH_WRITE` | delete files, modify system or global config | **ask** (explicit user confirmation) |
| `SYSTEM` | admin ops, service control, firewall/network, credential access | **ask + confirmation**, usually deny |
| `FORBIDDEN` | explicitly prohibited; configured in `security.deny` | deny, always (logged) |

Classification rules:

- The **most dangerous** permitted class must always be explicit: no action
  exceeds its declared risk level (a tool cannot silently escalate).
- Path scoping: `LOW_WRITE` under `C:\JARVIS\workspaces\...` is safer than the
  same class at `C:\Windows`; scope must be part of the decision. Actions
  outside configured trusted roots are treated as one level higher.
- No `SYSTEM` privilege is requested unless a task explicitly needs it and the
  user confirms; the app should run non-elevated by default.

## 3. Decision Modes

```text
allow  → execute without asking (scoped, TTL-bounded)
ask    → surface a structured confirmation to the user (what/where/risk), wait
deny   → refuse, log audit entry
```

- Default mode is **`ask`** (`security.default_mode`).
- READ actions within trusted roots may be auto-approved.
- A grant is scoped + bounded (`ttl`, path prefix, task id) and revocable.
- Previously denied actions require re-approval; auto-repeat of denied actions
  by an agent loop is blocked and logged.

## 4. OpenCode Interaction

- OpenCode's own granular permissions (`read`, `edit`, `bash`, `task`,
  `websearch`, `webfetch`, `external_directory`, `skill`, `question`, … with
  `allow`/`ask`/`deny`) are used **as the enforcement layer**, not bypassed.
- We never invoke OpenCode with unrestricted auto-approval. `--auto` style
  mode is only considered when the equivalent action would already be
  auto-allowed by J.A.R.V.I.S. policy; otherwise approvals are surfaced.
- J.A.R.V.I.S. passes its own permission decision to OpenCode (or prompts the
  user), rather than letting the agent self-approve destructive actions.

## 5. Audit Log

Append-only audit entries:

```text
timestamp, session_id, task_id, action, permission_class,
risk_level, decision, user_response, scope, duration, error
```

Audit log location: `C:\JARVIS\data\audit.log` (config-overridable).
Audit writes are synchronous and cannot be disabled by agents.

## 6. Threads (implemented Phase 9; design now)

- Permission manager with policy file (`security.policy` section of config).
- Sandboxing for high-risk processes (timeout, working-dir jail, no network
  where possible, no admin token).
- Secrets management: in-memory only, sourced from env; never logged or
  serialized.
- Destructive-action confirmations: structured UI prompt (not plain
  "ok?"), showing exact command/paths.

## 7. What These Rules Mean for Agents

- An agent loop may retry a failed action; it may **not** retry a denied
  action.
- Every autonomous loop carries: max iterations, timeout, resource limit,
  permission enforcement, failure handling, cancellation, audit logging.

## 8. Memory Privacy Rules (implemented Phase 3)

- **No secret storage.** The memory subsystem never stores credentials,
  tokens, or API keys; inspection (`jarvis memory list|get|stats|search`)
  never exposes them by design — memory is for curated facts, not secrets.
- **Content never leaves the machine unencrypted by default.** The SQLite
  database is a local file under `C:\JARVIS\data\` (config-overridable).
- **No automatic conversation storage.** `auto_save_conversations` cannot be
  enabled — validation refuses `true` with an explicit error. Memory writes
  always require a deliberate save decision.
- **Events and logs carry no content.** `MemoryCreated/Updated/Deleted/
  Expired/Retrieved` payloads and INFO-level logs contain only
  `memory_id`, `memory_type`, `source`, `provenance`, `session_id`. The CLI
  prints content only with an explicit `--content` flag; JSON output redacts
  it by default.
- **Deletion is real and inspectable.** `forget()`/`delete` soft-delete
  (auditable, `MemoryDeleted` event); `--include-deleted` makes deleted rows
  visible for verification; expired memories are swept into the deleted
  state. No unconfirmed bulk deletion: a filtered delete requires an
  explicit `--yes`.
- **Inspectability is a feature.** Every memory carries source, provenance,
  confidence, and timestamps so the user can audit why a fact exists — and
  remove it without AI services.
- **Corrupted databases are never deleted to repair.** Degradation is
  reported (`unavailable`, file kept as-is) so data loss is never
  automatic.

## 9. Tool System Security (implemented Phase 4)

The Phase 4 tool layer (`jarvis/tools/`) turns the design above into the
enforcement layer every tool execution passes through. Full contract:
`docs/TOOLS.md`.

- **One pipeline, no bypass.** AI and CLI executions share
  `ToolService.execute`: registry → policy → decision → approval → execution
  → audit events. `critical` risk is denied in every mode; an `ASK` with no
  approval provider is denied (fail-closed).
- **Risk model.** Tool risks are `safe`/`low`/`medium`/`high`/`critical`
  (the §2 vocabulary maps: READ ≈ safe/low, LOW_WRITE ≈ medium,
  HIGH_WRITE ≈ high, SYSTEM/FORBIDDEN ≈ critical). Category default risks in
  config keep the §2 names (`LOW_WRITE`, `READ`, …) as base risks.
- **Modes.** `security.mode`: `normal` (default), `lockdown` (only `safe`),
  `development` (also auto-approves `medium`). `low` is auto-approved when
  `security.allow_auto_approve_read` is true (the default).
- **Scope is part of the decision.** Path arguments are canonicalized
  against the explicit working directory and checked against
  `allowed_roots`/`denied_roots` before any execution; paths outside the
  roots are denied, not escalated. Protected files (`memory.db`, `.env`,
  secret-stemmed names) are always denied.
- **No silent escalation.** The shell classifier can only raise a command's
  risk (`safe`/`restricted`/`dangerous`/`forbidden`); `forbidden` and
  `dangerous` commands are denied outright in every mode.
- **No `SYSTEM` privilege ever requested.** No tool requests elevation; the
  app runs non-elevated.
- **Secrets never reach tools.** Environments are scrubbed of `JARVIS_*`
  secret-shaped variables before tools see them; tools cannot inject
  secret-shaped arguments; `system.info` output is redacted before it can
  leak environment values.
- **Every attempt is audited.** `ToolRequested` … `ToolDenied` events carry
  `request_id`/`tool_id`/`risk_level`/`session_id`/`task_id` and reasons;
  complete sensitive argument values are never published.
- **Bounded execution.** No `shell=True`; every subprocess has a timeout and
  bounded output; a crashing tool becomes a failed result, never a crashed
  process.
- **Phase 4 intentional absences.** No delete tool, no process-kill tool,
  and no `network`/`browser`/`gui` tools. §6 (permission manager with policy
  files, sandboxing, audit file) remains Phase 9 hardening scope.