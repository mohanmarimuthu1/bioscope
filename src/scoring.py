"""0–100 typicality score for one session (CLAUDE.md §7.6, ADR-010, ADR-011).

WHAT:  `score(features, qc, condition, preset)` → composite, confidence, 4 dimensions,
       per-feature z and scores, named metrics, plain-language explanations, warnings.
WHY:   One number a person can read, that still decomposes:
       composite → dimensions → features → z vs reference → signal.
STEPS:
  1. Reference cell = (preset, condition). z per feature via `reference.to_z` (the only z code).
  2. Feature score s = clip(100 − 15·|z|, 0, 100). Dimension = mean of its available scores.
     tbr_osc NaN (no beta rhythm) → Attention from paf alone + warning.
  3. signal_quality = 100·(0.5·retained_frac + 0.5·r2n), r2n = clip((fooof_r2 − 0.8)/0.2, 0, 1).
  4. composite = Σ weight·dimension; weights renormalised over dimensions that could be scored.
  5. confidence = 0.5·retained_frac + 0.3·r2n + 0.2·min(duration_s/60, 1).
CAVEATS:
  - The score is typicality versus 40–47 public-dataset adults, not health.
  - duration_s is read from qc (callers copy it from load_eeg meta); missing → no duration credit + warning.
  - 0 clean epochs → composite None, confidence 0: unrejected epochs are never scored.
"""
import logging

import numpy as np

from src import config, reference

log = logging.getLogger(__name__)

LABELS = {
    "tbr_osc": "Theta/beta ratio",
    "tbr_classic": "Classic theta/beta ratio",
    "paf": "Peak alpha frequency",
    "alpha_exc": "Alpha power above background",
    "faa": "Frontal alpha asymmetry",
    "hibeta_exc": "High beta power above background",
    "ap_exponent": "1/f slope",
}
NAMED_METRICS = ["tbr_osc", "tbr_classic", "paf", "paf_fallback_frac", "hibeta_exc", "hibeta_abs"]
COND_TEXT = {"eyes_open": "eyes-open", "eyes_closed": "eyes-closed"}


def _finite(x) -> bool:
    try:
        return bool(np.isfinite(float(x)))
    except (TypeError, ValueError):
        return False


def _num(x) -> float | None:
    return float(x) if _finite(x) else None


def _empty_result(features: dict, qc: dict, condition: str, preset: str, warnings: list[str]) -> dict:
    return {"composite": None, "confidence": 0.0, "condition": condition, "preset": preset,
            "dimensions": {d: None for d in config.WEIGHTS},
            "feature_z": {}, "feature_scores": {},
            "named_metrics": {k: _num(features.get(k)) for k in NAMED_METRICS},
            "explanations": [], "warnings": warnings}


def _explain(feature: str, z: float, method: str, condition: str) -> str:
    side = "above" if z > 0 else "below"
    unit = "SD-equivalent (rank-based)" if method == "percentile" else "SD"
    return f"{LABELS[feature]} is {abs(z):.1f} {unit} {side} the {COND_TEXT[condition]} reference"


def score(features: dict, qc: dict, condition: str, preset: str) -> dict:
    """Score one session against the (preset, condition) reference. Output keys per §7.6."""
    if condition not in config.CONDITIONS:
        raise ValueError(f"Unknown condition {condition!r}; expected one of {config.CONDITIONS}")
    if preset not in config.PRESETS:
        raise ValueError(f"Unknown preset {preset!r}; expected one of {list(config.PRESETS)}")
    ref = reference.load_reference(condition, preset)
    warnings = list(dict.fromkeys(list(qc.get("warnings", [])) + list(features.get("warnings", []))))

    n_kept = int(qc.get("n_kept", features.get("n_epochs", 0)) or 0)
    if features.get("insufficient_data") or n_kept == 0:
        msg = f"Insufficient clean data: 0/{qc.get('n_total', '?')} epochs passed rejection"
        if msg not in warnings:
            warnings.append(msg)
        return _empty_result(features, qc, condition, preset, warnings)

    # ---- z and feature scores
    feature_z, feature_scores = {}, {}
    for f, entry in ref.items():
        x = features.get(f)
        z = reference.to_z(f, float(x) if _finite(x) else np.nan, entry)   # None (e.g. from DB) → NaN
        if np.isfinite(z):
            feature_z[f] = float(z)
    for feats in config.DIMENSIONS.values():
        for f in feats:
            if f in feature_z:
                feature_scores[f] = float(np.clip(100 - config.Z_PENALTY * abs(feature_z[f]), 0, 100))

    # ---- dimensions
    dims: dict = {}
    for dim, feats in config.DIMENSIONS.items():
        avail = [feature_scores[f] for f in feats if f in feature_scores]
        missing = [f for f in feats if f not in feature_scores]
        for f in missing:
            if f == "tbr_osc":
                warnings.append("Theta/beta ratio unavailable (no beta rhythm above background): Attention uses peak alpha frequency only")
            elif avail:
                warnings.append(f"{f} missing; {dim} uses remaining features")
        if avail:
            dims[dim] = float(np.mean(avail))
        else:
            dims[dim] = None
            warnings.append(f"Dimension {dim} not scored: {', '.join(feats)} missing")

    retained = float(qc.get("retained_frac", 0.0) or 0.0)
    r2 = features.get("fooof_r2")
    if _finite(r2):
        r2n = float(np.clip((float(r2) - config.R2_FLOOR) / config.R2_SPAN, 0, 1))
    else:
        r2n = 0.0
        warnings.append("FOOOF fit quality unavailable: signal quality and confidence use r2n = 0")
    dims["signal_quality"] = 100 * (0.5 * retained + 0.5 * r2n)

    # ---- composite (weights renormalised over scored dimensions, ADR-011)
    scored = {d: v for d, v in dims.items() if v is not None}
    if not set(scored) & set(config.DIMENSIONS):     # signal quality alone is not a brain score
        warnings.append("No EEG features could be scored: composite not computed")
        composite = None
    else:
        w_total = sum(config.WEIGHTS[d] for d in scored)
        composite = sum(config.WEIGHTS[d] * v for d, v in scored.items()) / w_total
    if composite is not None and len(scored) < len(config.WEIGHTS):
        warnings.append(f"Composite uses {len(scored)}/{len(config.WEIGHTS)} dimensions (weights renormalised)")

    # ---- confidence
    duration = qc.get("duration_s")
    if not _finite(duration):
        duration = 0.0
        warnings.append("Recording duration unknown: no duration credit in confidence")
    dur_credit = min(float(duration) / config.CONF_FULL_DURATION_S, 1.0)
    confidence = (config.CONF_W_RETAINED * retained + config.CONF_W_R2 * r2n
                  + config.CONF_W_DURATION * dur_credit)
    if retained < config.MIN_RETAINED_FRAC or n_kept < config.MIN_EPOCHS:
        warnings.append(f"Low clean data ({n_kept} epochs, {retained:.0%} retained): interpret with caution")

    explanations = [_explain(f, feature_z[f], ref[f]["method"], condition)
                    for f in sorted(feature_scores, key=lambda f: -abs(feature_z[f]))
                    if abs(feature_z[f]) >= config.EXPLAIN_Z_THRESHOLD]

    return {"composite": None if composite is None else float(composite), "confidence": float(np.clip(confidence, 0, 1)),
            "condition": condition, "preset": preset,
            "dimensions": dims, "feature_z": feature_z, "feature_scores": feature_scores,
            "named_metrics": {k: _num(features.get(k)) for k in NAMED_METRICS},
            "explanations": explanations, "warnings": list(dict.fromkeys(warnings))}
