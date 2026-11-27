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

## ADR-004 — Local git hooks enforce authorship hygiene (2026-11-27)
**Context:** R2/R3 forbid AI trailers and tooling files in history. BUG-001 showed a manual printed check can be ignored.
**Options:** (a) manual checklist; (b) committed hooks framework (pre-commit package — new dependency); (c) local `.git/hooks` shell scripts, never committed.
**Decision:** (c). `pre-commit` blocks: trailer text in staged *added* lines; staged CLAUDE.md / plan.md / .claude/ / .claude-flow/ / data/raw/ / *.db / .venv/ (case-insensitive); user.name ≠ "Mohankumar M". `commit-msg` blocks trailer/attribution text in the message.
**Consequence:** Enforcement without new dependencies or tooling in the repo. Hooks are per-clone, so a fresh clone is unguarded — acceptable for a single-owner repo; never use `--no-verify`. Data-commit bodies use "Command:" wording. Verified with 6 pass/fail cases.

## ADR-005 — frontal8 ICA uses EOG correlation; rejection at 200 µV (2026-11-27)
**Context:** §7.4 excluded components via `find_bads_eog` z ≥ 3. With n = 7 components the largest attainable z-score is √(n−1) = √6 ≈ 2.45, so z ≥ 3 **can never fire**.
Audit (S001–S010 × R01/R02, frontal8): 0 components excluded in 20/20 files; median retention 12% (EO 9%, EC 74%); blink components clearly present (max |r| with Fp1/Fp2: EO 0.91–0.99, EC 0.62–0.86).
**Options** (all `measure="correlation"`, cap 2; frontal8 audit):
| Option | Rule | Reject | Median | EO | EC | Components excluded (files) |
|---|---|---|---|---|---|---|
| baseline | z ≥ 3 | 150 µV | 12% | 9% | 74% | 0 → 20 |
| 1 | \|r\| ≥ 0.5 | 150 µV | 93% | 57% | 93% | 1 → 7, 2 → 13 |
| **2 (chosen)** | **\|r\| ≥ 0.7** | **200 µV** | **97%** | **79%** | **100%** | 0 → 2, 1 → 15, 2 → 3 |
| 3 | \|r\| ≥ 0.5 | 200 µV | 100% | 88% | 100% | 1 → 7, 2 → 13 |
(Option 2 what-if showed 1 → 16, 2 → 2; the committed code gives 1 → 15, 2 → 3 — same retention.)
**Decision:** Option 2 (owner). |r| ≥ 0.7 removes mostly one clear blink component (least risk of removing brain signal); 200 µV keeps eyes-open data usable.
**Consequence:** Gate becomes per-condition (EO median ≥ 70% AND EC median ≥ 70%). Epoch p2p after ICA p50/p90/p99 = 133.8/364.6/543.3 µV. S009 retains 0% in both runs (outlier subject, noted for the reference build).

## ADR-006 — muse4 gets 3-component ICA with AF7/AF8 proxies (2026-11-27)
**Context:** §7.4 skipped ICA on 4-ch; blinks in AF7/AF8 left muse4 median retention at 57% (EO 31%) even at 200 µV.
**Options:** (1) 3-component ICA, AF7/AF8 proxies, |r| ≥ 0.7, cap 1, 200 µV — keep if EO median ≥ 50%; (2) no ICA + "experimental" warning, gate = runs/warns/never crashes. Timebox 20 min; no other methods.
**Result (option 1, S001–S010 × R01/R02):** median 57% → **100%** (EO 31% → 100%, EC 93% → 100%); 1 component removed in 20/20 files; 0.11 s/file; S009 still 0%.
**Decision:** keep option 1; muse4 gate = EO median ≥ 50% → PASS.
**Consequence / risk:** with 3 components and AF7/AF8 being half the montage, the removed component may also carry real frontal activity (removed in every EC file too, |r| 0.74–0.99).
Check in P3: muse4 must still show EC alpha_osc > EO; if the contrast collapses, revisit with the owner.
