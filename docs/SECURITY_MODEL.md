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