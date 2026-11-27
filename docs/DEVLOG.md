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
