# Reviews

Format:
```
## <file> — <date> — PASS | FIXED | KNOWN-ISSUE
Tried to break: <what>   Checked: <numbers>
Found: <issues>   Fixed: <how, commit>   Remaining: <limits>
```

## src/config.py — 2026-11-27 — PASS
Tried to break: unit slip (µV vs V), hidden hard-coded mains frequency, FAA groups not inside presets, demo subject leaking into reference.
Checked: weights sum = 1.0; FAA groups ⊆ preset channels (both presets); S060 ∉ 50 reference subjects; REJECT_PTP_V = 150e-6 V = 150 µV; bin = 0.5 Hz; overlap = 0.5.
Found: none. hibeta 20–30 overlaps beta 13–30 by design (§7.5). Remaining: weights are a design choice → sensitivity analysis (P8).

## scripts/download_data.py — 2026-11-27 — PASS (KNOWN-ISSUE noted)
Tried to break: interrupted download leaving a truncated file; 0-byte file; rerun duplicating work.
Checked: run 1 → 114 downloaded / 0 failed; run 2 → 114 skipped / 0 downloaded; 114 EDF on disk (S060: 14), 0 `.part` left, 153.3 MB; `data/raw/` ignored by git.
Found: no checksum verification against PhysioNet SHA256SUMS. Remaining: accepted — every file is parsed by MNE in P1+, which fails loudly on corruption.

## PR review — P0 Setup (0aa60dc..docs commit) — 2026-11-27 — PASS
Tried to break: tooling/junk files in history, absolute paths, stray prints in src/, author identity, AI trailers.
Checked: 5 committed files only (.gitignore, requirements.txt, src/__init__.py, src/config.py, scripts/download_data.py) + docs/; no absolute paths or prints in src/; all commits "Mohankumar M"; `Co-Authored` grep empty; CLAUDE.md, plan.md, .claude/, .claude-flow/, .venv/, data/raw/ all ignored.
Found: none blocking. Remaining: download checksum (accepted, above).
