# Decisions (ADR-lite)

Format: Context · Options · Decision · Consequence.

## ADR-001 — Stack (2026-11-27)
**Context:** Solo, CPU-only Windows laptop, 2.5-day build. Must be explainable end to end.
**Options:** (a) Python + MNE + FOOOF + Streamlit + SQLite; (b) web stack (FastAPI/React); (c) deep-learning EEG models.
**Decision:** (a). Python 3.11.15 (installed with `uv` onto E:, no system install), pinned in `requirements.txt`:
mne 1.13.2 · fooof 1.1.0 · antropy 0.2.3 · numpy 2.4.6 · scipy 1.17.1 · pandas 3.1.1 · lightgbm 4.7.0 ·
scikit-learn 1.9.1 · shap 0.51.0 · joblib 1.6.0 · streamlit 1.67.0 · plotly 7.2.0 · pytest 9.2.0.
**Consequence:** Single-process app, no server. `fooof` 1.1.0 prints a deprecation notice (successor: `specparam`).
It is functional — verified on a synthetic 1/f + 10 Hz spectrum: peak at 10.15 Hz, r² = 1.000 on numpy 2.4.6.
We keep `fooof` because CLAUDE.md pins it; migrating is out of scope.

## ADR-002 — Data split (2026-11-27)
**Context:** The score compares a recording to a reference distribution; the demo must not be scored against itself; ML CV must not leak subjects.
**Options:** (a) random epoch split; (b) fixed subject split.
**Decision:** (b).
| Set | Subjects | Runs | Use |
|---|---|---|---|
| Reference | S001–S050 | R01 eyes-open, R02 eyes-closed | reference.json, ML training/CV |
| Demo (held out) | S060 | R01–R14 | 13 demo sessions |
| Fallback | next clean subject ≥ S051 | R01–R14 | only if S060 unusable (new ADR) |
**Consequence:** Reference and ML scripts assert S060 is absent. ML uses GroupKFold by subject.

## ADR-003 — Welch segment length stays 2 s (2026-11-27)
**Context:** CLAUDE.md §7.4 said 4 s epochs give "0.25 Hz resolution", but §7.5 sets Welch `n_per_seg` = 2 s, which gives 0.5 Hz bins.
**Options:** (a) n_per_seg = 4 s (0.25 Hz bins, one segment per epoch); (b) n_per_seg = 2 s (0.5 Hz bins, 3 overlapping segments per epoch).
**Decision:** (b), owner delegated the choice.
**Why:** Averaging 3 segments per epoch reduces PSD variance, which matters most for per-epoch ML features. FOOOF fits peaks as continuous Gaussians,
so PAF precision is not limited to the bin grid (10 Hz synthetic peak recovered at 10.15 Hz on a 0.5 Hz grid).
**Consequence:** CLAUDE.md §7.4 note corrected. Band edges fall on 0.5 Hz bins.
