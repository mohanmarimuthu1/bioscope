# Dev log

Format:
```
### <YYYY-MM-DD HH:MM> — <title>  (commit <hash>)
Type: feature | bugfix (BUG-###) | tuning | refactor | retro
Change:  Why:  Effect on calculations:
Before → After: <numbers>
Files: <paths>
```

### 2026-11-27 19:45 — Environment and repo setup  (commit 0aa60dc)
Type: feature
Change: Python 3.11.15 installed via `uv` onto E: (no C: usage); `.venv`; pinned direct dependencies; `.gitignore`.
Why: Reproducible environment matching CLAUDE.md §5.
Effect on calculations: none. FOOOF smoke test on synthetic 1/f + 10 Hz: peak 10.15 Hz, r² 1.000.
Files: requirements.txt, .gitignore

### 2026-11-27 19:58 — Central config  (commit 9a09d01)
Type: feature
Change: All §7 constants in `src/config.py`.  Why: single source for every number.
Effect on calculations: defines them. Welch kept at 2 s → 0.5 Hz bins (ADR-003).
Files: src/__init__.py, src/config.py

### 2026-11-27 20:20 — PhysioNet downloader  (commit 4e2c2be)
Type: feature
Change: `scripts/download_data.py`, idempotent with retries.  Why: reproducible data.
Effect on calculations: none. Data in place: 100 reference + 14 demo EDF = 114 files, 153.3 MB. Rerun skipped all 114.
Files: scripts/download_data.py

### 2026-11-27 20:30 — BUG-001: pre-commit trailer guard did not block  (commit: this docs fix)
Type: bugfix (BUG-001) — process, not calculation
Symptom: guard printed STOP on the docs commit, but the chained command still committed and pushed.
Root cause: (1) the guard only printed STOP instead of aborting; (2) REVIEWS.md text quoting the guard's own search word made it match (false positive — no commit message contains a trailer; verified with `git log --format=%B | grep`).
Fix: REVIEWS wording changed to "AI-trailer grep"; guard now `throw`s before `git commit` so a match stops the commit, and scans only added (`+`) diff lines so deleting bad text is not itself blocked.
Test: guard blocked the first attempt of this fix (matched the removed line) → proved it now aborts; with added-lines filter → clean.
Before → After: guard matches on HEAD content 1 → 0.
Files: docs/REVIEWS.md, docs/DEVLOG.md

### 2026-11-27 20:25 — P0 retro
Type: retro
Went well: env built entirely on E: (Python 3.11 via uv, no C: growth); FOOOF verified on numpy 2.4 before any feature code.
Broke + fix: a placeholder commit hash slipped into this log; caught in self-review and replaced with the real hash (0aa60dc).
Next: start ~4.5 h late → P2/P3 move to Sat morning; keep doc entries short during build, expand in P8.

### 2026-11-27 20:15 — Local git hooks installed (not committed)
Type: feature (process)
Change: `.git/hooks/pre-commit` blocks AI-trailer text in staged added lines, forbidden paths (CLAUDE.md, plan.md, .claude/, .claude-flow/, data/raw/, *.db, .venv/, case-insensitive) and user.name ≠ "Mohankumar M"; `.git/hooks/commit-msg` blocks AI trailers in the message. CLAUDE.md §11 updated to the blocking, added-lines-only check.
Test: 6 cases — forbidden path → blocked; trailer in added line → blocked; clean file → pass; trailer in message → blocked; clean message → pass; wrong user.name → blocked.
Effect on calculations: none.

### 2026-11-27 20:40 — io_utils: loader + label normalisation  (commits 6a2f243, d7bba16, 9e3fb7c)
Type: feature
Change: `load_eeg` (EDF/FIF, preset pick in order, annotations kept, meta incl. n_samples); `normalise_label`; 61 s sample FIF; 20 tests.
Why: one consistent channel set for every downstream step.
Effect on calculations: defines input shape. **Correction:** the plan assumed R01 = 9,600 samples (60 s); the real file has **9,760 samples = 61.0 s**.
Gate rewritten to compare against the source file's own `n_times` (no hard-coded count). Confidence will use the actual duration_s (61 s → duration term 1.0).
Before → After: expected R01 length 9,600 (assumed) → 9,760 (measured).
Process note: the commit-msg hook blocked a data-commit body that began with the forbidden phrase; data-commit bodies now start "Command:".
Files: src/io_utils.py, tests/test_io.py, pytest.ini, data/sample/sample_frontal8_raw.fif

