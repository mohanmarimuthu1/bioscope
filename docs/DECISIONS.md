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
**P3 result:** contrast preserved — EC > EO alpha in 9/10 subjects (S001–S010, S009 excluded), median EC−EO alpha_exc +31.6 µV², alpha_osc +2.17.

## ADR-007 — Per-epoch features reuse the session aperiodic fit (2026-11-27)
**Context:** The ML table needs per-epoch features. A 4 s epoch has only three 2 s Welch segments, so its spectrum is noisy.
**Options:** (a) FOOOF per epoch per channel; (b) FOOOF once per channel on the session spectrum, reused for every epoch.
**Measured (sample S060 R01, 27 epochs × 8 ch):** (a) 216 fits in 1.45 s, median r² 0.762, 8% of fits r² < 0.5; (b) whole `extract` 0.27 s, session r² 0.97.
**Decision:** (b) (owner). Per-epoch `{band}_osc/_exc` = epoch PSD vs the channel's session aperiodic fit; per-epoch PAF = centre of gravity 7–13 Hz; `ap_exponent/ap_offset` session-only.
**Consequence:** Speed was not the binding constraint (1.45 s); fit quality was. Per-epoch rows share the session 1/f model, so within-session aperiodic changes are not tracked per epoch.

## ADR-008 — Excess power above 1/f for TBR, alpha and high beta (2026-11-27)
**Context:** §7.5 defined `{band}_osc = mean(PSD/aperiodic)`. Synthetic probe (8 ch, 1/f slope 1 → 2, rhythms fixed; |Δlog| = movement, smaller = more robust):
| Feature | Rhythm µV | classic abs | ratio osc | **excess** |
|---|---|---|---|---|
| TBR (θ 6 Hz, β 20 Hz) | 1 / 2 / 4 / 6 | 0.58 / 0.34 / 0.21 / 0.16 | 0.68 / 0.88 / 0.99 / 1.04 | **0.03 / 0.03 / 0.02 / 0.01** |
| alpha (10 Hz) | 2 / 4 / 8 / 15 | 2.28 / 1.20 / 0.44 / 0.13 | 2.39 / 3.52 / 4.30 / 4.64 | **0.62 / 0.16 / 0.02 / 0.01** |
| high beta (25 Hz) | 2 / 4 / 8 / 15 | 2.16 / 1.07 / 0.39 / 0.13 | 3.46 / 4.59 / 5.32 / 5.61 | **0.64 / 0.16 / 0.04 / 0.01** |
The ratio is a rhythm-to-background ratio, so it tilts with the background — worse than classic in every row.
**Decision (owner):** `{band}_exc = ∫ max(PSD − aperiodic, 0)` (µV²). `tbr_osc = theta_exc/beta_exc`, NaN + warning if beta_exc < 5% of beta_abs.
By the owner's rule (switch if ratio moves ≥ abs), alpha and high beta also switch: the score uses `alpha_exc`, `hibeta_exc`. Ratio `_osc` kept for display/ML.
Reference/z use ln(tbr). Pitch anchor 1 reworded. Regression test: |Δlog tbr_osc| < 0.1 (measured 0.064–0.071 through `extract`).
**Consequence:** excess is µV² (subject-scale dependent), right-skewed, and can be exactly 0 (frontal8 EO alpha_exc = 0 in 3/10) → handling decided in P4.

## ADR-009 — PAF peak search 8–13 Hz (2026-11-27)
**Context:** §7.5 searched 7–14 Hz. S060 R01 frontal channels show theta peaks at 6.0–7.5 Hz, stronger than alpha (10.8–11.2 Hz), so 7.1 Hz was picked.
| Peak range | EO PAF mean ± sd | EO min | EO < 8 Hz | EC PAF mean ± sd |
|---|---|---|---|---|
| 7–14 Hz | 9.20 ± 1.53 | 7.05 | 2/10 | 9.85 ± 0.52 |
| **8–13 Hz** | **9.88 ± 1.08** | 8.27 | **0/10** | 9.87 ± 0.53 |
| 7.5–13.5 Hz | 9.88 ± 1.08 | 8.27 | 0/10 | 9.85 ± 0.52 |
(frontal8, S001–S010 + S060, 20 usable recordings.)
**Decision (owner):** 8–13 Hz peak search; centre-of-gravity fallback stays 7–13 Hz.
**Consequence:** PAF window = alpha band; a genuine slow alpha below 8 Hz would be reported via the fallback.

