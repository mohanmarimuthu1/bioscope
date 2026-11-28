"""Central configuration for BioScope EEG.

WHAT:  Every constant used by the pipeline: paths, dataset split, channel presets,
       preprocessing, spectral, scoring and longitudinal parameters.
WHY:   One place to read, audit and tune. No module hard-codes a number.
CAVEATS: Values marked "design choice" are not taken from literature; they are
       ours and are stress-tested (weights) in scripts/sensitivity_analysis.py.
"""
from pathlib import Path

# --------------------------------------------------------------------------- paths
ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"          # PhysioNet downloads (gitignored)
DATA_SAMPLE = ROOT / "data" / "sample"    # small committed file for tests/README
DATA_DEMO = ROOT / "data" / "demo"        # 13 committed demo sessions (.fif)
MODELS_DIR = ROOT / "models"
REFERENCE_PATH = MODELS_DIR / "reference.json"
MODEL_PATH = MODELS_DIR / "lgbm_eyes.joblib"
METRICS_PATH = MODELS_DIR / "metrics.json"
DB_PATH = ROOT / "bioscope.db"            # SQLite store (gitignored via *.db)
DOCS_DIR = ROOT / "docs"

# --------------------------------------------------------------------------- dataset
# PhysioNet EEG Motor Movement/Imagery v1.0.0 (ODC-By). 64 ch, 160 Hz, EDF.
PHYSIONET_BASE_URL = "https://physionet.org/files/eegmmidb/1.0.0"
DATASET_SFREQ = 160.0                     # source: dataset description
DATASET_LINE_FREQ = 60.0                  # source: recorded in the US (60 Hz mains)
REFERENCE_SUBJECTS = [f"S{i:03d}" for i in range(1, 51)]   # ADR-002
REFERENCE_RUNS = {"eyes_open": "R01", "eyes_closed": "R02"}  # source: dataset description
DEMO_SUBJECT = "S060"                     # ADR-002: held out from reference and ML
HOLDOUT_SUBJECTS = [f"S{i:03d}" for i in range(61, 110)]   # P6b external test: S061–S109, never trained on
DEMO_LONGITUDINAL_SUBJECT = "S051"        # ADR-012 addendum: screened S051–S059; 12/12 T0 runs with ≥ 6 clean epochs
# Guard: the demo subjects are never reference/ML subjects or holdout subjects (ADR-002, ADR-012).
for _s in (DEMO_SUBJECT, DEMO_LONGITUDINAL_SUBJECT):
    if _s in REFERENCE_SUBJECTS or _s in HOLDOUT_SUBJECTS:
        raise ValueError(f"Demo subject {_s} overlaps the reference or holdout set")
DEMO_RUNS = [f"R{i:02d}" for i in range(1, 15)]            # R01–R14
DEMO_REST_LABEL = "T0"                    # source: dataset annotations (rest blocks)
CONDITIONS = ("eyes_open", "eyes_closed")

# --------------------------------------------------------------------------- channel presets
# CLAUDE.md §7.3. faa_left/faa_right are the hemispheric groups for FAA.
PRESETS = {
    "frontal8": {
        "channels": ["Fp1", "Fp2", "AF3", "AF4", "F3", "F4", "F7", "F8"],
        "faa_left": ["Fp1", "AF3", "F3", "F7"],
        "faa_right": ["Fp2", "AF4", "F4", "F8"],
        # ICA: n_ch−1 = 7 comps; Fp1/Fp2 are EOG proxies (no EOG channel in EEGMMI)
        "ica": {"eog_proxy": ["Fp1", "Fp2"], "max_exclude": 2},
    },
    "muse4": {  # Muse-like approximation; real Muse uses TP9/TP10
        "channels": ["AF7", "AF8", "TP7", "TP8"],
        "faa_left": ["AF7", "TP7"],
        "faa_right": ["AF8", "TP8"],
        # ICA: n_ch−1 = 3 comps; AF7/AF8 = frontmost sites (ADR-006 trial)
        "ica": {"eog_proxy": ["AF7", "AF8"], "max_exclude": 1},
    },
}