### 2026-11-27 21:00 — CLAUDE.md edits log (file is untracked; changes recorded here)
Type: refactor (rules)
1. §7.4 step 4: "(0.25 Hz resolution)" → "PSD bins are 0.5 Hz (Welch n_per_seg = 2 s) … (ADR-003)". Why: the old note was wrong for 2 s segments.
2. §11 pre-commit block: printing guard → blocking, added-lines-only guard + hooks note (BUG-001, ADR-004).
3. §11 rules: data-commit bodies start with `Command:` (the hook blocks the AI-attribution phrase).
Effect on calculations: none. Rule from now on: every CLAUDE.md edit is shown to the owner as a diff and logged here.

### 2026-11-27 20:05 — preprocess stage 1: filter, epoch, reject  (commit c83c8bf)
Type: feature
Change: average ref → FIR 1–45 Hz → conditional notch → 4 s / 2 s-overlap epochs → p2p rejection; qc dict (+ notch_applied, ica_eog_scores, epoch_ptp_uv).
Finding: S060R01 kept 0/29 epochs at 150 µV. Diagnosis: units correct (EDF µV, 1:1 digital/physical); Fp1/Fp2 4 s p2p 328/301 µV vs 75–115 µV elsewhere → blinks (EO).
Files: src/preprocess.py

### 2026-11-27 20:20 — ICA as specified  (commit 896654c)
Type: feature
Change: fastica, n−1 comps, find_bads_eog z ≥ 3, cap 2.  Result: 0 components excluded in 20/20 audit files → root cause for ADR-005.
Files: src/preprocess.py, src/config.py

### 2026-11-27 20:25 — tune: EOG correlation ICA + 200 µV  (commit df12993)
Type: tuning
Change: `measure="correlation"`, |r| ≥ 0.7, cap 2; REJECT_PTP_V 150 → 200 µV.  Why: z ≥ 3 unreachable with 7 comps (max √6 ≈ 2.45). ADR-005.
Before → After (frontal8, S001–S010 × R01/R02): median retention 12% → 97%; EO 9% → 79%; EC 74% → 100%;
components excluded per file 0×20 → 0×2, 1×15, 2×3; epoch p2p p50/p90/p99 174.9/463.9/675.7 → 133.8/364.6/543.3 µV; mean 0.73 s/file. S009 R01/R02 still 0%.
Files: src/config.py, src/preprocess.py

### 2026-11-27 20:30 — muse4 3-component ICA trial (kept)  (commit 5c30406)
Type: tuning
Change: per-preset ICA settings; muse4 3 comps, AF7/AF8 proxies, |r| ≥ 0.7, cap 1 (ADR-006). Timeboxed 20 min, done in ~5.
Before → After (muse4, no ICA @200 µV → ICA): median 57% → 100%; EO 31% → 100%; EC 93% → 100%; 1 comp removed in 20/20 files; p2p p50/p90/p99 194.0/430.8/706.1 → 124.5/298.6/414.6 µV; 0.11 s/file.
Risk: component removed in every EC file too → verify EC > EO alpha_osc survives for muse4 in P3.
Files: src/config.py, src/preprocess.py

### 2026-11-27 20:35 — CLAUDE.md §7.4 amended (shown to owner as diff)
Step 3: ICA via EOG correlation |r| ≥ 0.7; 8-ch Fp1/Fp2 cap 2 (ADR-005); 4-ch 3-component ICA, AF7/AF8, cap 1 (ADR-006). Step 5: 150 → 200 µV.

