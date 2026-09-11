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
5. **GitHub is read-only by default.** Reference code, specs, and patterns
   may be studied freely; downloading anything (code, models, binaries)
   needs the operator's explicit permission first, every time.
6. **Game automation needs the operator's ToS judgment.** Botting violates
   most games' terms (Supercell bans CoC botting accounts). The `gui.*`
   tools provide the hands; unattended game-playing loops ship only with
   explicit per-game approval and stay ASK-gated.

## Phase A — It talks (months 1–3)

Replace `jarvis/voice/` stub backends with real local ones.
SHIPPED 2026-09: Vosk STT (`vosk` + small-en model), Piper TTS
(`piper-tts` + en_GB-alan-medium), stdlib fuzzy wake-word tolerance —
see `docs/DEPENDENCY_POLICY.md` §5 for why faster-whisper lost. Model
files live under `C:\JARVIS\models\` (config-overridable), health reports
real backend names. Remaining: mic capture (`sounddevice` was tried and
removed — no speculative deps), always-on listening loop.

## Phase B — It remembers (months 4–6)

Semantic-memory ingestion over the Phase 3 store: deliberate-save rule stays,
but saving gets one-command easy (`memory digest` shipped, embeddings
shipped). SHIPPED 2026-09: Ollama `nomic-embed-text` provider (stdlib
urllib, zero new deps), `memory_embeddings` table (schema v2),
`memory search --semantic`, `memory reindex`, auto-embed on save
(best-effort), vectors die with their memory. Remaining: auto-rollups,
recall gating.

## Phase C — It does chores (months 7–9)

Scheduler + persistent goals on the Phase 7 graph (morning briefing, repo
watchdog), plus new permissioned tools: browser fetches, Home Assistant
(local smart home), desktop notifications. Each tool: risk-rated, policy-hooked,
tested allow/ask/deny like Phase 4.
SHIPPED 2026-09 (early): `jarvis/scheduler/` (SQLite schedules,
`briefing`/`tool` kinds, bounded `tick`, `schedule add|list|remove|tick|
health`), `network.fetch` (MEDIUM), `homeassistant.states` (LOW) +
`homeassistant.call` (HIGH), corrupt-DB quarantine (`storage/recovery.py`),
Telegram bridge (`jarvis/telegram/`, allowlisted long-poll). Remaining:
persistent goals, notifications, more tools.

## Phase F — It plays and it travels (operator-requested)

- **Hands**: `gui.screenshot|click|type` shipped (ctypes, Windows-only,
  HIGH/MEDIUM, no silent auto-play). Game loops (e.g. CoC via an Android
  emulator + see→decide→act over `gui.*` + vision) are designed per-game
  with the operator — see rule 6. The laptop is the hands; there is no
  cloud gaming path by design.
- **Reach**: Telegram bridge shipped — message the bot from the phone with
  plain internet; the laptop stays home and online. Remote *control of the
  phone itself* is out of scope (needs cloud relays or root/ADB tricks —
  both violate local-first).

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
| 2026-09-06 | Legacy models housed in `legacy/` (Jarvis-SSS scaffold + jarvis-main donor); `jarvis briefing` deterministic daily brief (health + episodes + open tasks/plans + delegation) | Committed (`145c39c`), pushed |
| 2026-09-08/09 | Scheduler + 6 new tools + Telegram + embeddings + real voice + quarantine | Built, verifying, uncommitted |
