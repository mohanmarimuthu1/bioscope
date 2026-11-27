"""Condition- and preset-matched reference distributions (CLAUDE.md §7.6, ADR-010).

WHAT:  `load_reference(condition, preset)` → {feature: entry} from models/reference.json.
       `transform(feature, x)` applies the feature's ADR-010 transform (ln, ln1p or none).
       `build_entry(feature, values)` summarises reference values into an entry.
       `to_z(feature, x, entry)` turns a new session value into a z against that entry.
WHY:   The score measures typicality versus people recorded the same way (same preset,
       same eyes-open/closed condition). Skewed features would make mean ± std z-scores
       misleading, so they are transformed and, if still skewed, ranked instead.
ENTRY: {transform, method, mean, std, n, skew, min, max, values?}. mean/std/skew/min/max
       are on the transformed scale. `values` (sorted, transformed) only for method
       "percentile".
Z METHODS:
  zscore     z = (t − mean) / std
  percentile inside [min, max]: z = Φ⁻¹(rank / (n + 1)), rank = mid-rank of t among the
             reference values (ties averaged, 1-based). Outside the range, a continuous
             linear extension: z = z_pct(edge) + (t − edge) / std (ADR-010 rev 2; the rev 1
             hybrid jumped 2.05 → 3.85 at the max). |z| capped at PERCENTILE_Z_CAP.
CAVEATS:
  - n ≈ 43–49 per cell, so the skew estimate itself has SE ≈ 0.35; the |skew| > 1 split
    is an owner rule, not a test.
  - Presets are never mixed: frontal8 and muse4 have different scales (ADR-010).
"""
import json
import logging
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.stats import norm, skew

from src import config

log = logging.getLogger(__name__)

_FUNCS = {"none": lambda x: x, "ln": np.log, "ln1p": np.log1p}


def transform(feature: str, x: float) -> float:
    """Apply the feature's reference transform; NaN for NaN or out-of-domain input."""
    tf = config.REFERENCE_TRANSFORMS[feature]
    x = float(x)
    if not np.isfinite(x) or (tf == "ln" and x <= 0) or (tf == "ln1p" and x <= -1):
        return np.nan
    return float(_FUNCS[tf](x))


def build_entry(feature: str, values: list[float]) -> dict:
    """Summarise raw reference values of one feature (one preset × condition cell).

    Non-finite values are dropped. Method = "percentile" if |skew| after transform exceeds
    SKEW_PERCENTILE_THRESHOLD, else "zscore".
    """
    t = np.array([transform(feature, v) for v in values], dtype=float)
    t = np.sort(t[np.isfinite(t)])
    if len(t) < 3:
        raise ValueError(f"{feature}: only {len(t)} finite reference values")
    sk = float(skew(t, bias=False))
    method = "percentile" if abs(sk) > config.SKEW_PERCENTILE_THRESHOLD else "zscore"
    entry = {"transform": config.REFERENCE_TRANSFORMS[feature], "method": method,
             "mean": float(t.mean()), "std": float(t.std(ddof=1)), "n": int(len(t)),
             "skew": sk, "min": float(t[0]), "max": float(t[-1])}
    if method == "percentile":
        entry["values"] = [float(v) for v in t]
    return entry


def _z_pct(v: np.ndarray, t: float) -> float:
    """Φ⁻¹(rank/(n+1)) with the 1-based mid-rank of t among sorted reference values v."""
    rank = (np.sum(v < t) + np.sum(v <= t)) / 2 + 0.5
    return float(norm.ppf(rank / (len(v) + 1)))


def to_z(feature: str, x: float, entry: dict) -> float:
    """z of a raw session value against a reference entry (see module docstring)."""
    t = transform(feature, x)
    if not np.isfinite(t) or not entry["std"] > 0:
        return np.nan
    z_param = (t - entry["mean"]) / entry["std"]
    if entry["method"] == "zscore":
        return float(z_param)
    v = np.asarray(entry["values"])
    if t < entry["min"]:          # continuous extension below the range (ADR-010 rev 2)
        z = _z_pct(v, entry["min"]) + (t - entry["min"]) / entry["std"]
    elif t > entry["max"]:        # ... and above it
        z = _z_pct(v, entry["max"]) + (t - entry["max"]) / entry["std"]
    else:
        z = _z_pct(v, t)
    cap = config.PERCENTILE_Z_CAP
    return float(np.clip(z, -cap, cap))


@lru_cache(maxsize=4)
def _read(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_reference(condition: str, preset: str) -> dict:
    """Return {feature: entry} for one preset × condition. Raises ValueError if unknown."""
    path = config.REFERENCE_PATH
    if not path.exists():
        raise FileNotFoundError(f"{path} missing; run: python scripts/build_reference.py")
    ref = _read(str(path))
    cells = ref["presets"]
    if preset not in cells or condition not in cells[preset]:
        avail = [f"{p}/{c}" for p in cells for c in cells[p]]
        raise ValueError(f"No reference for {preset}/{condition}; available: {avail}")
    cell = cells[preset][condition]
    log.debug("reference %s/%s: %d subjects, built %s", preset, condition, len(cell["subjects_used"]), ref["build_date"])
    return cell["features"]


def assert_no_leak(subjects: list[str]) -> None:
    """Raise AssertionError if a demo (S060, S051) or holdout subject is in `subjects` (ADR-002, ADR-012).

    Explicit raise, not `assert`, so the guard survives `python -O`.
    """
    held_out = {config.DEMO_SUBJECT, config.DEMO_LONGITUDINAL_SUBJECT} | set(config.HOLDOUT_SUBJECTS)
    leaked = sorted(set(subjects) & held_out)
    if leaked:
        raise AssertionError(f"Held-out subjects in reference: {leaked}")
