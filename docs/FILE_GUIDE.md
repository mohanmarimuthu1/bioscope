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