# --------------------------------------------------------------------------- preprocessing
L_FREQ = 1.0                              # Hz, band-pass low edge (design choice, removes drift)
H_FREQ = 45.0                             # Hz, band-pass high edge (design choice, below mains)
NOTCH_ONLY_IF_BELOW = 45.0                # apply notch only if line_freq < this (else low-pass covers it)
ICA_METHOD = "fastica"
ICA_EOG_MEASURE = "correlation"           # ADR-005: z>=3 is unreachable with 7 comps (max z = sqrt(6) ≈ 2.45)
ICA_EOG_THRESHOLD = 0.7                   # ADR-005: |r| with the EOG proxies; audit-chosen (S001–S010)
# Per-preset ICA settings (EOG proxies, max components removed) live in PRESETS[...]["ica"].
RANDOM_STATE = 42                         # fixed seed everywhere (CLAUDE.md §13)
EPOCH_LENGTH_S = 4.0                      # design choice: 4 s windows
EPOCH_OVERLAP_S = 2.0                     # 50% overlap
REJECT_PTP_V = 200e-6                     # 200 µV peak-to-peak, in volts (ADR-005; was 150 µV)
MIN_RETAINED_FRAC = 0.5                   # below this: warn + lower confidence
MIN_EPOCHS = 6                            # below this: warn + lower confidence

# --------------------------------------------------------------------------- spectral
WELCH_N_PER_SEG_S = 2.0                   # 2 s segments -> 0.5 Hz bins (ADR-003)
WELCH_OVERLAP_FRAC = 0.5                  # 1 s overlap -> 3 segments per 4 s epoch (ADR-003)
FOOOF_MIN_R2 = 0.5                        # design choice: below this a channel's FOOOF fit is treated as failed
PSD_FMIN = 1.0
PSD_FMAX = 40.0
FOOOF_SETTINGS = {
    "peak_width_limits": [1.0, 8.0],
    "max_n_peaks": 6,
    "min_peak_height": 0.1,
    "aperiodic_mode": "fixed",            # no knee; adequate for 1–40 Hz scalp EEG (design choice)
}
FOOOF_FREQ_RANGE = [1.0, 40.0]
PAF_PEAK_RANGE = (8.0, 13.0)              # ADR-009: 7–14 caught frontal theta at ~7 Hz; = alpha band
PAF_COG_RANGE = (7.0, 13.0)               # centre-of-gravity fallback window
BANDS = {                                 # Hz, half-open [lo, hi)
    "theta": (4.0, 8.0),
    "alpha": (8.0, 13.0),
    "beta": (13.0, 30.0),
    "hibeta": (20.0, 30.0),
}
V2_TO_UV2 = 1e12                          # V^2/Hz -> µV^2/Hz
TBR_MIN_BETA_EXC_FRAC = 0.05              # ADR-008: beta_exc < 5% of beta_abs -> no beta rhythm, tbr_osc = NaN

# --------------------------------------------------------------------------- reference (ADR-010)
# Features with a reference distribution, and the transform applied before mean/std/rank.
# ln1p: power/ratio features that can be exactly 0 (no rhythm above 1/f); ln: never 0.
REFERENCE_TRANSFORMS = {
    "tbr_osc": "ln1p",
    "tbr_classic": "ln",
    "paf": "none",
    "alpha_exc": "ln1p",
    "faa": "none",
    "hibeta_exc": "ln1p",
    "ap_exponent": "none",
}
SKEW_PERCENTILE_THRESHOLD = 1.0           # ADR-010 (owner): |skew| > 1 after transform -> percentile z
PERCENTILE_Z_CAP = 4.0                    # ADR-010 (owner): |z| cap for percentile-method features
REFERENCE_FEATURES_PATH = MODELS_DIR / "reference_features.csv"   # per-recording features behind the reference

