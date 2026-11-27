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
Checked: 5 committed files only (.gitignore, requirements.txt, src/__init__.py, src/config.py, scripts/download_data.py) + docs/; no absolute paths or prints in src/; all commits "Mohankumar M"; AI-trailer grep empty; CLAUDE.md, plan.md, .claude/, .claude-flow/, .venv/, data/raw/ all ignored.
Found: none blocking. Remaining: download checksum (accepted, above).

## src/io_utils.py — 2026-11-27 — PASS
Tried to break: upper-case `.EDF`; already-normalised FIF names; `T10.`; non-EEGMMI scheme (`EEG Fp1-REF`); missing file; channel order after pick; annotations lost on pick.
Checked: S060R01 → (8, 9760)/(4, 9760) == (n_ch, source n_times); sfreq 160.0; duration 61.0 = 9760/160; 64/64 unique labels; S060R03 T0 ×15 after load.
Found: none. Remaining (KNOWN): other naming schemes fail with a clear missing-channel error (ASSUMPTION in docstring); missing file raises MNE's FileNotFoundError → UI must catch (P7).

## tests/test_io.py — 2026-11-27 — PASS
Tried to break: run on a clean clone with no data/raw; magic-number shapes.
Checked: local 20 passed; clean clone (E:\hackathon\_cleanclone, deleted after) 17 passed + 3 skipped; gate asserts use source n_times.

## src/preprocess.py — 2026-11-27 — FIXED (spec bug) → PASS, KNOWN-ISSUE noted
Tried to break: unit slip (checked EDF header: µV, 1:1); ICA that never fires; caller Raw mutated; ICA exception; unknown montage; all epochs rejected; < 4 s file; notch boundary.
Checked: audit 20 files × 2 presets with retention, components removed, |r|, s/file, p2p percentiles.
Found: z ≥ 3 unreachable with 7 comps (0 removed in 20/20) → ADR-005; muse4 without ICA 57% → ADR-006. Audit header "|z|" actually |r| (docs corrected).
Remaining: sklearn FastICA ConvergenceWarning seen once in 40 runs (not surfaced in qc); muse4 removes 1 comp in every file — alpha-preservation check in P3; S009 0% retention.

## tests/test_preprocess.py — 2026-11-27 — PASS
Tried to break: forced ICA failure via monkeypatch; threshold not really read from config (monkeypatched to 1 µV → 0 kept). Checked: 32 passed.

## PR review — P2 preprocess (f0cb096..HEAD) — 2026-11-27 — PASS
Tried to break: history hiding the tune (no — spec ICA 896654c, then tune df12993 with before→after in body); stray files; red commits.
Checked: 4 code/test commits (c83c8bf, 896654c, df12993, 5c30406, f2d707b) + docs; only src/preprocess.py, src/config.py, tests/test_preprocess.py touched; owner-only authors; gate table below.
Gate: frontal8 EO 79% ≥ 70% ✓, EC 100% ≥ 70% ✓; muse4 EO 100% ≥ 50% ✓; mean s/file 0.73 / 0.11 < 10 ✓.

## PR review — P1 io_utils (0fd8742..HEAD) — 2026-11-27 — PASS
Tried to break: commits that are red in isolation, stray files, hooks bypassed.
Checked: order feat(io) → data(sample) → test(io) keeps every commit green; 4 files total (src/io_utils.py, data/sample/sample_frontal8_raw.fif, tests/test_io.py, pytest.ini) + docs; all commits by the owner; hooks ran on each commit (and blocked one message, see DEVLOG).
Found: none.
