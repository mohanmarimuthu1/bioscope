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