# --------------------------------------------------------------------------- scoring
Z_PENALTY = 15.0                          # s = clip(100 - 15*|z|, 0, 100) (design choice)
DIMENSIONS = {                            # feature lists per dimension (CLAUDE.md §7.6)
    "attention": ["tbr_osc", "paf"],
    "relaxation": ["alpha_exc", "faa"],      # ADR-008: excess power, robust to 1/f slope
    "load": ["hibeta_exc", "ap_exponent"],   # ADR-008
}
WEIGHTS = {                               # design choice; tested in sensitivity analysis
    "attention": 0.30,
    "relaxation": 0.30,
    "load": 0.25,
    "signal_quality": 0.15,
}
R2_FLOOR = 0.8                            # r2n = clip((r2 - 0.8)/0.2, 0, 1)
R2_SPAN = 0.2
CONF_W_RETAINED = 0.5                     # confidence weights (design choice)
CONF_W_R2 = 0.3
CONF_W_DURATION = 0.2
CONF_FULL_DURATION_S = 60.0               # recordings >= 60 s get full duration credit
EXPLAIN_Z_THRESHOLD = 1.0                 # explain features with |z| >= 1 (design choice)

# --------------------------------------------------------------------------- longitudinal
BASELINE_N = 3                            # first 3 sessions
BASELINE_STD_FLOOR = 2.0                  # avoids divide-by-tiny-std flags
EMA_ALPHA = 0.3
PRIOR_SD = 15.0                           # prior N(first score, 15^2)
OBS_SD_BASE = 5.0                         # obs_sd = 5 + 15*(1 - confidence)
OBS_SD_SCALE = 15.0
FLAG_Z = 2.0                              # flag if |score - mean| / std > 2

# --------------------------------------------------------------------------- ML validation
CV_FOLDS = 5                              # GroupKFold by subject
# ADR-013: the original gate (LightGBM CV accuracy >= 0.80) was set before any evidence; it failed (0.661 ± 0.033,
# AUC 0.72) and was replaced AFTER seeing that result by the significance gate below (owner decision).
GATE_PERM_P = 0.01                        # ADR-013: within-subject label permutation p-value for per-epoch AUC
GATE_AUC = 0.65                           # ADR-013: mean subject-held-out per-epoch ROC-AUC must exceed this
GATE_PAIRED_ACC = 0.75                    # ADR-013: share of subjects with mean p(EC) on R02 > R01 (out-of-fold)
N_PERMUTATIONS = 1000                     # ADR-013: permutations for the gate's p-value (min p = 1/1001)
SHAP_TOP_N = 10                           # ADR-013: features reported by mean |SHAP|
HOLDOUT_PATH = MODELS_DIR / "holdout.json"                     # P6b external test results (S061–S109)
HOLDOUT_FEATURES_PATH = MODELS_DIR / "holdout_features.csv"    # one row per holdout recording, for traceability
N_BOOTSTRAP = 1000                        # design choice: subject-level bootstrap resamples for holdout 95% CIs
ML_PRESET = "frontal8"                    # design choice: the demo/UI preset; muse4 ML is stretch
ML_LABELS = {"eyes_open": 0, "eyes_closed": 1}   # R01 -> 0, R02 -> 1 (CLAUDE.md §7.8)
LGBM_PARAMS = {                           # design choice: fixed before CV, never tuned on CV folds
    "n_estimators": 200,
    "learning_rate": 0.05,
    "num_leaves": 15,
    "min_child_samples": 20,
    "random_state": RANDOM_STATE,
    "n_jobs": 1,
    "verbose": -1,
}
LR_MAX_ITER = 1000                        # design choice: enough for lbfgs to converge on 17 scaled features
EPOCH_FEATURES_PATH = MODELS_DIR / "epoch_features.csv"   # per-epoch training table behind the ML model
