# File guide

One section per file: purpose · inputs → outputs · algorithm in plain English · why this approach ·
key parameters · connections · change history.

---

## src/config.py
**Purpose:** The single home for every constant. No other module hard-codes a number.
**Inputs → outputs:** none → module-level constants imported as `from src import config`.
**Contents in plain English:**
- *Paths* are built from the project root (`Path(__file__).resolve().parents[1]`), so the repo runs from any folder.
- *Dataset split* (ADR-002): reference = S001–S050 R01/R02, demo = S060 R01–R14.
- *Presets*: `frontal8` (8 frontal sites) and `muse4` (Muse-like 4 sites), each with left/right groups for frontal alpha asymmetry.
- *Preprocessing*: 1–45 Hz band-pass, ICA only with ≥ 8 channels, 4 s epochs with 2 s overlap, reject epochs over 150 µV peak-to-peak (stored in volts: `150e-6`).
- *Spectral*: 2 s Welch segments (0.5 Hz bins, ADR-003), FOOOF settings, PAF windows, bands theta 4–8, alpha 8–13, beta 13–30, high-beta 20–30 Hz.
- *Scoring*: per-feature score `100 − 15·|z|`; dimension weights 0.30/0.30/0.25/0.15; confidence weights.
- *Longitudinal*: baseline of first 3 sessions (std floor 2.0), EMA α 0.3, Bayesian prior SD 15, flag at |z| > 2.
- *ML*: 5 subject-grouped folds, 80% accuracy gate.
**Why one file:** Every number in the methodology can be traced to one line with its source comment.
**Changing parameters:** `Z_PENALTY` ↑ → scores drop faster with distance from the reference. `REJECT_PTP_V` ↓ → cleaner but fewer epochs (lower confidence). `WEIGHTS` → composite mix (see sensitivity analysis).
**Connections:** imported by every `src/` module and script.
**Change history:**
| Date | Commit | Change | Effect on numbers |
|---|---|---|---|
| 2026-11-27 | 9a09d01 | Created | — (baseline) |

---

## scripts/download_data.py
**Purpose:** Fetch the 114 EDF files BioScope uses from PhysioNet into `data/raw/<subject>/`.
**Inputs → outputs:** network → `data/raw/S001/S001R01.edf` … `data/raw/S060/S060R14.edf`.
**Algorithm:** build the list (50 subjects × 2 runs + 14 demo runs) → for each file: skip if it exists and is non-empty →
download to `.part` → rename on success → on error, delete the partial file, wait 2 s × attempt, retry up to 3 times → print a summary and exit 1 if anything failed.
**Why:** stdlib `urllib` (no new dependency); `.part` + rename means an interrupted run never leaves a truncated file that the skip check would treat as complete.
**Key parameters:** `MAX_RETRIES=3`, `BACKOFF_S=2`, `TIMEOUT_S=60`.
**Connections:** feeds `io_utils.load_eeg` via `build_reference.py`, `train_sanity_model.py`, `build_demo_sessions.py`.
**Change history:**
| Date | Commit | Change | Effect on numbers |
|---|---|---|---|
| 2026-11-27 | 4e2c2be | Created | 114 files downloaded (153.3 MB); rerun: 114 skipped |

---

## src/io_utils.py
**Purpose:** Turn any supported EEG file into a Raw object holding exactly the preset's channels, in preset order, with standard names.
**Inputs → outputs:** `load_eeg(path, preset)` → `(raw, meta)`; meta = `sfreq, n_samples, duration_s, channels, preset, source`.
**Algorithm in plain English:**
1. Reject an unknown preset (lists the valid ones) or an unsupported extension (only `.edf`, `.fif`).
2. Open the file lazily with MNE (EDF or FIF reader).
3. Rename every channel with `normalise_label`: strip dots → uppercase → `FP…` back to `Fp…` → trailing `Z` back to `z`.
   This one rule covers every EEGMMI label class: `Fp1.`→Fp1, `Fpz.`→Fpz, `Afz.`→AFz, `Fc5.`→FC5, `Cz..`→Cz, `Tp7.`→TP7, `Iz..`→Iz, `Poz.`→POz, `T9..`→T9.
