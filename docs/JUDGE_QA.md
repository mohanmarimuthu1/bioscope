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

## ML
*(P6)*

## Validation
*(P4–P6)*

## Limitations
*(P8)*

## Product
*(P7)*