### 2026-11-27 20:45 — P1 retro
Type: retro
Went well: one label rule covers all 64 EEGMMI names; clean-clone run proved tests stay green without raw data (17 passed, 3 skipped).
Broke + fix: assumed 9,600-sample length was wrong (9,760) → gate now data-driven; hook blocked a commit body wording → reworded.
Next: P2 preprocess — watch ICA on Windows and the 150 µV retention on unfiltered ~100 µV signals.

### 2026-11-27 21:00 — Holdout download  (commit 211ca89)
Type: feature
Change: `download_data.py --holdout` → S061–S109 R01/R02. Result: 98/98, rerun 98 skipped, total raw 272.5 MB (E:).
TODO(verify) resolved: I expected S088/S092/S100 at 128 Hz — **wrong**: all 98 files are 160 Hz (95 × 61.0 s, 3 × 60.0 s).
Files: scripts/download_data.py

### 2026-11-27 21:10 — features as specified  (commit 131393e)
Type: feature
Change: §7.5 features + per-epoch table (ADR-007). Timing: preprocess + extract 0.2–1.7 s per 61 s file (gate < 10 s ✓).
Findings: frontal8 EO PAF 7.13 Hz (theta caught); tbr_osc ratio less robust than classic; pure-1/f test found spurious FOOOF peaks (60 s noise ≈ 0.05 log units vs min_peak_height 0.1).
Files: src/features.py, src/config.py

### 2026-11-27 21:30 — tune: PAF search 8–13 Hz  (commit d3606d8)
Type: tuning — ADR-009
Before → After (frontal8, 20 recordings): EO PAF mean 9.20 → 9.88 Hz, sd 1.53 → 1.08, EO < 8 Hz 2/10 → 0/10; EC 9.85 → 9.87 Hz.

### 2026-11-27 21:40 — tune: excess power for TBR, alpha, high beta  (commit fbfb3f1)
Type: tuning — ADR-008
Before → After (synthetic slope change, |Δlog|): TBR 0.68–1.04 (ratio) → 0.01–0.03 (excess); through `extract` 0.064–0.071.
S060 frontal8 tbr_osc EO/EC 1.012/1.142 → 0.68/1.04. Score features alpha_osc → alpha_exc, hibeta_osc → hibeta_exc.
Real data after both tunes (S001–S010 + S060, S009 insufficient):
| preset | EO PAF | EC PAF | EO fallback | **EC fallback** | EC > EO alpha (exc / osc) | tbr NaN | s/file |
|---|---|---|---|---|---|---|---|
| frontal8 | 9.88 ± 1.08 | 9.87 ± 0.53 | 0.74 | **0.23** | 9/10 / 9/10 | 0 | 0.45 |
| muse4 | 10.51 ± 1.11 | 10.25 ± 0.58 | 0.55 | **0.17** | 9/10 / 9/10 | 0 | 0.20 |
EO fallback ≫ EC fallback = alpha appears when eyes close → physiological, accepted (Q3). frontal8 EO alpha_exc exactly 0 in 3/10 → P4 question.
Files: src/features.py, src/config.py, tests/test_features.py (7a7d53d)

### 2026-11-27 21:50 — CLAUDE.md §7.5/§7.6/§15 amended (diff shown to owner)
§7.5: PAF 8–13 Hz + session-PAF rule; `_exc` row; `_osc` display-only; tbr_osc = theta_exc/beta_exc + guard; FOOOF-failure nanmedian; per-epoch rule (ADR-007).
§7.6: sanity uses alpha_exc; skip insufficient_data; ln(tbr); Attention from paf when tbr_osc NaN; dimensions alpha_exc/hibeta_exc; named_metrics + paf_fallback_frac, hibeta_exc.
§15: pitch anchor 1 reworded.

### 2026-11-27 21:55 — P3 retro
Type: retro
Went well: probes on synthetic data with known ground truth caught two spec errors (theta-as-PAF, slope-sensitive ratio TBR) before they reached the score.
Broke + fix: ratio "osc" was less robust than classic → excess power (ADR-008); 7–14 Hz PAF caught theta → 8–13 Hz (ADR-009); my 128 Hz recollection was wrong (verified 160 Hz).
Next: P4 — decide zero/skew handling for alpha_exc & hibeta_exc before building the reference; skip S009.