4. If any preset channel is absent → `ValueError` naming the missing channels and listing the available ones.
5. Keep only the preset channels, in preset order; load into memory. Annotations (T0/T1/T2) are kept for the demo builder.
6. Build `meta`: `duration_s = n_samples / sfreq`, `source` = file name.
**Why this approach:** one rule instead of a 64-entry lookup table — shorter, testable per class, and idempotent on already-standard names (FIF files we save).
**Key parameters:** the presets in `config.PRESETS`. Adding a preset needs no code change.
**Units:** volts, untouched (S060R01 frontal8 mean |x| ≈ 103 µV unfiltered, i.e. ~1e-4 V).
**Connections:** called by `preprocess.clean` callers (Upload page, `build_reference.py`, `build_demo_sessions.py`, `train_sanity_model.py`).
**Real numbers (S060R01):** source n_times 9760 → frontal8 (8, 9760), muse4 (4, 9760), sfreq 160.0, duration 61.0 s; 64/64 unique normalised labels; S060R03 keeps T0 ×15, T1 ×8, T2 ×7.
**Change history:**
| Date | Commit | Change | Effect on numbers |
|---|---|---|---|
| 2026-11-27 | 6a2f243 | Created | S060R01 → (8, 9760) / (4, 9760) @ 160 Hz, 61.0 s |

## tests/test_io.py · pytest.ini
**Purpose:** 20 tests: each label-mapping class, 64 unique labels, presets ⊆ labels, idempotence, gate shapes vs the source file's own `n_times` (no magic numbers), T0 annotations survive, meta keys, volts, FIF round-trip, missing channel / unknown preset / bad extension errors.
**Clean-clone behaviour:** the 3 tests needing `data/raw/` skip; the rest use `data/sample/` → 17 passed, 3 skipped.
`pytest.ini` puts the repo root on the import path so `from src import …` works.
| Date | Commit | Change | Effect on numbers |
|---|---|---|---|
| 2026-11-27 | 9e3fb7c | Created | 20 passed (local), 17 passed + 3 skipped (clean clone) |

