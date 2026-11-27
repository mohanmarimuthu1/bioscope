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

## src/features.py — 2026-11-27 — FIXED (2 spec issues) → PASS
Tried to break: missing µV conversion (test: alpha_abs 24.4 µV² on sample; ~1e-11 without); flat channel; 0 epochs; pure 1/f; slope change; theta near alpha; zero beta rhythm; failed FOOOF.
Checked: 43 tests; 20 real recordings × 2 presets (PAF, fallback, EC>EO, NaN counts, timing ≤ 1.43 s).
Found: PAF window caught theta (ADR-009); ratio osc slope-sensitive (ADR-008); FOOOF spurious peaks in 60 s noise at min_peak_height 0.1 (spec value kept; test uses 300 s).
Remaining: alpha_exc can be exactly 0 (3/10 EO) → P4 decision; per-epoch rows share the session 1/f fit (ADR-007).

## tests/test_features.py — 2026-11-27 — PASS
Tried to break: guard only testable via monkeypatch → added a direct unit test too; FAA test relies on gains on rhythm only (background symmetric). Checked: 43 passed.

## PR review — P3 features (5cb0403..HEAD) — 2026-11-27 — PASS
Tried to break: tunes hidden in the feat commit (no: spec 131393e → tunes d3606d8, fbfb3f1 with numbers); holdout commit mixed in (separate 211ca89); leftover probe scripts in repo (kept in E:\hackathon\_work, outside).
Checked: files touched src/features.py, src/config.py, tests/test_features.py, scripts/download_data.py + docs; owner-only; clean-clone run below.
Gate: pytest green; S060 EC > EO alpha_exc (21.20 vs 3.55) and alpha_osc; ADR-006 muse4 contrast preserved 9/10; timing 0.45 s/file.

## PR review — P2 preprocess (f0cb096..HEAD) — 2026-11-27 — PASS
Tried to break: history hiding the tune (no — spec ICA 896654c, then tune df12993 with before→after in body); stray files; red commits.
Checked: 4 code/test commits (c83c8bf, 896654c, df12993, 5c30406, f2d707b) + docs; only src/preprocess.py, src/config.py, tests/test_preprocess.py touched; owner-only authors; gate table below.
Gate: frontal8 EO 79% ≥ 70% ✓, EC 100% ≥ 70% ✓; muse4 EO 100% ≥ 50% ✓; mean s/file 0.73 / 0.11 < 10 ✓.

## PR review — P1 io_utils (0fd8742..HEAD) — 2026-11-27 — PASS
Tried to break: commits that are red in isolation, stray files, hooks bypassed.
Checked: order feat(io) → data(sample) → test(io) keeps every commit green; 4 files total (src/io_utils.py, data/sample/sample_frontal8_raw.fif, tests/test_io.py, pytest.ini) + docs; all commits by the owner; hooks ran on each commit (and blocked one message, see DEVLOG).
Found: none.

## src/reference.py — 2026-11-27 — FIXED → PASS, KNOWN-ISSUE noted
Tried to break: ln(0) inputs; NaN values; < 3 finite values; std 0; value exactly at min/max; far outside range; `python -O`; leaked S060/S061.
Checked: 10 unit tests; ADR-010 worked example reproduced by hand-run code.
Found: `assert_no_leak` used bare `assert` → silently disabled under -O. Fixed: explicit raise (ed0a2e4, verified under -O).
Remaining: hybrid z jumps at the range edge (max 2.05 → just above 3.85, frontal8 EC hibeta_exc); `_read` is lru_cached, so a rebuilt json needs an app restart.

## scripts/build_reference.py — 2026-11-27 — PASS
Tried to break: determinism (2 rebuilds), NaN in json, demo/holdout leak, console encoding of µ.
Checked: rebuild identical except build_date; no NaN/Infinity (now also `allow_nan=False`); 4 sanity checks PASS; skipped subjects listed per cell.
Found: µ printed as mojibake on Windows console → ASCII "uV^2". Remaining: FastICA ConvergenceWarning on ~3% of fits (pre-existing, P2).

## tests/test_reference.py — 2026-11-27 — PASS
Tried to break: comparison with hand-computed mid-ranks and Φ⁻¹; caps both signs. Checked: 10 passed; suite 53 passed.

## P4a phase PR review (499c293..HEAD) — 2026-11-27 — PASS
Diff: config (+3 constants), reference.py, build_reference.py, tests, models/. Contract change load_reference(condition, preset) recorded in ADR-010. No scoring code yet (P4b). Author check: owner only.
