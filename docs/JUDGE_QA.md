# Likely judge questions

Short answers, backed by our own numbers. Target ≥ 25 by P8.

## Science
*(P3)*

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

## Limitations
**Q: Why is 4-channel less reliable?**
A: (1) Blink removal is coarser: 3 ICA components instead of 7, and the blink reference (AF7/AF8) is half of the montage, so one component
is removed in every recording — it may also contain some real frontal activity (we check that eyes-closed alpha still exceeds eyes-open).
(2) Asymmetry uses 2 channels per side instead of 4. (3) TP7/TP8 sit over temporal muscle. Retention is high after ICA (median 100%),
but the 8-channel result is the primary one; muse4 is the Muse-like approximation (real Muse uses TP9/TP10).

## ML
*(P6)*

## Validation
*(P4–P6)*

## Product
*(P7)*
