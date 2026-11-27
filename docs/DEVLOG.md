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

### 2026-11-27 20:25 — P0 retro
Type: retro
Went well: env built entirely on E: (Python 3.11 via uv, no C: growth); FOOOF verified on numpy 2.4 before any feature code.
Broke + fix: a placeholder commit hash slipped into this log; caught in self-review and replaced with the real hash (0aa60dc).
Next: start ~4.5 h late → P2/P3 move to Sat morning; keep doc entries short during build, expand in P8.
