# BioScope EEG — Methodology

*Judge-facing science. Full version in P8; sections are filled as the pipeline is built.*

## Reference and score
- **Reference:** S001–S050 of PhysioNet EEGMMI, eyes-open (R01) and eyes-closed (R02), built separately for each channel preset.
  A recording is included only with ≥ 6 clean 4 s epochs: frontal8 40 eyes-open / 42 eyes-closed, muse4 44 / 47 (ADR-010).
- **Transforms:** ln(1+x) for theta/beta ratio, alpha and high-beta excess power (they can be 0); ln for classic TBR.
  If a feature is still skewed (|skew| > 1), its z comes from its rank in the reference: z = Φ⁻¹(rank/(n+1)), extended linearly past the
  reference range and capped at |z| = 4.
- **Score:** feature s = clip(100 − 15·|z|, 0, 100); Attention (TBR, PAF), Relaxation (alpha, FAA), Load (high beta, 1/f slope) average their
  features; Signal quality = 100·(0.5·retained + 0.5·fit quality). Composite = 0.30·A + 0.30·R + 0.25·L + 0.15·SQ (weights: design choice).
- **Confidence** = 0.5·retained + 0.3·fit quality + 0.2·min(duration/60 s, 1).
- **Held-out check (S060):** eyes-open run vs eyes-open reference 86.3; eyes-closed run 84.1 vs eyes-open and 89.4 vs eyes-closed (frontal8).

## Limitations
- **Frontal alpha with eyes open is often absent.** Alpha is suppressed with eyes open and weakest frontally. In the reference subset
  (S001–S010), 74% of frontal channels had no FOOOF alpha peak with eyes open versus 23% with eyes closed (muse4 approximation: 55% vs 17%).
  PAF then comes from the spectral centre of gravity over 7–13 Hz, which is less precise; the UI shows the fallback share beside PAF.
- **Eyes-open frontal reference is the thinnest.** A recording joins the reference only with ≥ 6 clean 4 s epochs. Frontal
  eyes-open recordings are the most blink-contaminated, so 10 of 50 frontal8 eyes-open recordings are excluded (20%; 12% before the
  ≥ 6-epoch rule) versus 8/50 eyes-closed; muse4 excludes 6/50 and 3/50. The excluded people may be systematically blinkier, so the
  eyes-open reference may under-represent them (accepted, ADR-010).
- **The composite separates conditions weakly.** On S060 the eyes-open/eyes-closed difference is 0.5–2.2 composite points; it is carried
  by alpha power (z 3.3–4.1), while the other features are near-typical in both runs and averaging dilutes it.
- **Typicality is not condition detection.** A person with strong eyes-open alpha can look more typical of the eyes-closed reference:
  S060's eyes-open run scores 88.9 vs eyes-closed and 86.3 vs eyes-open (frontal8), driven by alpha (z 0.28 vs 1.38). The eyes-open
  reference is also wider for 4 of 7 features (1/f slope ×1.50, PAF ×1.30, high beta ×1.23, classic TBR ×1.34), so eyes-open deviations
  cost fewer points. The UI must always state which reference was used.
- **Between-task rest is noisier than true rest.** In S060, rest blocks inside the motor runs were 1.5–2× the amplitude of its
  dedicated rest run on every channel; only 0–5 of 15 epochs passed rejection and confidence fell to 0.25–0.43. The confidence score caught
  it; we did not loosen the threshold. The longitudinal demo uses S051 instead (12/12 runs clean, screened from S051–S059 by a fixed rule).
- **The longitudinal demo is one visit.** Its 13 sessions are sequential rest blocks from a single recording session: they demonstrate the
  tracker (baseline, EMA, Bayesian posterior, flags), not multi-day change. With S051 no session is flagged (largest deviation 1.74 SD).
- **4-channel (muse4) is an approximation** of a Muse headset (TP7/TP8 instead of TP9/TP10) and uses a coarser 3-component ICA.
- **Typicality, not health.** Scores compare a recording with 50 healthy adults from one public dataset (PhysioNet EEGMMI).
- Research prototype, not a diagnostic device.