## ADR-010 — Reference per preset × condition; transforms; percentile z for skewed features (2026-11-27)
**Context:** P3 left `_exc` features in µV², right-skewed and sometimes exactly 0. The P4a audit (S001–S050, R01/R02, both presets) also found `tbr_osc = 0` (theta_exc = 0) in 6 recordings, so ln(tbr_osc) = −inf. frontal8 and muse4 differ in scale (EC alpha_exc mean 4.90 vs 32.14 µV²).
Skew (bias-corrected) before → after transform. Cells: frontal8 EO / EC · muse4 EO / EC. n = 44 / 49 / 47 / 48.
| Feature | Transform | frontal8 EO | frontal8 EC | muse4 EO | muse4 EC |
|---|---|---|---|---|---|
| tbr_osc | ln(1+x) | 2.90 → **1.57** | 1.67 → 0.95 | 3.14 → **2.02** | 2.56 → **1.73** |
| tbr_classic | ln | 1.31 → −0.19 | 0.65 → −0.66 | 1.38 → −0.40 | 1.37 → 0.12 |
| paf | none | **1.19** | 0.10 | −0.02 | 0.29 |
| alpha_exc | ln(1+x) | 1.39 → 0.44 | 1.60 → 0.14 | 2.00 → 0.01 | 1.80 → −0.42 |
| faa | none | −0.10 | −0.30 | −0.42 | −0.15 |
| hibeta_exc | ln(1+x) | 2.33 → 0.76 | 6.30 → **1.43** | 2.86 → 0.71 | 4.65 → 0.96 |
| ap_exponent | none | −0.54 | −0.62 | −0.63 | −0.50 |
(ln on tbr_osc would give −0.53 / −0.49 / −0.20 / −1.36 but only after dropping the zeros.)
**Decision (owner):**
1. Reference is separate per preset × condition (4 cells); presets never mix. Contract change: `load_reference(condition, preset)` (R11; no callers yet).
2. Transforms: ln(1+x) for tbr_osc, alpha_exc, hibeta_exc (0 → 0); ln for tbr_classic (never 0 in the reference).
3. |skew| > 1 after the transform → **percentile** method, else **zscore**. Bold cells above (5 of 28) are percentile.
4. *(rev 1 — superseded by rev 2 below)* Percentile z: inside [min, max] of the reference, z = Φ⁻¹(rank/(n+1)) with 1-based mid-rank; outside, the parametric z on transformed values when its magnitude is larger; |z| ≤ 4.
**Worked example, rev 1** (frontal8 EC hibeta_exc, ln(1+x): n 49, mean 1.179, sd 0.902, range 0.141–4.651):
| raw µV² | t | rank | z_pct | z_param | z |
|---|---|---|---|---|---|
| 1.64 (median) | 0.970 | 25 | 0.00 | −0.23 | **0.00** |
| 103.7 (= max) | 4.651 | 49 | 2.05 | 3.85 | **2.05** (inside) |
| 311 | 5.744 | 49.5 | 2.33 | 5.06 | **4.00** (outside, param, capped) |
| 0.00 | 0.000 | 0.5 | −2.33 | −1.31 | **−2.33** (outside, pct larger) |
**Consequence:** no −inf; per-cell method stored in reference.json (`transform`, `method`, `mean`, `std`, `n`, `skew`, `min`, `max`, `values` for percentile). KNOWN: the rule jumps at the range edge (max → 2.05, just above max → 3.85 in the example); flagged to owner for P4b. With n ≈ 44–49 the skew estimate has SE ≈ 0.35, so the threshold-1 split is a rule, not a test.
**Revision 2 (2026-11-27 21:25, owner) — continuous extension outside the range.** Rev 1 jumped at the edge (max → 2.05, max + ε → 3.85).
Now: below min z = z_pct(min) + (t − t_min)/std; above max z = z_pct(max) + (t − t_max)/std; |z| ≤ 4. Inside the range unchanged.
z is continuous at both edges and monotone everywhere (tested). Inside the range it is still a step function of rank (e.g. top step
z_pct(max) − z_pct(next) ≈ 0.17 at n = 49) — inherent to ranks.
| raw µV² | t | rev 1 z | **rev 2 z** |
|---|---|---|---|
| 1.64 (median) | 0.970 | 0.00 | **0.00** |
| 103.7 (= max) | 4.651 | 2.05 | **2.05** |
| 103.7 + ε | 4.651⁺ | 3.85 | **2.05** |
| 311 | 5.743 | 4.00 (capped) | **3.26** |
| 0.00 | 0.000 | −2.33 | **−2.21** |
**Inclusion and coverage (2026-11-27 21:30, owner).** A recording enters the reference only with n_kept ≥ MIN_EPOCHS (6). Used of 50
(EO/EC): frontal8 40/42, muse4 44/47. The frontal8 eyes-open skip rate (12% at rev 1, 20% with the ≥ 6 rule) is **accepted** and stated in
methodology.md limitations. The rule moved two method choices: frontal8 EC hibeta_exc → zscore (skew 0.76), muse4 EC hibeta_exc →
percentile (skew 1.02, borderline). Percentile cells: frontal8 EO tbr_osc, paf; muse4 EO tbr_osc; muse4 EC tbr_osc, hibeta_exc.

