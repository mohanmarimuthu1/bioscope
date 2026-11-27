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

### 2026-11-27 20:45 — P1 retro
Type: retro
Went well: one label rule covers all 64 EEGMMI names; clean-clone run proved tests stay green without raw data (17 passed, 3 skipped).
Broke + fix: assumed 9,600-sample length was wrong (9,760) → gate now data-driven; hook blocked a commit body wording → reworded.
Next: P2 preprocess — watch ICA on Windows and the 150 µV retention on unfiltered ~100 µV signals.
