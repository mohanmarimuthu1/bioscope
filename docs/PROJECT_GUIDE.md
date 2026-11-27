# Project guide — everything I need to know

Updated each phase. Sections fill in as the build progresses.

## 1. The problem
Zenix Bio Hackathon 01, Round 2, Problem Statement 3: a point-in-time brain-activity score from 4- or 8-channel frontal EEG,
with longitudinal tracking. BioScope gives one 0–100 *typicality* score versus a condition-matched reference built from public data,
decomposed into dimensions → features → z-scores → signal, plus a tracker across sessions.

## 2. EEG basics needed
*(P3)*

## 3. End-to-end walkthrough of one real recording
*(P4, with real numbers at every stage)*

## 4. Each file's role
| File | Role |
|---|---|
| src/config.py | Every constant, with its source |
| scripts/download_data.py | Fetches the 114 PhysioNet files |
| src/io_utils.py | Opens EDF/FIF, fixes channel names, keeps only the preset's channels |
| data/sample/sample_frontal8_raw.fif | 61 s real recording for tests/demo without downloading |

## 5. How the algorithm evolved
- P0: Welch segment kept at 2 s (0.5 Hz bins) rather than 4 s, for lower-variance spectra (ADR-003).
- P1: recordings are 61.0 s (9,760 samples), not the assumed 60 s; all checks now read the length from the file itself.

## 6. Current results
*(P4 onward)*

## 7. Limitations
- Reference = 50 healthy US adults from one public dataset; typicality is relative to them only.
- Research prototype, not a diagnostic device.

## 8. Glossary
| Term | Meaning |
|---|---|
| EO / EC | Eyes open / eyes closed resting recording (R01 / R02) |
| Epoch | A 4 s slice of signal analysed on its own |
| PSD | Power spectral density: how much power is at each frequency |
| Welch | PSD method that averages spectra of overlapping segments to reduce noise |
| FOOOF | "Fitting oscillations & one over f": splits a spectrum into a 1/f background plus peaks |