## ADR-011 — score() takes the preset; duration from qc; missing dimensions (2026-11-27)
**Context:** §6 `score(features, qc, condition)` cannot pick the reference cell (ADR-010 keys it by preset; features carry no preset), and
confidence needs duration_s, which only `load_eeg` meta has. The spec is silent on a dimension whose features are all NaN.
**Decision (owner-approved plan):**
1. Contract: `score(features, qc, condition, preset)`. No callers existed.
2. duration_s is read from `qc["duration_s"]`; callers copy it from meta. Missing → 0 duration credit + warning. preprocess.py unchanged.
3. A dimension with no available feature is None; the composite renormalises the weights over scored dimensions + warning.
   If no EEG dimension can be scored, composite = None (signal quality alone is not a brain score; review found it gave 100).
**Consequence:** P5/P7 callers must pass the preset and put duration_s into qc. Composite stays comparable only when all 4 dimensions are
present; the UI must show the renormalisation warning.

## ADR-012 — Segment-aware epoching; db_path kwarg; baseline flag rule (2026-11-27)
**Context:** Demo sessions 2–13 join 15 T0 rest blocks (4.1 s each) with `mne.concatenate_raws`, which marks joins with BAD/EDGE boundary
annotations (filters then run per segment; epochs overlapping a BAD annotation are rejected). But `make_fixed_length_epochs` lays one 2 s grid
from t = 0, so on S060 R03 every epoch after the first straddled a join: **n_total = 1** for a 61.5 s session.
**Decision (owner-approved plan):**
1. `preprocess._segment_events`: split at boundary onsets, restart the 4 s / 2 s-step grid at each segment's first sample, then
   `mne.Epochs(..., reject_by_annotation=True)`. Without boundaries the events equal MNE's (tested); full reference rebuild →
   reference_features.csv byte-identical, reference.json identical except build_date. qc gains additive `n_segments`.
2. db functions take an optional `db_path` (default config.DB_PATH) so tests use a temp file. Additive.
3. flag_shifts never flags the baseline sessions themselves; baseline std uses ddof=1 with the 2.0 floor; < 3 sessions → provisional baseline.
**Consequence:** a 4.1 s block yields exactly one 4 s epoch (the 0.1 s remainder is unused); epochs never cross a join.
**Addendum (2026-11-27 22:00, owner) — longitudinal demo subject S051.** S060's T0 blocks inside the motor runs kept 0–5 of 15 epochs
at 200 µV (5 of 12 sessions unscorable). Screened S051–S059 (outside the reference and holdout sets) through the exact demo pipeline:
| Subject | R01 kept | T0 kept per run R03–R14 | Runs ≥ 6 kept | Median T0 confidence |
|---|---|---|---|---|
| **S051** | 29 | 15 15 15 15 15 15 15 15 15 15 14 15 | **12/12** | **0.98** |
| S055 | 29 | 15 ×12 | 12/12 | 0.96 |
| S059 | 0 | 11 13 10 14 11 14 5 12 12 13 1 13 | 10/12 | 0.85 |
| S057 | 29 | 15 15 15 10 3 1 12 2 7 2 13 7 | 8/12 | 0.53 |
| S054 | 29 | 3 8 15 3 6 2 1 15 0 1 10 14 | 6/12 | 0.53 |
| S052 | 0 | 0 1 1 1 5 2 11 4 10 10 7 2 | 4/12 | 0.54 |
| S056 | 17 | 4 0 2 0 1 2 9 5 0 0 0 1 | 1/12 | 0.23 |
| S058 | 0 | 1 0 0 0 1 10 0 0 0 0 0 0 | 1/12 | 0.00 |
| S053 | 0 | 0 ×12 | 0/12 | 0.00 |
| *S060 (was)* | 27 | 3 2 0 0 0 5 1 0 1 1 0 2 | 0/12 | — |
Pick rule (owner): most runs with ≥ 6 kept; tie → higher median confidence; accept if ≥ 10/12. S051 and S055 tie at 12/12 → **S051** (0.98 > 0.96).
`config.DEMO_LONGITUDINAL_SUBJECT = "S051"`; config refuses to load if either demo subject is in the reference or holdout lists, and
`reference.assert_no_leak` (also used for ML training subjects) rejects it. S060 stays the held-out sample/test subject (sample file, tests, P3/P4 numbers unchanged).