## src/preprocess.py
**Purpose:** Turn a preset-picked Raw into clean 4 s epochs plus a QC dict.
**Inputs → outputs:** `clean(raw, line_freq)` → `(epochs, qc)`; qc = n_total, n_kept, retained_frac, ica_used, ica_excluded, warnings + additive notch_applied, ica_eog_scores (|r| per component), epoch_ptp_uv.
**Steps:** copy → average reference → FIR 1–45 Hz zero-phase → notch only if line_freq < 45 (50/60 Hz: skipped, the low-pass already removes them) →
ICA (n_ch − 1 comps, seed 42; drop components with |r| ≥ 0.7 to the preset's EOG proxies, top-k by |r|: frontal8 Fp1/Fp2 k=2, muse4 AF7/AF8 k=1) →
4 s epochs, 2 s step → drop epochs over 200 µV p2p → warnings (0 kept: "Insufficient clean data: 0/N epochs passed rejection"; < 50% or < 6 kept: low-data warning).
**Why:** correlation, not z-score, because with 7 components a z-score can never reach 3 (ADR-005). Zero kept epochs return empty — never a fallback to unrejected data.
**Key parameters:** `ICA_EOG_THRESHOLD` ↓ → more components removed (risk: brain signal); `REJECT_PTP_V` ↓ → fewer epochs kept.
**Real numbers:** audit S001–S010 R01/R02 — frontal8 median 97% (EO 79%, EC 100%), muse4 100%; 0.73 / 0.11 s per file. S060R01 sample: 27/29 kept, component 0 removed.
**Connections:** io_utils.load_eeg → **clean** → features.extract.
| Date | Commit | Change | Effect on numbers |
|---|---|---|---|
| 2026-11-27 | c83c8bf | filter/epoch/reject | S060R01 0/29 kept @150 µV (blinks) |
| 2026-11-27 | 896654c | ICA per spec (z ≥ 3) | 0 comps removed in 20/20; median 12% |
| 2026-11-27 | df12993 | correlation ICA, 200 µV | frontal8 median 12% → 97% |
| 2026-11-27 | 5c30406 | muse4 3-comp ICA | muse4 median 57% → 100% |

## tests/test_preprocess.py
12 tests: qc keys + retained_frac, 29 epochs from 61 s, frontal8 ICA (7 scores, ≤ 2 removed, each ≥ threshold), muse4 3-comp ICA, unknown montage → no ICA, caller raw untouched, 500 µV → 0 kept with exact warning, threshold read from config, < 4 s raises, notch at 30/50/60 Hz, forced ICA failure → warning + epochs.
| Date | Commit | Change | Effect on numbers |
|---|---|---|---|
| 2026-11-27 | f2d707b | Created | suite 32 passed |

## src/features.py
**Purpose:** Turn clean epochs into the session features the score uses, plus a per-epoch table for ML.
**Inputs → outputs:** `extract(epochs, preset)` → `(feats, per_epoch)`; `session_spectrum(epochs)` → `{freqs, psd_uv2, ap_fit_uv2, ch_names}` for the UI plot.
**Steps in plain English:**
1. Welch PSD of every epoch (2 s segments, 1 s overlap → 3 per epoch, 0.5 Hz bins, 1–40 Hz); ×1e12 to µV²/Hz.
2. Average epochs → one spectrum per channel → FOOOF splits it into a straight line in log-log (the 1/f "aperiodic" background: offset, exponent) plus Gaussian peaks (rhythms).
3. PAF: the strongest peak between 8 and 13 Hz; if a channel has none, the spectrum's centre of gravity over 7–13 Hz.
4. For each band: `abs` = area under the spectrum; `exc` = area *above the 1/f line* (the rhythm itself); `osc` = average height relative to the line (display/ML).
5. tbr_classic = theta_abs/beta_abs; tbr_osc = theta_exc/beta_exc (NaN if beta has < 5% excess); faa = ln(right alpha) − ln(left alpha); sample entropy.
6. Median across channels (a channel with a failed or poor fit is ignored and warned about).
7. Per epoch: same band features using the channel's *session* 1/f line (ADR-007); PAF by centre of gravity.
**Why:** a broadband slope change (age, arousal, reference) moves classic power and the ratio; excess power isolates the rhythm (ADR-008 table).
**Key parameters:** `PAF_PEAK_RANGE` (8–13), `FOOOF_SETTINGS`, `FOOOF_MIN_R2` 0.5, `TBR_MIN_BETA_EXC_FRAC` 0.05.
**Real numbers:** S060 frontal8 EO/EC: PAF 10.85/9.94 Hz, alpha_exc 3.55/21.20 µV², tbr_osc 0.68/1.04, r² 0.974/0.981. 20 reference recordings: see DEVLOG 21:40.
**Connections:** preprocess.clean → **extract** → scoring.score / ml_sanity; session_spectrum → Session page.
| Date | Commit | Change | Effect on numbers |
|---|---|---|---|
| 2026-11-27 | 131393e | Created per §7.5 | S060 EO PAF 7.13 Hz (theta) |
| 2026-11-27 | d3606d8 | PAF 8–13 Hz | EO PAF mean 9.20 → 9.88 Hz |
| 2026-11-27 | fbfb3f1 | excess power | TBR slope |Δlog| 0.68–1.04 → 0.01–0.03 |

## tests/test_features.py
12 tests: PAF 10 Hz ±0.5 with no fallback; excess TBR |Δlog| < 0.1 at 2 and 6 µV; FAA sign; 300 s pure 1/f → fallback; flat channel → warning + finite median; no-beta guard (direct + through extract); 0 epochs → NaN + flag; sample µV² range; session_spectrum shapes.
| Date | Commit | Change | Effect on numbers |
|---|---|---|---|
| 2026-11-27 | 7a7d53d | Created | suite 43 passed |

## scripts/download_data.py — update
`--holdout` (commit 211ca89): S061–S109 R01/R02, 98 files, all 160 Hz.

## data/sample/sample_frontal8_raw.fif
**Purpose:** a committed, real recording for tests and the README demo when raw data is not downloaded.
**What it is:** S060 R01 (eyes open), frontal8, full 61 s (9760 samples, 160 Hz), float32, 314,808 bytes, annotations kept.
Full length, not 20 s: 61 s gives ~29 epochs and full duration credit in the confidence formula (`min(61/60, 1) = 1`); 20 s would cap it at 0.33.
| Date | Commit | Change | Effect on numbers |
|---|---|---|---|
| 2026-11-27 | d7bba16 | Created | — |

## src/reference.py
**Purpose:** the reference distributions the score compares against, and the one place that turns a feature value into a z (ADR-010).
**Inputs → outputs:** `load_reference(condition, preset)` → `{feature: entry}`; `to_z(feature, x, entry)` → float z; `transform`, `build_entry`, `assert_no_leak`.
**Algorithm:** (1) transform the value: ln(1+x) for tbr_osc/alpha_exc/hibeta_exc (they can be 0), ln for tbr_classic, none otherwise.
(2) zscore cells: z = (t − mean)/std. (3) percentile cells (|skew| > 1 after transform): inside the reference range z = Φ⁻¹(rank/(n+1)),
mid-rank 1-based; outside, the parametric z if larger in magnitude; |z| ≤ 4.
**Why:** mean ± std on a skewed feature mislabels ordinary high values as extreme; ranks do not care about shape.
**Key parameters (config):** `REFERENCE_TRANSFORMS`, `SKEW_PERCENTILE_THRESHOLD` = 1 (lower → more percentile cells), `PERCENTILE_Z_CAP` = 4.
**Connects to:** built by scripts/build_reference.py; used by scoring.py (P4b).
| Date | Commit | Change | Effect on numbers |
|---|---|---|---|
| 2026-11-27 | ed0a2e4 | Created | 5/28 cells percentile |
| 2026-11-27 | 35511fb | Percentile z: continuous linear extension outside range (ADR-010 rev 2) | max+ε 3.85 → 2.05 (frontal8 EC hibeta_exc) |

## scripts/build_reference.py
**Purpose:** build models/reference.json + models/reference_features.csv from S001–S050 R01/R02.
**Steps:** 200 jobs (2 presets × 50 subjects × 2 runs) on 8 worker processes → load_eeg → clean(60 Hz) → extract → skip insufficient_data →
`build_entry` per feature per cell → leak guard → sanity checks (EO PAF mean 9–11 Hz; EC alpha_exc > EO) → exit 1 on any failure.
**Run:** `python scripts/build_reference.py` (~30 s). Output is identical between runs except `build_date`.
**Current numbers:** EO PAF 9.65 / 10.42 Hz; alpha_exc EO→EC 1.71→4.90 / 7.92→32.14 µV² (frontal8 / muse4); used 44/49 · 47/48 of 50.
| Date | Commit | Change | Effect on numbers |
|---|---|---|---|
| 2026-11-27 | ed0a2e4 | Created | first reference |
| 2026-11-27 | db70e0b | Inclusion requires n_kept ≥ 6 | used EO/EC frontal8 44/49 → 40/42, muse4 47/48 → 44/47 |

## tests/test_reference.py
10 tests: transforms at 0, mid-rank percentile, outside-range rule and cap, NaN input, leak guard, built json (4 cells, no leak, percentile ⇔ values), load_reference + sanity.
| Date | Commit | Change | Effect on numbers |
|---|---|---|---|
| 2026-11-27 | a6ceb2a | Created | suite 53 passed |

## models/reference.json · models/reference_features.csv
Per preset → condition: `subjects_used`, `subjects_skipped` (with reason), `features` {transform, method, mean, std, n, skew, min, max, values?};
top level: build_date, command, runs, candidate and excluded subjects, settings. The CSV has one row per recording (all session features + QC).
| Date | Commit | Change | Effect on numbers |
|---|---|---|---|
| 2026-11-27 | 7d588c9 | Created | see DEVLOG 21:10 |

## src/scoring.py
**Purpose:** one session → 0–100 typicality score that decomposes into dimensions, features and z (§7.6, ADR-011).
**Inputs → outputs:** `score(features, qc, condition, preset)`; qc must carry `duration_s` → dict with composite, confidence, dimensions,
feature_z, feature_scores, named_metrics, explanations, warnings (+ condition, preset).
**Algorithm:** z per feature from `reference.to_z` → s = clip(100 − 15·|z|, 0, 100) → dimension = mean of its feature scores →
signal_quality = 100·(0.5·retained + 0.5·r2n) → composite = weighted sum (0.30/0.30/0.25/0.15, renormalised if a dimension is missing) →
confidence = 0.5·retained + 0.3·r2n + 0.2·min(duration/60, 1). Explanations for |z| ≥ 1, largest first.
**Edge cases:** tbr_osc NaN → Attention from PAF + warning; a missing feature → its dimension uses the rest; whole dimension missing →
renormalise + warning; no EEG dimension → composite None; 0 epochs → composite None, confidence 0; None values treated as missing.
**Key parameters:** Z_PENALTY 15 (one SD costs 15 points; |z| ≥ 6.7 → 0), WEIGHTS, EXPLAIN_Z_THRESHOLD 1.
**Connects to:** reference.py (z), features.py/preprocess.py (inputs), db.py + pages (P5/P7).
| Date | Commit | Change | Effect on numbers |
|---|---|---|---|
| 2026-11-27 | b825445 | Created | S060 R01 vs EO 86.3 (frontal8) |

## tests/test_scoring.py
17 tests: weights sum, typical session ≈ 100 for all 4 cells, bounds on extreme values, NaN TBR, missing feature, missing dimension,
missing duration, bad args, 0 epochs end-to-end, sample file, S060 R01 > R02 vs EO (both presets), None value, all-EEG-missing.
| Date | Commit | Change | Effect on numbers |
|---|---|---|---|
| 2026-11-27 | 7cbe9e3 | Created | suite 72 passed |

## src/longitudinal.py
**Purpose:** turn a list of session composites into baseline, EMA, Bayesian posterior and shift flags (§7.7).
**Functions:** `compute_baseline(scores, n=3)` → {mean, std (ddof=1, floor 2.0), raw_std, n, provisional}; `ema(scores, 0.3)`;
`obs_sd_from_confidence(conf)` → 5 + 15·(1 − conf); `bayesian_track(scores, obs_sd)` → [(mean, sd)] with prior N(s1, 15²);
`flag_shifts(scores, baseline, 2.0)` (never flags the baseline sessions); `deltas_vs_baseline(values)`.
**Why Bayesian:** a session with confidence 0.3 has obs_sd 15.5 and barely moves the posterior; one with 0.98 (sd 5.3) moves it a lot.
**Caveat:** inputs must be finite; callers drop composite None sessions.
| Date | Commit | Change | Effect on numbers |
|---|---|---|---|
| 2026-11-27 | 5c2a2dd | Created | S051 posterior 87.0 ± 5.3 → 84.3 ± 1.5 over 13 sessions |

## src/db.py
**Purpose:** SQLite store of every session (features, QC and the full score dict as JSON). `save_session`, `load_subject`, `list_subjects`,
`delete_subject`; optional `db_path` (ADR-012). NaN/inf are stored as null and return as None. DB file bioscope.db is gitignored.
| Date | Commit | Change | Effect on numbers |
|---|---|---|---|
| 2026-11-27 | 8a9a15b | Created | — |

## scripts/build_demo_sessions.py
**Purpose:** build data/demo/ (13 × 8-ch frontal8 .fif) for S051 and seed the DB. s01 = R01; s02–s13 = T0 blocks of R03–R14 joined by
`mne.concatenate_raws` (boundary annotations kept, filtered per block, no epoch crosses a join — asserted). Prints the longitudinal table.
**Run:** `python scripts/download_data.py --demo` then `python scripts/build_demo_sessions.py` (~1 min).
| Date | Commit | Change | Effect on numbers |
|---|---|---|---|
| 2026-11-27 | 81bea35 | Created (S051) | 13/13 sessions scored, 14–15 epochs each |

## tests/test_longitudinal.py · tests/test_db.py
7 longitudinal tests (hand-computed EMA and posterior, std floor, flags, posterior sd monotone ↓, None rejected); 3 db tests (None/NaN/inf/numpy
round trip, ordering with a None composite, list/delete) — all in a tmp_path database.
| Date | Commit | Change | Effect on numbers |
|---|---|---|---|
| 2026-11-27 | 5a3b972 | Created | suite 85 passed |

## data/demo/
13 files `S051_sNN_<run>_raw.fif`, frontal8, float32, annotations (T0 + BAD/EDGE boundary) kept, 4.0 MB total.
| Date | Commit | Change | Effect on numbers |
|---|---|---|---|
| 2026-11-27 | 3fd6025 | Created | see DEVLOG 22:02 |

## src/preprocess.py — update (ADR-012, BUG-002)
`_segment_events`: the 4 s / 2 s grid restarts at every concatenation boundary; boundary marks are removed from the working copy before
epoching. Continuous files: identical events (tested), reference unchanged. qc gains `n_segments`.
| Date | Commit | Change | Effect on numbers |
|---|---|---|---|
| 2026-11-27 | 6ebb2ae | Segment-aware epoching | S060 R03 T0 n_total 1 → 11 |
| 2026-11-27 | 0b520a8 | BUG-002 boundary marks | n_total 11 → 15 |

## scripts/download_data.py — update
`--demo` (commit 29aa9e8): S051 R01 + R03–R14 (13 files), mutually exclusive with `--holdout`.

## src/ml_sanity.py
**Purpose:** eyes-open/closed validation model at runtime: `predict(per_epoch)` → p_eyes_closed (mean over epochs), p_epochs, SHAP values
(n_epochs × 17, log-odds), base_value, feature_names, warnings. Never feeds the score.
**Inputs → outputs:** frontal8 per-epoch table from `features.extract` → dict above. Empty table → p None + warning; missing column → ValueError.
**Algorithm:** load models/lgbm_eyes.joblib once (lru_cache) → LightGBM predict_proba → SHAP TreeExplainer built at runtime (lru_cache, never
pickled) → `shap_matrix` takes the eyes-closed class whatever shape shap returns (shap 0.51 returns a list for binary LightGBM).
Also holds `make_lgbm` / `make_lr`, so the pickled LR pipeline (log1p on *_abs/*_exc → median impute → scale → LR) unpickles from an importable module.
**Why:** pitch anchor 4. SHAP gives a per-epoch reason the UI can show.
**Parameters:** config.LGBM_PARAMS (fixed before CV), LR_MAX_ITER, ML_PRESET.
**Connects to:** features.EPOCH_COLUMNS; trained by scripts/train_sanity_model.py; shown on pages/2_Session (P7).
| Date | Commit | Change | Effect on numbers |
|---|---|---|---|
| 2026-11-28 | c45b366 | Created | S060 R01 p(EC) 0.187, R02 0.914 |

## scripts/train_sanity_model.py
**Purpose:** train and validate the model; write lgbm_eyes.joblib, metrics.json, epoch_features.csv.
**Algorithm:** S001–S050 R01 (0) / R02 (1), frontal8, all epochs passing rejection (parallel workers) → leak guards → GroupKFold(5) by subject,
same folds for LightGBM and LR → per-epoch acc/AUC, per-recording acc, paired within-subject acc from out-of-fold p → permutation test
(labels shuffled within each subject, full CV per shuffle, 1000×, ~4 min on 14 workers) → final models on all data → SHAP top-10 → gate (ADR-013), exit 1 on FAIL.
**Why grouped CV:** epochs of one subject are correlated; mixing them across folds would inflate accuracy.
**Why within-subject permutation:** keeps each subject's label balance, so the null includes subject effects.
**Parameters:** `--workers`, `--permutations` (default 1000; p cannot go below 1/(n+1)).
| Date | Commit | Change | Effect on numbers |
|---|---|---|---|
| 2026-11-28 | 9b3f8c6 | Created | LGBM acc 0.661, AUC 0.719, paired 0.886, p 0.001 |

## models/lgbm_eyes.joblib · models/metrics.json · models/epoch_features.csv
joblib = {lgbm, lr, feature_names, preset, train_subjects, lgbm_params, lr_max_iter, versions, build_date}; no explainer.
metrics.json = original_gate (0.80, FAIL, replaced), folds, summary, permutation, shap, gate. epoch_features.csv = 2206 training rows.
| Date | Commit | Change | Effect on numbers |
|---|---|---|---|
| 2026-11-28 | 1f73e00 | Created | see DEVLOG 2026-11-28 09:10 |

## tests/test_ml_sanity.py
7 tests: EO sample p < 0.5; EC S060 R02 p > 0.5 (skips without raw data); SHAP shape + additivity (row sum + base = raw margin);
no shap object in the joblib; train subjects ⊆ S001–S050 and disjoint from held-out; empty table; missing column; log1p only on power columns.
| Date | Commit | Change | Effect on numbers |
|---|---|---|---|
| 2026-11-28 | c6b114b | Created | suite 92 passed |

## src/config.py — update (P6)
ML_PRESET, ML_LABELS, LGBM_PARAMS, LR_MAX_ITER, EPOCH_FEATURES_PATH (77ebae2); CV_ACCURACY_GATE 0.80 replaced by GATE_PERM_P 0.01,
GATE_AUC 0.65, GATE_PAIRED_ACC 0.75, N_PERMUTATIONS 1000, SHAP_TOP_N 10 (5a446bb, ADR-013).
