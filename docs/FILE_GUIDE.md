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

## data/sample/sample_frontal8_raw.fif
**Purpose:** a committed, real recording for tests and the README demo when raw data is not downloaded.
**What it is:** S060 R01 (eyes open), frontal8, full 61 s (9760 samples, 160 Hz), float32, 314,808 bytes, annotations kept.
Full length, not 20 s: 61 s gives ~29 epochs and full duration credit in the confidence formula (`min(61/60, 1) = 1`); 20 s would cap it at 0.33.
| Date | Commit | Change | Effect on numbers |
|---|---|---|---|
| 2026-11-27 | d7bba16 | Created | — |