### 2026-11-27 20:40 — P2 retro
Type: retro
Went well: audit-first caught a spec bug (z ≥ 3 unreachable with 7 comps) with numbers before any feature code; every option was evaluated on the same 20 files.
Broke + fix: 0–12% retention → ADR-005 (correlation ICA, 200 µV) → 97%; muse4 14–57% → ADR-006 (3-comp ICA) → 100%. Audit table column mislabelled "|z|" (values are |r|) — corrected in docs.
Next: P3 must verify muse4 ICA did not remove alpha (EC > EO alpha_osc); S009 is an outlier to watch in the reference.

### 2026-11-27 21:10 — P4a reference built (commits ed0a2e4, a6ceb2a, 7d588c9)
Type: feature
Change: scripts/build_reference.py + src/reference.py → models/reference.json (4 cells) + reference_features.csv (200 rows). ADR-010 transforms and percentile method.
Why: score = typicality vs a condition- and preset-matched reference (§7.6).
Effect on calculations: first reference. 5 of 28 feature cells use percentile z (tbr_osc ×3, frontal8 EO paf, frontal8 EC hibeta_exc).
Numbers: EO PAF mean 9.65 Hz (frontal8) / 10.42 Hz (muse4) — PASS 9–11. alpha_exc mean EO → EC: 1.71 → 4.90 µV² (frontal8), 7.92 → 32.14 (muse4) — PASS. Used EO/EC: frontal8 44/49, muse4 47/48. Skipped (0 epochs kept): S009 (all cells), S013, S048 (EO, + muse4 EC), S022, S024, S028 (frontal8 EO). Build 29–50 s on 8 workers; rebuild byte-identical except build_date.
Files: src/config.py, src/reference.py, scripts/build_reference.py, tests/test_reference.py, models/

### 2026-11-27 21:15 — P4a retro
Went well: features were fast enough (200 extractions in ~30 s) to audit skew on the full reference before designing, and every number above comes from that run.
Broke: ln(tbr_osc) = −inf on 6 recordings (theta_exc = 0); leak guard used bare `assert` (stripped by `python -O`) — both caught before commit.
Next: P4b scoring must decide the percentile range-edge jump (ADR-010 KNOWN) and the frontal8 EO 12% skip rate.

### 2026-11-27 21:25 — Percentile z: continuous extension outside the reference range
Type: tuning
Change: `reference.to_z` percentile cells outside [min, max] use z_pct(edge) + (t − edge)/std (was: larger of parametric / percentile z).
Why: rev 1 jumped 2.05 → 3.85 just above the max (≈ 27 feature-score points for an infinitesimal change). ADR-010 rev 2.
Effect on calculations: only values outside a percentile cell's reference range; reference.json unchanged.
Before → After (frontal8 EC hibeta_exc): max + ε 3.85 → 2.05; 311 µV² 4.00 → 3.26; 0 µV² −2.33 → −2.21; median 0.00 → 0.00.
Files: src/reference.py, tests/test_reference.py (+ continuity/monotonicity test, 12 passed)

### 2026-11-27 21:30 — Reference inclusion requires n_kept ≥ 6
Type: tuning
Change: build_reference keeps a recording only if features exist and n_kept ≥ MIN_EPOCHS (6, the low-data warning threshold).
Why: a reference value from 1–5 epochs (4–12 s) is noisy; it should not define "typical".
Effect on calculations: 15 more recordings dropped; 2 cells switch method; sanity still PASS.
Before → After (n used of 50, EO/EC): frontal8 44/49 → 40/42; muse4 47/48 → 44/47.
Newly dropped: frontal8 EO S018 S023 S043 S044; frontal8 EC S015 S017 S027 S028 S043 S048 S049; muse4 EO S017 S022 S044; muse4 EC S043.
Methods: frontal8 EC hibeta_exc skew 1.43 → 0.76, percentile → zscore (the tail came from low-epoch recordings);
muse4 EC hibeta_exc 0.96 → 1.02, zscore → percentile (borderline). Percentile cells still 5 of 28.
Sanity: EO PAF mean 9.65 → 9.69 Hz (frontal8), 10.42 → 10.42 (muse4); alpha_exc EO→EC 1.41→3.93 (frontal8), 7.55→29.79 µV² (muse4).
Files: scripts/build_reference.py, models/reference.json, models/reference_features.csv