## ADR-013 — ML validation gate replaced after it failed (2026-11-28)
**Context:** §7.8 set the gate "LightGBM subject-held-out CV accuracy ≥ 80%" **before any evidence**. On frontal8 it failed:
**accuracy 0.661 ± 0.033, ROC-AUC 0.719** (LR baseline 0.671 ± 0.052, AUC 0.740). No pipeline bug found: per-epoch feature medians track the
session features (Spearman r 0.92–0.995). Cause: frontal-only channels plus large differences between subjects — the eyes-closed alpha
increase is mainly posterior, and frontal alpha_abs rose in only 25/44 subjects. Exploratory scratch runs (not in the repo): posterior channels
P3 Pz P4 PO3 PO4 O1 Oz O2 → LGBM 0.704 / LR 0.760; frontal8 session-level LGBM 0.688; relative band power no gain (0.659–0.666).
**This gate was replaced after seeing the result.** That is stated here and in metrics.json (`original_gate`), not hidden.
**Options:** (1) re-declare the gate as a significance test on the frontal8 model; (2) posterior validation-only preset (scope change,
still < 80%, validates a montage the score does not use); (3) more debugging (evidence points to data, not code).
**Decision (owner):** option 1, with metrics fixed before the rerun: per-epoch accuracy + AUC, per-recording accuracy (mean p > 0.5), paired
within-subject accuracy (out-of-fold mean p(EC) on R02 > R01), a 1000-shuffle within-subject label permutation test on mean fold AUC (full CV
re-run per shuffle), SHAP top-10. New gate (LightGBM): **permutation p < 0.01 AND AUC > 0.65 AND paired accuracy ≥ 0.75**. No posterior preset.
**Result:** PASS — p 0.001 (0/1000 null AUC ≥ 0.719; null 0.501 ± 0.017, max 0.561), AUC 0.719, paired 0.886 (39/44).
Alpha features do **not** lead SHAP (alpha_osc rank 3, after hibeta_abs and samp_entropy).
**Consequence:** UI/pitch wording: "Validation: features separate eyes-open from eyes-closed well above chance (AUC 0.72, paired 89% of subjects,
p < 0.01); frontal-only EEG limits per-epoch accuracy." Never quote 80% or "validated accuracy". P6b reports the same metrics on S061–S109.

## ADR-014 — Sessions store spectrum and validation extras; shared pipeline module (2026-11-28)
**Context:** the Session page must show the PSD with its 1/f fit and the SHAP bar for any saved session (including the 13 demo sessions),
but the DB kept only features/qc/score. The pipeline steps also lived only in scripts, so the UI, seeding and tests would each repeat them.
**Decision (owner-approved P7 plan):**
1. `db`: additive `extras_json` column (`{spectrum: freqs, per-channel PSD + aperiodic fit, 4 significant figures; ml: p_eyes_closed,
   mean SHAP per feature, base_value, n_epochs; timings_s}`); record key `extras` optional; an older DB gains the column on first connect
   and its rows load with `{}`. ~11 KB per session.
2. `src/pipeline.py` (no streamlit): `run` / `save` / `seed_demo` used by Upload, first-run seeding and tests; user-fixable problems raise
   `PipelineError` with a plain message; 0 clean epochs is not an error (composite None).
3. Additive helpers: `reference.reference_n`, `config.DEMO_LABEL` (single source; the demo script imports it), `config.MIN_DURATION_S`.
**Consequence:** the UI shows exactly what scripts compute (seeding reproduces the 13 P5 composites, tested). `scripts/build_demo_sessions.py`
still writes rows without extras; the UI re-seeds S051 through the pipeline when it finds such rows.
