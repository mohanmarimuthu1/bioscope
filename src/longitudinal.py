"""Longitudinal tracking of session scores (CLAUDE.md §7.7, ADR-012).

WHAT:  compute_baseline (first n sessions), ema (exponential moving average), bayesian_track
       (Gaussian posterior over the person's "true" score), flag_shifts (|z| vs baseline > 2),
       deltas_vs_baseline (per-dimension / named-metric change).
WHY:   One session is noisy; a trend needs a personal reference point and a way to weigh
       low-confidence sessions less.
CAVEATS:
  - Inputs are finite floats in session order. Sessions with composite None (no clean data)
    must be dropped by the caller, which keeps its own index mapping.
  - The demo's 13 sessions come from one visit; the tracker shows mechanics, not multi-day change.
"""
import numpy as np

from src import config


def _check(values: list[float], name: str) -> np.ndarray:
    a = np.asarray(values, dtype=float)
    if a.ndim != 1 or not np.all(np.isfinite(a)):
        raise ValueError(f"{name} must be a 1-D list of finite floats (drop None sessions first)")
    return a


def compute_baseline(scores: list[float], n: int = config.BASELINE_N) -> dict:
    """Mean/std of the first n sessions; std = sample std (ddof=1) floored at BASELINE_STD_FLOOR.

    Fewer than n sessions → baseline from those available, provisional=True. 0 sessions → ValueError.
    """
    a = _check(scores, "scores")
    if len(a) == 0:
        raise ValueError("No sessions to build a baseline from")
    first = a[:n]
    sd = float(np.std(first, ddof=1)) if len(first) > 1 else 0.0
    return {"mean": float(np.mean(first)), "std": max(sd, config.BASELINE_STD_FLOOR),
            "raw_std": sd, "n": int(len(first)), "provisional": bool(len(first) < n)}


def ema(scores: list[float], alpha: float = config.EMA_ALPHA) -> list[float]:
    """e_1 = s_1; e_t = alpha·s_t + (1 − alpha)·e_{t−1}."""
    a = _check(scores, "scores")
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in (0, 1]")
    out: list[float] = []
    for s in a:
        out.append(float(s) if not out else float(alpha * s + (1 - alpha) * out[-1]))
    return out


def obs_sd_from_confidence(confidence: list[float]) -> list[float]:
    """obs_sd = 5 + 15·(1 − confidence): a low-confidence session is a noisier observation."""
    c = np.clip(_check(confidence, "confidence"), 0, 1)
    return [float(config.OBS_SD_BASE + config.OBS_SD_SCALE * (1 - x)) for x in c]


def bayesian_track(scores: list[float], obs_sd: list[float]) -> list[tuple[float, float]]:
    """Gaussian update per session; returns [(posterior mean, posterior sd)] after each session.

    Prior N(scores[0], PRIOR_SD²). post_var = 1/(1/prior_var + 1/obs_var);
    post_mean = post_var·(prior_mean/prior_var + obs/obs_var). The posterior becomes the next prior.
    """
    a, sd = _check(scores, "scores"), _check(obs_sd, "obs_sd")
    if len(a) != len(sd) or np.any(sd <= 0):
        raise ValueError("scores and obs_sd must have equal length and obs_sd > 0")
    if len(a) == 0:
        return []
    mean, var = float(a[0]), config.PRIOR_SD ** 2
    out = []
    for s, o in zip(a, sd):
        obs_var = float(o) ** 2
        post_var = 1 / (1 / var + 1 / obs_var)
        mean = post_var * (mean / var + float(s) / obs_var)
        var = post_var
        out.append((float(mean), float(np.sqrt(var))))
    return out


def flag_shifts(scores: list[float], baseline: dict, z: float = config.FLAG_Z) -> list[bool]:
    """True where |score − baseline mean| / baseline std > z, for sessions after the baseline window."""
    a = _check(scores, "scores")
    return [bool(i >= baseline["n"] and abs(s - baseline["mean"]) / baseline["std"] > z) for i, s in enumerate(a)]


def deltas_vs_baseline(values: list[float], n: int = config.BASELINE_N) -> list[float]:
    """value − mean(first n values), for a dimension or named metric. NaN entries stay NaN."""
    a = np.asarray(values, dtype=float)
    base = a[:n][np.isfinite(a[:n])]
    if len(base) == 0:
        return [float("nan")] * len(a)
    return [float(x - base.mean()) for x in a]