### 2026-11-27 21:26 — P4b scoring  (commits b825445, 7cbe9e3, fb264e3)
Type: feature
Change: src/scoring.py per §7.6 with ADR-011 (preset argument, duration from qc, missing-dimension renormalisation).
Why: the single score with breakdown judges must see.
Effect on calculations: first composite. S060 (held out), both runs, both references, both presets:
| preset | run | ref | composite | conf | attention | relaxation | load | signal q. | z alpha_exc |
|---|---|---|---|---|---|---|---|---|---|
| frontal8 | R01 (EO) | EO | **86.3** | 0.93 | 87.3 | 80.6 | 89.6 | 89.9 | 1.38 |
| frontal8 | R01 (EO) | EC | 88.9 | 0.93 | 90.7 | 90.6 | 84.3 | 89.9 | 0.28 |
| frontal8 | R02 (EC) | EO | **84.1** | 0.97 | 90.1 | 64.3 | 93.8 | 95.3 | 4.06 |
| frontal8 | R02 (EC) | EC | **89.4** | 0.97 | 96.7 | 79.4 | 89.1 | 95.3 | 2.24 |
| muse4 | R01 (EO) | EO | **84.2** | 0.83 | 91.3 | 78.6 | 89.0 | 72.9 | 1.17 |
| muse4 | R01 (EO) | EC | 84.1 | 0.83 | 84.8 | 86.6 | 87.1 | 72.9 | 0.02 |
| muse4 | R02 (EC) | EO | **83.7** | 0.81 | 97.2 | 69.9 | 87.0 | 79.2 | 3.30 |
| muse4 | R02 (EC) | EC | **86.5** | 0.81 | 98.9 | 78.4 | 85.8 | 79.2 | 1.94 |

Sanity: R01 vs EO > R02 vs EO — PASS both (margins 2.2 and 0.5 points); R02 vs EC > R02 vs EO — PASS both (5.3, 2.8).
Read: the eyes-open/closed contrast is carried almost entirely by alpha_exc (z 4.06 / 3.30 for R02 vs EO); other features are near-typical
in both runs, and averaging dilutes the contrast. Not tuned toward the expected result.
Review bugs (fixed before commit): None feature value crashed to_z (TypeError); all EEG features NaN gave composite 100 from signal quality alone.
Files: src/scoring.py, tests/test_scoring.py, docs/DECISIONS.md

### 2026-11-27 21:30 — P4 retro
Went well: every rule change (continuous z, n_kept ≥ 6) was measured before → after on the full reference, and both sanity directions hold.
Broke: two scoring edge cases (None value, signal-quality-only composite) — caught by adversarial probes, regression-tested.
Next: the composite separates EO from EC weakly (0.5–2.2 points on S060); sensitivity analysis (P6) should show how weights move this.

### 2026-11-27 21:40 — Check: why S060 R01 scores higher vs the EC reference (88.9) than vs EO (86.3)
Type: analysis (report only, no tuning)
frontal8 reference SDs on the transformed scale, eyes-open vs eyes-closed, with S060 R01 z:
| Feature | EO sd | EC sd | EO/EC | z vs EO | z vs EC |
|---|---|---|---|---|---|
| tbr_osc (ln1p) | 0.469 | 0.534 | 0.88 | 0.58 | −0.06 |
| tbr_classic (ln) | 0.789 | 0.588 | 1.34 | — | — |
| paf | 1.126 | 0.867 | 1.30 | 1.11 | 1.18 |
| alpha_exc (ln1p) | 0.592 | 0.808 | 0.73 | 1.38 | 0.28 |
| faa | 0.283 | 0.305 | 0.93 | −1.21 | −0.98 |
| hibeta_exc (ln1p) | 0.883 | 0.718 | 1.23 | 0.94 | 1.79 |
| ap_exponent | 0.389 | 0.260 | 1.50 | 0.45 | −0.30 |
Finding: the EO reference is wider for 4/7 features (ap_exponent, tbr_classic, paf, hibeta_exc) but narrower for alpha_exc, tbr_osc and faa.
The 2.6-point gap is location, not width: S060's eyes-open alpha is high for an eyes-open recording (z 1.38) and near the eyes-closed mean
(z 0.28) → Relaxation 80.6 vs 90.6; partly offset by high beta (Load 89.6 vs 84.3). Typicality is not a condition classifier.

