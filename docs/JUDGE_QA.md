# Likely judge questions

Short answers, backed by our own numbers. Target ≥ 25 by P8.

## Science
**Q: Why FOOOF?**
A: An EEG spectrum = 1/f background + rhythms. Classic band power mixes both, so a background tilt looks like a rhythm change.
FOOOF fits the background separately; we then measure power *above* it. In our synthetic test a pure slope change moved classic TBR by
|Δlog| 0.16–0.58 and our TBR by 0.01–0.03 (ADR-008).

**Q: Why are there two TBRs?**
A: `tbr_classic` = theta/beta power (what most papers report) and `tbr_osc` = theta/beta *rhythm power above 1/f* (what we score).
We show both so you can see how much of the classic value is background. S060 eyes-open: classic 0.66, rhythm-based 0.68.

**Q: Didn't you plan a "mean PSD/aperiodic" ratio?**
A: Yes, and we tested it: it moved *more* than classic power under a pure slope change (1.04 vs 0.16 for TBR), so we replaced it (ADR-008).

**Q: Why is frontal alpha often missing with eyes open?**
A: Alpha is strongest over the back of the head and is suppressed when the eyes are open. In our reference subset 74% of frontal channels
had no FOOOF alpha peak with eyes open versus 23% with eyes closed (muse4: 55% vs 17%). When no peak is found we use the spectral centre
of gravity (7–13 Hz) and show the fallback share beside PAF. EO PAF still averages 9.88 Hz.

**Q: How did you choose the PAF window?**
A: 7–14 Hz picked up frontal theta peaks at ~7 Hz (2/10 eyes-open recordings below 8 Hz). 8–13 Hz (the alpha band) fixed it: 0/10, mean 9.88 Hz (ADR-009).

## Methodology
**Q: Why PhysioNet EEGMMI?**
A: Public (ODC-By), 109 subjects, standard 10-10 montage with all 8 frontal sites and Muse-like sites, and separate eyes-open (R01) and
eyes-closed (R02) resting runs, giving two condition-matched references. 114 files used: 100 reference (S001–S050) + 14 held-out demo (S060).

**Q: How do you avoid scoring the demo subject against itself?**
A: Fixed subject split (ADR-002). S060 is never in the reference or the ML training data; scripts assert this.

**Q: How do you support both 4- and 8-channel headsets?**
A: Channel presets in one config: `frontal8` (Fp1 Fp2 AF3 AF4 F3 F4 F7 F8) and `muse4` (AF7 AF8 TP7 TP8, a Muse-like approximation).
The loader normalises labels and keeps only the preset's channels in a fixed order; a missing channel gives a clear error listing what is available.
On S060 R01 both presets load the full 61.0 s: (8, 9760) and (4, 9760) samples at 160 Hz.

**Q: There is no EOG channel — how do you remove blinks?**
A: ICA, using the channels closest to the eyes as blink references (Fp1/Fp2 for 8-ch, AF7/AF8 for 4-ch). A component is removed if its
time course correlates |r| ≥ 0.7 with those channels (at most 2 for 8-ch, 1 for 4-ch). Then 4 s epochs over 200 µV peak-to-peak are dropped.
On 20 reference recordings this keeps a median 97% of epochs (eyes open 79%, eyes closed 100%); without working ICA it was 12%.

**Q: Why correlation and not MNE's default z-score rule?**
A: With 8 channels ICA yields 7 components, and the largest z-score 7 numbers can produce is √6 ≈ 2.45, so the default z ≥ 3 never triggers.
We measured it: 0 components removed in 20/20 files (ADR-005).

**Q: What is the score compared against?**
A: People recorded the same way: 50 public-dataset adults, same channel preset, same condition (eyes open or closed) — 4 separate references.
frontal8 eyes-open uses 44 recordings, eyes-closed 49; muse4 47 and 48. Recordings with no clean epochs are skipped and listed.

**Q: Your features are skewed — isn't a z-score wrong?**
A: We measured it. Power features are log-transformed first (ln(1+x), since some are exactly 0); hibeta_exc skew 6.30 → 1.43.
Any feature still skewed past |1| (5 of 28) is ranked against the reference instead (percentile → z), capped at |z| = 4 (ADR-010).

**Q: What does a score of 72 mean?**
A: That the recording is moderately typical of people recorded the same way. Each feature loses 15 points per standard deviation from the
reference, dimensions average their features, and the composite weights them 0.30/0.30/0.25/0.15. S060's own eyes-open run scores 86.3
against the eyes-open reference; its eyes-closed run scores 84.1 against eyes-open but 89.4 against eyes-closed. It is not a health grade.

**Q: Why not train on "healthy vs unhealthy" labels?**
A: The public resting data has no such labels, and inventing them would be fake. Typicality against a matched reference is what the data supports.

**Q: Why doesn't the composite separate eyes open/closed strongly?**
A: Because it is not built to. The score asks "how typical is this recording of people recorded the same way", not "were the eyes open".
Most features (TBR, PAF, FAA, 1/f slope) are similar in both conditions, so they stay typical either way; the contrast lives in alpha.
On S060 the composite moves only 0.5–2.2 points, but Relaxation drops to 64.3 and the explanation reads "Alpha power above background is
4.1 SD above the eyes-open reference" when the eyes-closed run is scored against the eyes-open reference. We did not tune weights to
exaggerate this. Telling the conditions apart is the job of the separate pipeline-validation model (P6).

