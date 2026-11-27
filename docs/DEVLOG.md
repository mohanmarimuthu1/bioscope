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

### 2026-11-27 20:40 — P2 retro
Type: retro
Went well: audit-first caught a spec bug (z ≥ 3 unreachable with 7 comps) with numbers before any feature code; every option was evaluated on the same 20 files.
Broke + fix: 0–12% retention → ADR-005 (correlation ICA, 200 µV) → 97%; muse4 14–57% → ADR-006 (3-comp ICA) → 100%. Audit table column mislabelled "|z|" (values are |r|) — corrected in docs.
Next: P3 must verify muse4 ICA did not remove alpha (EC > EO alpha_osc); S009 is an outlier to watch in the reference.
