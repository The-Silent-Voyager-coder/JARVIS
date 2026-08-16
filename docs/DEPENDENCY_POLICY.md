# Dependency Policy

## 1. The Rule

**No dependency enters `project.dependencies` without written justification.**

Phase 0 shipped with **zero runtime dependencies**; Phase 1 added exactly one
(`PyYAML`, see §5). Later phases must continue to prefer Python's standard
library. Dependencies are added only when:

1. The capability is genuinely required for the current phase (no speculative
   additions for future phases), **and**
2. A stdlib-only implementation would be unreasonable (substantial code size,
   security risk, or maintenance burden), **and**
3. The package is actively maintained, OSI-licensed, and works on Windows
   Python 3.11+ without paid tiers.

Every addition is recorded in this document (table below) with its
justification, alternatives rejected, and review date.

## 2. Zero-Cost Constraint

Free tier limits are acceptable; hard dependency on any paid API, subscription,
or rate-limited SaaS is forbidden. A dependency must remain fully functional
offline/local. Candidate evaluation checklist:

- [ ] works offline
- [ ] no mandatory cloud account
- [ ] permissive/OSI license compatible with local use
- [ ] Windows support
- [ ] no telemetry that requires consent-blind collection; nothing sends data
  without explicit user opt-in through JARVIS config

## 3. Locking & Vendoring

- `requirements-*.txt` or uv/pip lockfiles committed for reproduccible installs.
- Secrets never appear in lockfiles (no env-var interpolation).
- If a dependency is at risk of disappearing (small project, archive state),
  vendor it under `vendor/` with license attribution.

## 4. STT/TTS/Model Runtime Boundaries

Voice model binaries (faster-whisper, Piper, ONNX wake-word models) are
**runtime assets**, not Python dependencies. They live under `C:\JARVIS\models\`
(config-overridable) and are downloaded on demand by an explicit user action —
never silently, and never from non-official sources. Each engine remains
swappable behind the voice pipeline interfaces (`docs/ARCHITECTURE.md` §4).

## 5. Approved Dependencies

| Package | Version | Phase | Justification | Alternatives rejected | Added |
|---|---|---|---|---|---|
| `PyYAML` | `>=6.0` | 1 | The configuration format is YAML (`config/jarvis.yaml`); parsing it safely requires a maintained, tested YAML library — stdlib has none | Hand-rolled parser (security risk, maintenance burden); JSON/TOML format change (violates the Phase 0 YAML contract); `ruamel.yaml` (unnecessary round-trip API) | Phase 1 (2026) |

## 6. Dev-Only Dependencies

`pyproject.toml [project.optional-dependencies] dev` holds `pytest`,
`pytest-cov`, `mypy` + `types-PyYAML`, and `ruff`. Dev tooling never ships
with the runtime package (wheel contains only the `jarvis` package).

## 7. Review Cadence

Every `pyproject.toml` change that adds a dependency requires an update to
§5 table and a note in the commit message. Dependency upgrades for security
fixes are always allowed; gratuitous minor bumps are avoided.