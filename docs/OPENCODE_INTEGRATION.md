# OpenCode Integration Strategy

> Verified against OpenCode server documentation (Aug 2026). OpenCode exposes
> a **headless HTTP server** ("`opencode serve`") with an OpenAPI 3.1 spec —
> J.A.R.V.I.S. integrates through this supported surface only. **Never** screen
> scrape, click the UI, parse terminal screenshots, or fake human input.

## 1. Server Surface

```text
opencode serve [--port 4096] [--hostname 127.0.0.1] [--cors <origin>]
```

| Item | Value |
|---|---|
| Default endpoint | `http://127.0.0.1:4096` (config-overridable) |
| Spec | `GET /doc` — OpenAPI 3.1 (use to generate clients / validate schemas) |
| Health | `GET /global/health` → `{healthy, version}` |
| Events | `GET /event` — SSE stream (first event `server.connected`, then bus events); `GET /global/event` for global stream |
| Auth (optional) | HTTP Basic via `OPENCODE_SERVER_PASSWORD` (+ `OPENCODE_SERVER_USERNAME`, default `opencode`) — supported by the client, passed via env |

## 2. Client Architecture (`jarvis/integration/opencode/`)

```text
OpenCodeClient
├── health()            → GET /global/health
├── events()            → SSE subscription (async iterator) → mapped to JARVIS events
├── create_session()    → POST /session {parentID?, title?}
├── list_sessions()     → GET /session
├── get_session(id)     → GET /session/:id
├── get_session_status(id) → GET /session/:id (status/todo via /session/:id/todo)
├── send_message(id, parts, opts)
│       └── synchronous  POST /session/:id/message     (returns Message + Parts)
│       └── async        POST /session/:id/prompt_async → 204, then watch events
├── abort_session(id)   → POST /session/:id/abort
├── session_diff(id)    → GET /session/:id/diff        (file changes for review)
├── respond_permission(id, permissionID, response, remember)
│                       → POST /session/:id/permissions/:permissionID
└── dispose_connection() → auth cleanup behind an async HTTP client interface
```

Implementation notes:

- Generate a typed client from `/doc` at development time (or commit a
  vendored model of the relevant endpoints); do **not** hand-maintain
  ad-hoc JSON parsing per endpoint.
- All transport details (base URL, auth, timeouts, retries) are config-driven.
- The SSE event stream maps to `jarvis.events` (e.g. `OpenCodeEventReceived`,
  session progress, permission requests) so the core never polls.

## 3. Delegation Workflow

```text
1. Detect: task needs substantial coding  (planner heuristic: multi-file edits,
   build/test cycles, project-level changes)
2. Identify workspace: existing project under C:\JARVIS\workspaces\ or new repo
3. Create/reuse OpenCode session for that project root
4. Provide structured task spec: objective, constraints, files, acceptance
   criteria, forbidden actions — one message
5. Monitor: subscribe to session/event stream; task state driven by events
   (message.part.updated / todo changes), not polling
6. Receive progress events (tool calls, step completions, failures)
7. Inspect results: read final message parts + /session/:id/diff
8. Verify locally: run tests/builds/static checks ourselves (Phase 4 tools;
   Phase 7 verification) — do not trust the agent's self-report
9. Request more work: send follow-up message in the same session
10. Determine completion: completion_criteria validated by JARVIS, not OpenCode
11. Report: summary + evidence (diffs, test output) to user
```

## 4. Permission Handling (critical)

OpenCode enforces granular permissions (`read`, `edit`, `bash`, `task`,
`websearch`, `webfetch`, `external_directory`, `skill`, `question`, …) with
`allow` / `ask` / `deny`. J.A.R.V.I.S. **uses** this machinery; it never
bypasses it:

- Permission requests surface over the event stream and are answered via
  `POST /session/:id/permissions/:permissionID` with a JARVIS Security Layer
  decision:
  - decision = ALLOW → respond `{response: true, remember: <ttl-scoped>}`
  - decision = ASK → prompt the user with the exact action + risk level
  - decision = DENY → respond `{response: false}` and log audit entry
- J.A.R.V.I.S. **never** launches OpenCode in a mode that self-approves
  everything. Auto-approval is acceptable only for classes already
  auto-allowed by JARVIS policy (READ / LOW_WRITE inside trusted roots).
- `--auto`, `ask=never`, or equivalent blanket approval for unrestricted
  `bash`/`edit` is **forbidden** unless the user explicitly approved the
  exact scope; the audit log records every such approval.

## 5. Failure & Recovery

- `health()` gates delegation; unhealthy → mark provider degraded, route to
  LocalModelProvider or report, never hang.
- Session abort (`/session/:id/abort`) + JARVIS-side timeout/iteration caps.
- Disconnects: task state is persisted (SQLite) and the task survives; on
  reconnection, resume from persisted state (re-read messages/diff).
- Every delegated task carries a JARVIS-owned `completion_criteria` list; a
  task is only COMPLETED when JARVIS-side verification passes.

## 6. Mapping to AIProvider

`OpenCodeProvider` wraps the client behind `AIProvider` (see INTERFACES.md)
so the core stays provider-agnostic: `generate`/`stream` map to session
message endpoints, `tool_call` maps to delegating a task, `health_check` maps
to `/global/health`, `cancel` maps to abort. The OpenCode-specific session
lifecycle stays inside `integration/`.