### 2026-11-27 21:53 — BUG-002: boundary marks rejected valid epochs in concatenated sessions
Type: bugfix (BUG-002)
Symptom: S060 R03 demo session (15 T0 blocks × 4.1 s) gave n_total 11, not 15; drop_log said ('BAD boundary',) for epochs 7, 9, 12, 14.
Root cause: zero-length "BAD boundary" marks sit on a segment's first sample; MNE's time rounding put some inside the epoch window.
Fix: segment events are computed from the marks, then the marks are removed from clean()'s working copy before epoching
(other BAD_ annotations still reject). Test: test_boundary_marks_do_not_reject_valid_epochs (n_total == 15).
Before → After: S060 s02 n_total 11 → 15 (n_kept 3 → 3); continuous files unaffected (no boundary marks).
Files: src/preprocess.py, tests/test_preprocess.py

### 2026-11-27 21:47 — P5 longitudinal + DB  (commits 5c2a2dd, 5a3b972, 8a9a15b)
Type: feature
Change: src/longitudinal.py (baseline ddof=1 + 2.0 floor, EMA α 0.3, Gaussian posterior with obs_sd = 5 + 15·(1 − conf), flags |z| > 2 after the
baseline window, deltas vs baseline); src/db.py (one sqlite table, JSON columns, NaN/inf → null, numpy → Python).
Effect on calculations: none on scores. Hand-checked: EMA 80, 90, 70 → 80, 83, 79.1; posterior after (80, 90) with sd 5 → 84.737 ± 3.44.
Files: src/longitudinal.py, src/db.py, tests/test_longitudinal.py, tests/test_db.py

### 2026-11-27 21:55 — Finding: between-task rest in S060 is much noisier than true rest
Type: analysis
S060's T0 blocks inside the motor runs R03–R14 are 1.5–2× the amplitude of its R01 rest on every channel (median p2p F3 ≈ 300 vs 196 µV,
Fp2 ≈ 420 vs 222 µV, before ICA). Filtering the continuous run first gives the same p2p (351–469 µV on R03), so it is the data, not the joins.
After ICA, 0–5 of 15 epochs passed 200 µV; 5 of 12 sessions unscorable, the rest confidence 0.25–0.43 — the confidence score flagged it.
Threshold not loosened. Demo subject switched to S051 (ADR-012 addendum); S060 remains the sample/test subject.

