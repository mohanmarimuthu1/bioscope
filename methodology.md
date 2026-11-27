# BioScope EEG — Methodology

*Judge-facing science. Full version in P8; sections are filled as the pipeline is built.*

## Limitations
- **Frontal alpha with eyes open is often absent.** Alpha is suppressed with eyes open and weakest frontally. In the reference subset
  (S001–S010), 74% of frontal channels had no FOOOF alpha peak with eyes open versus 23% with eyes closed (muse4 approximation: 55% vs 17%).
  PAF then comes from the spectral centre of gravity over 7–13 Hz, which is less precise; the UI shows the fallback share beside PAF.
- **Eyes-open frontal reference is the thinnest.** A recording joins the reference only with ≥ 6 clean 4 s epochs. Frontal
  eyes-open recordings are the most blink-contaminated, so 10 of 50 frontal8 eyes-open recordings are excluded (20%; 12% before the
  ≥ 6-epoch rule) versus 8/50 eyes-closed; muse4 excludes 6/50 and 3/50. The excluded people may be systematically blinkier, so the
  eyes-open reference may under-represent them (accepted, ADR-010).
- **4-channel (muse4) is an approximation** of a Muse headset (TP7/TP8 instead of TP9/TP10) and uses a coarser 3-component ICA.
- **Typicality, not health.** Scores compare a recording with 50 healthy adults from one public dataset (PhysioNet EEGMMI).
- Research prototype, not a diagnostic device.
