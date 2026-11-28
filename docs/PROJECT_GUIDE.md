# Project guide — everything I need to know

Updated each phase. Sections fill in as the build progresses.

## 1. The problem
Zenix Bio Hackathon 01, Round 2, Problem Statement 3: a point-in-time brain-activity score from 4- or 8-channel frontal EEG,
with longitudinal tracking. BioScope gives one 0–100 *typicality* score versus a condition-matched reference built from public data,
decomposed into dimensions → features → z-scores → signal, plus a tracker across sessions.

## 2. EEG basics needed
- **EEG** measures tiny voltages (µV) on the scalp from many neurons firing together. Frontal sites (Fp, AF, F) sit near the eyes, so blinks are huge there.
- **Rhythms** are named by frequency: theta 4–8 Hz, alpha 8–13 Hz (strongest with eyes closed), beta 13–30 Hz, high beta 20–30 Hz.
- **Spectrum (PSD):** how much power at each frequency. Plotted on log-log axes it is roughly a straight falling line (the **1/f background**) with bumps (the **rhythms**).
- **FOOOF** fits that line (offset = height, exponent = steepness) and the bumps (centre frequency, height, width) separately.
- **Why it matters:** if the line tilts (age, arousal, reference), classic band power changes even when no rhythm changed. Power *above the line* ("excess") measures the rhythm itself (ADR-008).
- **PAF** = frequency of the alpha bump (~10 Hz in adults). **TBR** = theta/beta. **FAA** = right vs left frontal alpha.
- Eyes open often shows *no* frontal alpha bump (74% of frontal channels in our data) — eyes closed brings it back (23%).

## 3. End-to-end walkthrough of one real recording
*(P4, with real numbers at every stage)*

## 4. Each file's role
| File | Role |
|---|---|
| src/config.py | Every constant, with its source |
| scripts/download_data.py | Fetches the 114 PhysioNet files |
| src/io_utils.py | Opens EDF/FIF, fixes channel names, keeps only the preset's channels |
| data/sample/sample_frontal8_raw.fif | 61 s real recording for tests/demo without downloading |
| src/preprocess.py | Filters, removes blinks with ICA, cuts 4 s epochs, drops noisy ones |
| src/features.py | Spectrum → FOOOF → PAF, band powers (abs/excess/ratio), TBR, FAA, entropy |
| scripts/train_sanity_model.py | Trains the eyes-open/closed check with subject-held-out CV + permutation test |
| src/ml_sanity.py | Runs that check on one recording and explains it with SHAP (never feeds the score) |

## 5. How the algorithm evolved
- P0: Welch segment kept at 2 s (0.5 Hz bins) rather than 4 s, for lower-variance spectra (ADR-003).
- P1: recordings are 61.0 s (9,760 samples), not the assumed 60 s; all checks now read the length from the file itself.
- P2: blinks dominated frontal eyes-open data (Fp1 p2p ≈ 330 µV). The specified ICA rule (z ≥ 3) could never fire with 7 components
  (max z ≈ 2.45), so nothing was removed and only 12% of epochs survived. Switching to correlation |r| ≥ 0.7 with the frontopolar
  channels and a 200 µV threshold raised retention to 97% (ADR-005). muse4 got a 3-component ICA: 57% → 100% (ADR-006).
- P3: (1) PAF search 7–14 Hz picked frontal theta (7.1 Hz) → 8–13 Hz: eyes-open PAF mean 9.20 → 9.88 Hz (ADR-009).
  (2) The specified "oscillatory ratio" moved *more* than classic power when only the 1/f slope changed → switched TBR, alpha and high beta
  to excess power above the line: slope sensitivity of TBR 0.68–1.04 → 0.01–0.03 (ADR-008).

- P4a: the reference is split by preset as well as condition (muse4 alpha_exc is 4.6× frontal8 eyes-open, 6.6× eyes-closed). ln(tbr_osc) hit −inf on 6 recordings with
  no theta rhythm → ln(1+x). Features still skewed after transform use a percentile z (ADR-010). The first out-of-range rule jumped
  2.05 → 3.85 at the reference max → replaced by a continuous extension. Reference recordings now need ≥ 6 clean epochs.
- P4b: score() needs the preset too (ADR-011). Review caught a composite of 100 built from signal quality alone → now None.
- P5: concatenated rest blocks gave 1 epoch per session (one epoch grid across joins) → grid restarts per block (ADR-012); boundary marks
  then still dropped 4/15 epochs (BUG-002). S060's between-task rest was too noisy (0–5/15 epochs kept) → demo subject S051, chosen by a
  fixed screening rule.
- P6: the 80% accuracy gate for the eyes-open/closed check (set before any data) failed: 0.661 on frontal-only epochs. No bug — frontal
  alpha barely changes with eyes closed and subjects differ a lot. Gate replaced openly by a significance gate (ADR-013): AUC 0.72,
  89% of subjects ranked correctly, permutation p 0.001 → PASS.
- P6b: on 49 untouched subjects the check held (AUC 0.68, paired 83%, p 0.001), slightly below CV as expected.

## 6. Current results
- Reference (P4a): EO PAF mean 9.65 Hz (frontal8) / 10.42 Hz (muse4); eyes-closed alpha_exc 2.9× / 4.1× eyes-open. 12 of 200 recordings
  skipped for 0 clean epochs at first; with the ≥ 6-epoch rule 27 of 200 (frontal8 eyes-open 10/50).
- Score (P4b), held-out S060, frontal8: eyes-open run vs eyes-open reference 86.3 (confidence 0.93); eyes-closed run 84.1 vs eyes-open,
  89.4 vs eyes-closed. muse4: 84.2 / 83.7 / 86.5. Full breakdown in DEVLOG 2026-11-27 21:26.
- Longitudinal demo (P5), S051, 13 sessions: composites 79.8–87.0, confidence 0.87–0.99, baseline 84.2 ± 2.5, posterior 84.3 ± 1.5,
  no flags (max 1.74 SD).
- ML check (P6), frontal8, subject-held-out: accuracy 0.661 ± 0.033, AUC 0.719, recording accuracy 0.70, paired 0.886 (39/44),
  permutation p 0.001; LR baseline 0.671 / 0.740. SHAP top 3: hibeta_abs, samp_entropy, alpha_osc.
- Holdout (P6b), 49 unseen subjects, no refit: AUC 0.684 [0.626, 0.744], paired 0.833 (35/42), p 0.001; 98/98 files, 0 crashes.
  Composite medians: EO/EO 84.9, EC/EC 85.1, EC vs EO ref 83.6 — the score separates conditions only weakly.

## 7. Limitations
- Reference = 50 healthy US adults from one public dataset; typicality is relative to them only.
- Frontal-only EEG limits per-epoch eyes-open/closed accuracy (0.66); the check is significant, not highly accurate.
- Research prototype, not a diagnostic device.

## 8. Glossary
| Term | Meaning |
|---|---|
| EO / EC | Eyes open / eyes closed resting recording (R01 / R02) |
| Epoch | A 4 s slice of signal analysed on its own |
| PSD | Power spectral density: how much power is at each frequency |
| Welch | PSD method that averages spectra of overlapping segments to reduce noise |
| FOOOF | "Fitting oscillations & one over f": splits a spectrum into a 1/f background plus peaks |