### 2026-11-27 22:02 — Longitudinal demo built on S051  (commits 3408df9, 29aa9e8, 81bea35, 3fd6025)
Type: feature + data
Command: python scripts/download_data.py --demo && python scripts/build_demo_sessions.py
Before → After (demo subject S060 → S051): sessions scored 8/13 → 13/13; T0 kept per session 0–5 → 14–15; T0 confidence 0.25–0.43 → 0.87–0.99.
| Session | Source | Kept | Composite | Confidence | EMA | Posterior mean ± sd | Flag |
|---|---|---|---|---|---|---|---|
| s01 | R01 eyes-open rest | 29/29 | 87.0 | 0.96 | 87.0 | 87.0 ± 5.3 | |
| s02 | R03 T0 blocks | 15/15 | 83.5 | 0.97 | 85.9 | 85.3 ± 3.8 | |
| s03 | R04 T0 blocks | 15/15 | 82.1 | 0.98 | 84.8 | 84.2 ± 3.1 | |
| s04 | R05 T0 blocks | 15/15 | 85.1 | 0.98 | 84.9 | 84.4 ± 2.6 | |
| s05 | R06 T0 blocks | 15/15 | 85.6 | 0.98 | 85.1 | 84.7 ± 2.4 | |
| s06 | R07 T0 blocks | 15/15 | 86.6 | 0.98 | 85.5 | 85.0 ± 2.2 | |
| s07 | R08 T0 blocks | 15/15 | 82.8 | 0.99 | 84.7 | 84.7 ± 2.0 | |
| s08 | R09 T0 blocks | 15/15 | 84.8 | 0.98 | 84.8 | 84.7 ± 1.9 | |
| s09 | R10 T0 blocks | 15/15 | 85.9 | 0.87 | 85.1 | 84.8 ± 1.8 | |
| s10 | R11 T0 blocks | 15/15 | 85.4 | 0.99 | 85.2 | 84.8 ± 1.7 | |
| s11 | R12 T0 blocks | 15/15 | 82.6 | 0.96 | 84.4 | 84.6 ± 1.6 | |
| s12 | R13 T0 blocks | 14/15 | 79.8 | 0.96 | 83.0 | 84.3 ± 1.6 | |
| s13 | R14 T0 blocks | 15/15 | 84.8 | 0.97 | 83.6 | 84.3 ± 1.5 | |
Baseline (s01–s03): 84.2 ± 2.53. No flags: largest deviation s12, |79.8 − 84.2| / 2.53 = 1.74 < 2. Not tuned.

Files: src/config.py, src/reference.py, scripts/download_data.py, scripts/build_demo_sessions.py, data/demo/ (13 × ~0.3 MB)

### 2026-11-27 22:05 — P5 retro
Went well: the T0 problem was diagnosed with numbers before any change (grid misalignment → ADR-012; boundary rounding → BUG-002;
amplitude → data), and the screening rule was fixed before looking at candidates.
Broke: epoching straddled joins (1 epoch/session); boundary marks rejected 4/15 valid epochs after a FIF round trip; the first BUG-002 test
did not reproduce the bug (in-memory only) — rewritten to round-trip through FIF and shown to fail on the old code.
Next: P6 ML validation (train subjects from reference.json; assert_no_leak covers S051/S060/holdout).

### 2026-11-28 08:44 — Probe: S051 R02 (eyes closed) as a "condition change" session — not added
Type: analysis
Question: would an eyes-closed recording, scored against the eyes-open frontal8 reference, flag in the S051 tracker?
Command: score S051 R02 with the demo pipeline (load_eeg → clean(line_freq 60) → extract → score(condition="eyes_open", preset="frontal8")).
Result: composite 87.0, confidence 0.82, kept 28/29. z vs baseline = (87.0 − 84.16) / 2.53 = **+1.13 < 2 → no flag**. Not added to the demo.
| Dimension | S051 R02 vs EO ref | Baseline s01–s03 mean |
|---|---|---|
| Attention | 91.6 | 82.9 |
| Relaxation | 85.5 | 86.4 |
| Load | 92.7 | 76.3 |
| Signal quality | 71.5 | 95.5 |
Feature z: tbr_osc −1.00, paf +0.12, alpha_exc −1.18, faa −0.75, hibeta_exc −0.93, ap_exponent +0.05. Control: R02 vs EC ref = 85.5.
Why it does not move: S051 has no frontal alpha rhythm above the 1/f background in either condition —
alpha_exc 0.016 (R01) → 0.000 (R02) µV², alpha_osc 0.90 → 0.79, paf_fallback_frac 1.0 in both. Classic alpha_abs does rise
1.18 → 1.56 µV² (+32%), but the score uses excess power (ADR-008), so eyes closing is invisible for this subject; dimension changes
partly cancel (Load up, Signal quality down via fooof_r2 0.973 → 0.893). Limitation worth stating: a subject with no frontal alpha
peak cannot show an EO→EC shift in the excess-power score. Nothing tuned.
Files: none (data/raw/S051/S051R02.edf fetched, gitignored)
