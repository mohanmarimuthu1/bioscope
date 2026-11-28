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

## src/reference.py rev 2 + scripts/build_reference.py inclusion — 2026-11-27 — PASS
Tried to break: z at min/max ± 1e-9; monotonicity over a 400-point grid past both edges; cap both signs; rebuilt reference method flips.
Checked: 12 reference tests; worked example rev 1 → rev 2; 2 method changes listed in ADR-010. Remaining: rank step inside the range (~0.17 z at n = 49).

## src/scoring.py — 2026-11-27 — FIXED → PASS
Tried to break: None feature value; all EEG features NaN; whole dimension NaN; missing duration; fooof_r2 NaN; extreme values (paf 30 Hz,
alpha 1e6 µV², r2 0.1); bad condition/preset; 0 epochs from 500 µV noise.
Checked: 17 tests; S060 8-row breakdown (DEVLOG 21:26).
Found: (1) None → TypeError in to_z; (2) composite 100 with no EEG feature. Fixed before commit (b825445) + regression tests (7cbe9e3).
Unused loggers → used (fb264e3). Remaining: EO/EC separation by the composite is small (0.5–2.2 points on S060).

## P4 phase PR review (499c293..fb264e3) — 2026-11-27 — PASS
Diff: 16 files, +2027. Contracts changed: load_reference(condition, preset) (ADR-010), score(…, preset) (ADR-011), CLAUDE.md §6 synced.
Checked: no prints in src/, no absolute paths, all constants in config, holdout/demo leak guard raises under -O, suite 72 passed.
Author check: owner only. Remaining for P5/P7: callers must pass preset and qc["duration_s"].

## src/preprocess.py (ADR-012 + BUG-002) — 2026-11-27 — FIXED → PASS
Tried to break: continuous file event equality; 3 synthetic segments 4.1/9.0/4.1 s; real concatenated T0 after FIF round trip; epochs crossing joins.
Found: boundary marks rejected 4/15 epochs after FIF round trip (BUG-002, 0b520a8). First regression test passed on the old code (in-memory
only) → rewritten through FIF; verified it fails on 6ebb2ae (n_total 11) and passes now. Reference rebuild unchanged.

## src/longitudinal.py — 2026-11-27 — PASS
Tried to break: None in scores; length mismatch; empty list; constant baseline (std 0 → floor 2.0); a wild baseline session; confidence 0 and 1.
Checked: 7 hand-computed tests. Remaining: inputs must be pre-filtered for None (documented).

## src/db.py — 2026-11-27 — PASS
Tried to break: NaN, ±inf, None, numpy bool/int/array inside nested dicts; None composite; out-of-order inserts; unknown subject.
Checked: 3 tests in tmp_path; demo DB seeded with 13 rows. Remaining: no schema migration (single table, fine for the prototype).

## scripts/build_demo_sessions.py — 2026-11-27 — PASS
Tried to break: boundary crossings (asserted 0 in all 13); T1/T2 fragments in cropped blocks (removed); re-running (DB rows deleted first).
Checked: output matches the independent screening run exactly (13 composites). No S060 files committed (grep: 13 S051, 0 S060).

## P5 phase PR review (c74ac45..HEAD) — 2026-11-27 — PASS
Diff: preprocess epoching, longitudinal, db, demo builder, --demo download, S051 guard, data/demo, reference metadata. Contracts unchanged
except additive (`db_path`, qc `n_segments`). All score() callers pass preset and qc["duration_s"] (grep). Suite 85 passed. Author: owner only.

## src/ml_sanity.py — 2026-11-28 — PASS
Tried to break: empty table (object dtypes) → returns before astype; missing column → ValueError; shap 0.51 list output for binary LightGBM
(warning seen) → additivity test proves the eyes-closed class is used (atol 1e-6); explainer pickling (asserted absent).
Checked: S060 R01 p 0.187 (27 epochs), R02 p 0.914. Remaining: lru_cache keeps the old model if retrained during an app session.