**Q: Your eyes-open run scores higher against the eyes-closed reference. Isn't that a bug?**
A: No. We checked: S060 has unusually strong eyes-open alpha (z 1.38 vs the eyes-open reference, 0.28 vs eyes-closed), and the eyes-open
reference is wider for 4 of 7 features. Typicality versus a reference is not condition detection; the app always uses the condition the
user declares, and the session page names the reference used (P7).

**Q: Is the trend real multi-day change?**
A: No. The 13 demo sessions are sequential rest blocks from one visit of one public-dataset subject (S051): its eyes-open rest run, then the
rest blocks between motor tasks in each of 12 later runs. They demonstrate the tracker mechanics — baseline 84.2 ± 2.5 from sessions 1–3, EMA,
Bayesian posterior narrowing from ± 5.3 to ± 1.5 — not change over days. No session crosses the 2 SD flag (largest 1.74 SD).

**Q: Why S051, not S060?**
A: S060 is still our held-out test subject, but its between-task rest blocks were 1.5–2× the amplitude of its true rest run, so only 0–5 of 15
epochs per session passed artefact rejection (confidence 0.25–0.43, 5 sessions unscorable). Our confidence score caught that. We did not
loosen the rejection threshold; we screened S051–S059 (never in the reference or holdout) with a rule fixed in advance — most runs with
≥ 6 clean epochs, tie broken by confidence — and S051 kept 14–15 of 15 epochs in all 12 runs.

## Limitations
**Q: Why is 4-channel less reliable?**
A: (1) Blink removal is coarser: 3 ICA components instead of 7, and the blink reference (AF7/AF8) is half of the montage, so one component
is removed in every recording — it may also contain some real frontal activity (we check that eyes-closed alpha still exceeds eyes-open).
(2) Asymmetry uses 2 channels per side instead of 4. (3) TP7/TP8 sit over temporal muscle. Retention is high after ICA (median 100%),
but the 8-channel result is the primary one; muse4 is the Muse-like approximation (real Muse uses TP9/TP10).

## ML
**Q: Why only 66% accuracy?**
A: Our honest result on unseen subjects: per-epoch accuracy 0.661 ± 0.033, ROC-AUC 0.72, from 4 s frontal-only epochs. Three reasons:
(1) the eyes-closed alpha increase is mainly posterior; frontally, alpha power rose in only 25 of 44 subjects. (2) Subjects differ more from each
other than eyes-open differs from eyes-closed within one subject. (3) An exploratory check on posterior channels reached only 0.70–0.76, so
this data has a ceiling. Within each subject the model ranks the eyes-closed run above the eyes-open run for 89% (39/44), and a 1000-shuffle
permutation test gives p = 0.001. We set an 80% target before seeing data, missed it, and say so (ADR-013).

**Q: Show me the confusion matrix.**
A: Per 4 s epoch, threshold 0.5, eyes-closed = positive (figure: docs/figures/confusion_matrix.png). Cross-validation, LightGBM: TN 650,
FP 373, FN 374, TP 809 — precision 0.68, recall 0.68, specificity 0.64, balanced accuracy 0.66. Holdout (49 unseen subjects): TN 579, FP 317,
FN 409, TP 714 — balanced accuracy 0.64; LR 0.65. Errors are balanced between the classes, so neither condition is systematically missed.
Honest caveat: LightGBM's probabilities are overconfident (log-loss 0.84 on the holdout vs 0.69 for predicting the class prior), so we use it
for ranking and SHAP explanation, not as a calibrated probability; the logistic baseline is better calibrated (log-loss 0.66).

**Q: Why use ML if it doesn't decide the score?**
A: To test the features. If epoch-level features separate eyes-open from eyes-closed on subjects the model never saw, the pipeline carries
real physiological signal. The score stays transparent (z vs reference); the model is a check, shown with SHAP.

**Q: How did you avoid leakage?**
A: GroupKFold by subject (no subject in train and test), hyper-parameters fixed before CV, and held-out subjects (S051, S060, S061–S109)
are refused in code. The permutation test re-trains on every shuffle, so the null includes the whole procedure.

**Q: Which features does the model use?**
A: SHAP top: high-beta power, sample entropy, alpha oscillation ratio. Alpha is third, not first: with eyes closed there is also less eye
movement and muscle activity at frontal sites, which lowers high beta and entropy. Both are real EO/EC effects; we report this rather than claim alpha leads.

## Validation
**Q: How do you know it generalises?**
A: We kept 49 subjects (S061–S109) completely untouched — not in the reference, not in training. On them, with no refitting, the eyes-open/closed
check gives ROC-AUC 0.68 (95% CI 0.63–0.74, LR 0.71), ranks the eyes-closed run above the eyes-open run for 83% of subjects (35/42), and a
permutation test gives p = 0.001 — close to cross-validation (AUC 0.72, 89%). The pipeline processed 98/98 unseen files with zero crashes.

**Q: Does the score drop when someone closes their eyes?**
A: Only a little. On the 49 unseen subjects, eyes-closed recordings scored against the eyes-open reference have median 83.6 vs 84.9 for
eyes-open — because the score measures typicality and most features stay within about 1 SD. That is why the reference is condition-matched:
we compare like with like rather than expect the score to detect the condition.

## Product
*(P7)*
