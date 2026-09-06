# J.A.R.V.I.S. Roadmap — "Just Jarvis" (1–2 years)

> Goal: a real talking house-AI — voice, memory, chores, basic sight,
> local-first, zero-cost. No suits. Status: Phases 0–10 substrate is done
> (959 tests, all HEALTHY); everything below builds on it, never rewrites it.

## Rules for all roadmap work

1. Substrate is frozen — extend `jarvis/voice|memory|task|vision|interface/`,
   never re-architect.
2. Zero-cost + local-first hold (see `docs/DEPENDENCY_POLICY.md` — any new
   dependency needs written justification; stdlib preferred).
3. Every new tool goes through `ToolService.execute` (no bypass), every new
   loop carries the Phase 7/10 guardrails (bounds, timeouts, audit).
4. Stubs stay honest until replaced: mock → real backend swaps must flip the
   health detail string and the docs in the same commit.

## Phase A — It talks (months 1–3)

Replace `jarvis/voice/` stub backends with real local ones:
wake word (openWakeWord), STT (faster-whisper), TTS (Piper). Model files live
under `C:\JARVIS\models\` (config-overridable), never downloaded by code —
operator fetches once, service degrades to `unavailable` without them.
CLI stays `jarvis voice health|listen|speak`; `voice health` must report the
real backend name instead of `mock`.

## Phase B — It remembers (months 4–6)

Semantic-memory ingestion over the Phase 3 store: deliberate-save rule stays,
but saving gets one-command easy (`memory remember` already exists — add a
deterministic **daily digest** of episodic records first, embeddings later).
Local embed model (Ollama) + SQLite-backed vector/FTS retrieval; no cloud.

## Phase C — It does chores (months 7–9)

Scheduler + persistent goals on the Phase 7 graph (morning briefing, repo
watchdog), plus new permissioned tools: browser (Playwright), Home Assistant
(local smart home), desktop notifications. Each tool: risk-rated, policy-hooked,
tested allow/ask/deny like Phase 4.

## Phase D — It sees, a bit (months 10–12)

Screenshots + local VLM (Moondream via Ollama) into `jarvis/vision/`,
replacing `[stub-no-ocr]` with real descriptions; grounded clicks gated at
HIGH_WRITE minimum through the standard pipeline.

## Phase E — It feels present (year 2)

Real local web HUD (voice + dashboard + approval UI), consistent personality,
multi-step household routines, hardening from daily use.

## Progress log

| Date | Increment | Status |
|---|---|---|
| 2026-09-05 | Roadmap written; `memory digest` deterministic episodic rollup | Committed (`3afdaad`), pushed |
| 2026-09-06 | Legacy models housed in `legacy/` (Jarvis-SSS scaffold + jarvis-main donor); `jarvis briefing` deterministic daily brief (health + episodes + open tasks/plans + delegation) | Built, 968 tests green, uncommitted |
