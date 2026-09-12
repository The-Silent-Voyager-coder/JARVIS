# Great Sage — Evolution Roadmap

> **Wise One — state your query.** Formerly J.A.R.V.I.S. (kept as lore).
> Stage 1 of the evolution is **Great Sage**: logic without ego —
> bounded tools, validated config, honest degradation, permissioned
> everything. It computes; it does not want.
>
> Promotion to **Raphael** follows the gates in `docs/EVOLUTION.md`.
> Status: substrate complete, all checks green; roadmap phases below
> build on it, never rewrite it.

## Laws (carried over, renamed)

1. Substrate is frozen — extend, never re-architect.
2. Zero-cost + local-first hold (`docs/DEPENDENCY_POLICY.md` — written
   justification per dependency; stdlib preferred).
3. Every new tool goes through `ToolService.execute` (no bypass); every new
   loop carries bounds, timeouts, audit.
4. Stubs stay honest until replaced: mock → real swaps flip the health
   detail string and the docs in the same commit.
5. **GitHub is read-only by default.** Study freely; downloading anything
   needs the operator's explicit permission, every time.
6. **Game automation needs the operator's ToS judgment.** Botting violates
   most games' terms. The `gui.*` tools are hands, not a player;
   unattended game loops ship only with explicit per-game approval and
   stay ASK-gated. (CoC approval granted 2026-09-10.)

## Great Sage era — shipped

- **Voice given** (Phase A): Vosk STT + Piper TTS + fuzzy wake-word
  (`greatsage voice health|listen|speak`); mocks remain the default,
  real engines opt-in via `config/sage.yaml`.
- **Memory deepened** (Phase B): Ollama `nomic-embed-text` provider,
  `memory search --semantic`, `memory reindex`, `memory digest`.
- **Chores begun** (Phase C, early): `greatsage/scheduler/`
  (`schedule add|list|remove|tick|health`), `network.fetch`,
  `homeassistant.states|call`, corrupt-DB quarantine.
- **Reach** (Phase F, early): Telegram bridge
  (`telegram health|listen`, `/briefing` `/status` `/screenshot`).
- **Hands** (Phase F, early): `gui.screenshot|click|type` (ctypes,
  Windows-only, always ASK-gated, no silent auto-play).

## Next: the Raphael gates (`docs/EVOLUTION.md`)

1. **Eyes** — local VLM grounding: screenshot → coordinates, verified
   live (the CoC loop plays a full session on vision alone).
2. **Always-on voice** — mic loop with wake-word + barge-in.
3. **Wired brain** — a real LLM drives the bounded agent loop end-to-end.
4. **Recall gating** — memory decides for itself what to surface.
5. **30-day stability** — nightly green, zero silent fallbacks.

## Progress log

| Date | Increment | Status |
|---|---|---|
| 2026-09-05 | Roadmap written; `memory digest` | Committed, pushed (Jarvis era) |
| 2026-09-06 | Legacy models housed; `briefing` | Committed, pushed (Jarvis era) |
| 2026-09-08/09 | Scheduler, tools, Telegram, embeddings, real voice, quarantine | Committed, pushed (Jarvis era) |
| 2026-09-12/13 | **Rebrand P1–P4**: Great Sage surface, `greatsage/` package, GREATSAGE env/root/names, great-sage dist | This evolution |