## scripts/train_sanity_model.py — 2026-11-28 — FIXED → PASS
Tried to break: subject on both sides of a fold (asserted, none); held-out subjects (assert_no_leak twice + ⊆ S001–S050); determinism
(two runs, identical fold numbers); subjects with only one usable run (excluded from paired, n = 44); permutation p floor (16-shuffle smoke run p = 1/17).
Found: a print with "→" crashed on the Windows cp1252 console → ASCII "->". Remaining: permutation run ~4 min.

## tests/test_ml_sanity.py — 2026-11-28 — PASS
Tried to break: ran with -W default; the new warnings are shap/matplotlib deprecations + the known FastICA notice. 7 passed; suite 92 passed.

## P6 phase PR review (3d4225d..c6b114b) — 2026-11-28 — PASS (gate replaced, ADR-013)
Diff: config ML block, ml_sanity, train script, models artefacts, tests. Contract: `predict` returns the §6 keys plus additive p_epochs,
base_value, warnings. Model never imported by scoring.py (grep). Original 80% gate FAIL recorded in metrics.json and ADR-013; new gate PASS.
Suite 92 passed. Author: owner only.

## scripts/evaluate_holdout.py — 2026-11-28 — PASS
Tried to break: missing file (S999) → returned as an error record, run continues; leak guard with S001 → raises; per-channel warnings grouped
("on F7" → "on <ch>"); recordings with 0 clean epochs → excluded from ML, counted unscorable in scores (7 EO, 2 EC); non-160 Hz → listed (none).
Checked: 98/98 ok; counts consistent (tested). Remaining: permutation null mean is 0.521, not 0.5 — pooled AUC across subjects with unequal
label balance; the within-subject shuffle keeps that structure, which is the intended null.

## tests/test_holdout.py — 2026-11-28 — PASS
Tried to break: count identities and CI ordering; skips cleanly without holdout.json. Suite 95 passed.

## P6b phase PR review (618efe7..7eb0aa3) — 2026-11-28 — PASS
Diff: config paths, evaluate_holdout.py, holdout artefacts, tests. No refit (the script never calls fit). No contract change. Author: owner only.

## scripts/report_classification.py — 2026-11-28 — FIXED → PASS
Tried to break: reproduce the stored CV from the committed CSV → fold 1 LightGBM acc 0.661 vs stored 0.667 (rounded features) → the script
now re-extracts from raw and asserts |diff| ≤ 1e-3 on every fold accuracy/AUC; holdout epoch count must equal holdout.json (2019).
Checked: TN+FP+FN+TP = 2206 (CV) / 2019 (holdout); per-recording n 93 / 89; empty calibration bins handled (none occurred).
Remaining: report only — LightGBM overconfidence is documented, not corrected.

## src/pipeline.py — 2026-11-28 — PASS
Tried to break: .csv upload; muse4 on the frontal8 sample (missing channels listed); 2 s file; 500 µV noise (0 epochs → composite None,
no spectrum, ml unavailable); blank subject ID; repeated saves (index 1, 2). Checked: seeding reproduces all 13 P5 composites to 0.1.
Remaining: corrupt-file errors depend on MNE raising OSError/RuntimeError (others reach the UI guard as a generic message).

## src/ui.py + pages — 2026-11-28 — FIXED → PASS
Tried to break: empty DB (auto-seed), pre-ADR-014 DB (re-seed), session with composite None, muse4 session (no SHAP), page links when a page
is the entrypoint. Found: gauge passed `margin` twice → TypeError (guard showed a friendly error; AppTest caught it) → `_layout` merges margins.
Checked: AppTest 6/6; clean clone all pages 0 exceptions/0 errors. Remaining: light/dark readability needs a visual check in a browser.

## P7 phase PR review (78831cb..b3c6821) — 2026-11-28 — PASS
Diff: db extras (ADR-014), pipeline, ui helpers, 5 pages, streamlit config, tests. Contracts: additive only (db record `extras`,
reference_n). Scores unchanged (seeding test). No traceback path: every page body runs inside ui.guard. Suite 111 passed; clean clone 104
passed / 7 skipped. Author: owner only.
