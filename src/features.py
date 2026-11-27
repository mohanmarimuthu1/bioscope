"""Spectral and complexity features from clean epochs (CLAUDE.md §7.5, ADR-007).

WHAT:  `extract(epochs, preset)` → (session_features, per_epoch_features).
       `session_spectrum(epochs)` → mean PSD + aperiodic fit per channel (for the UI plot).
WHY:   FOOOF separates oscillations from the 1/f background, so TBR, PAF and high beta
       describe rhythms rather than broadband shifts.
STEPS (session level, per channel, then median across channels):
  1. Welch PSD per epoch (2 s segments, 50% overlap, 1–40 Hz), V²/Hz → µV²/Hz.
  2. Mean PSD over kept epochs → FOOOF (fixed aperiodic) → ap_exponent, ap_offset, fooof_r2, peaks.
  3. paf = strongest FOOOF peak in 7–14 Hz; else centre of gravity over 7–13 Hz (fallback).
  4. {band}_abs = ∫PSD (µV²); {band}_osc = mean(PSD / aperiodic fit) over the band.
  5. tbr_classic, tbr_osc; faa = ln(mean α right) − ln(mean α left); samp_entropy.
PER-EPOCH (ADR-007): no per-epoch FOOOF. Each epoch's PSD is divided by its channel's
  *session* aperiodic fit; per-epoch PAF = centre of gravity 7–13 Hz; ap_* are session-only.
CAVEATS:
  - A channel whose FOOOF fit fails, is NaN, or has r² < FOOOF_MIN_R2 gets NaN FOOOF
    features (and NaN osc), a warning, and is ignored by the nanmedian.
  - 0 epochs → all features NaN, insufficient_data=True, empty per-epoch table. No crash.
"""
import logging
import warnings as _pywarnings

import antropy as ant
import mne
import numpy as np
import pandas as pd

with _pywarnings.catch_warnings():  # fooof 1.1 prints a deprecation notice on import (ADR-001)
    _pywarnings.simplefilter("ignore", DeprecationWarning)
    from fooof import FOOOF

from src import config

log = logging.getLogger(__name__)

BAND_NAMES = list(config.BANDS)
SESSION_KEYS = (
    ["ap_exponent", "ap_offset", "fooof_r2", "paf", "paf_fallback", "paf_fallback_frac"]
    + [f"{b}_abs" for b in BAND_NAMES] + [f"{b}_osc" for b in BAND_NAMES]
    + ["tbr_classic", "tbr_osc", "faa", "samp_entropy"]
)
EPOCH_COLUMNS = (
    ["epoch"] + [f"{b}_abs" for b in BAND_NAMES] + [f"{b}_osc" for b in BAND_NAMES]
    + ["tbr_classic", "tbr_osc", "paf", "faa", "samp_entropy"]
)


# --------------------------------------------------------------------------- spectra
def _welch_uv2(epochs: mne.Epochs) -> tuple[np.ndarray, np.ndarray]:
    """Per-epoch Welch PSD in µV²/Hz, shape (n_epochs, n_ch, n_freqs), plus freqs."""
    n_per_seg = int(round(config.WELCH_N_PER_SEG_S * epochs.info["sfreq"]))
    spec = epochs.compute_psd(
        method="welch", fmin=config.PSD_FMIN, fmax=config.PSD_FMAX, n_fft=n_per_seg,
        n_per_seg=n_per_seg, n_overlap=int(n_per_seg * config.WELCH_OVERLAP_FRAC),
        verbose="ERROR",
    )
    psd, freqs = spec.get_data(return_freqs=True)
    return psd * config.V2_TO_UV2, freqs


def _band_mask(freqs: np.ndarray, band: tuple[float, float]) -> np.ndarray:
    lo, hi = band
    return (freqs >= lo) & (freqs < hi)


def _cog(freqs: np.ndarray, psd: np.ndarray) -> float:
    """Spectral centre of gravity over PAF_COG_RANGE (linear power weights)."""
    m = (freqs >= config.PAF_COG_RANGE[0]) & (freqs <= config.PAF_COG_RANGE[1])
    p = psd[m]
    return float(np.sum(freqs[m] * p) / np.sum(p)) if np.sum(p) > 0 else np.nan


def _fit_channel(freqs: np.ndarray, psd: np.ndarray) -> dict:
    """FOOOF on one channel's mean spectrum. Returns NaNs if the fit fails or is poor."""
    nan = {"ap_exponent": np.nan, "ap_offset": np.nan, "fooof_r2": np.nan,
           "peak_cf": np.nan, "ap_log": np.full_like(freqs, np.nan), "ok": False}
    if not np.all(np.isfinite(psd)) or np.any(psd <= 0):
        return nan
    try:
        fm = FOOOF(**config.FOOOF_SETTINGS, verbose=False)
        fm.fit(freqs, psd, config.FOOOF_FREQ_RANGE)
        offset, exponent = fm.aperiodic_params_
        r2 = float(fm.r_squared_)
    except Exception as exc:  # noqa: BLE001 — a bad channel must not crash the session
        log.warning("FOOOF raised: %s", exc)
        return nan
    if not (np.isfinite(offset) and np.isfinite(exponent) and np.isfinite(r2)) or r2 < config.FOOOF_MIN_R2:
        return {**nan, "fooof_r2": r2 if np.isfinite(r2) else np.nan}
    peaks = np.atleast_2d(fm.peak_params_)
    lo, hi = config.PAF_PEAK_RANGE
    in_alpha = [p for p in peaks if p.size and lo <= p[0] <= hi]
    peak_cf = max(in_alpha, key=lambda p: p[1])[0] if in_alpha else np.nan
    return {"ap_exponent": float(exponent), "ap_offset": float(offset), "fooof_r2": r2,
            "peak_cf": float(peak_cf), "ap_log": offset - exponent * np.log10(freqs), "ok": True}


def _band_features(freqs: np.ndarray, psd: np.ndarray, ap_log: np.ndarray) -> dict:
    """abs (∫PSD) and osc (mean PSD/aperiodic) per band for one channel spectrum."""
    out = {}
    ap_lin = 10.0 ** ap_log
    for name, band in config.BANDS.items():
        m = _band_mask(freqs, band)
        out[f"{name}_abs"] = float(np.trapezoid(psd[m], freqs[m]))
        out[f"{name}_osc"] = float(np.mean(psd[m] / ap_lin[m]))
    return out


def _ratio(num: float, den: float) -> float:
    return float(num / den) if np.isfinite(num) and np.isfinite(den) and den > 0 else np.nan


def _faa(alpha_abs: np.ndarray, ch_names: list[str], preset: str) -> float:
    """ln(mean alpha_abs right) − ln(mean alpha_abs left)."""
    p = config.PRESETS[preset]
    left = np.nanmean([alpha_abs[ch_names.index(c)] for c in p["faa_left"]])
    right = np.nanmean([alpha_abs[ch_names.index(c)] for c in p["faa_right"]])
    return float(np.log(right) - np.log(left)) if left > 0 and right > 0 else np.nan


def _session_fit(epochs: mne.Epochs) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[dict]]:
    psd_ep, freqs = _welch_uv2(epochs)
    mean_psd = psd_ep.mean(axis=0)
    fits = [_fit_channel(freqs, mean_psd[i]) for i in range(mean_psd.shape[0])]
    return psd_ep, freqs, mean_psd, fits


# --------------------------------------------------------------------------- public
def session_spectrum(epochs: mne.Epochs) -> dict:
    """Mean PSD (µV²/Hz) and aperiodic fit (µV²/Hz) per channel, for plotting."""
    if len(epochs) == 0:
        return {"freqs": np.array([]), "psd_uv2": np.empty((0, 0)), "ap_fit_uv2": np.empty((0, 0)),
                "ch_names": list(epochs.ch_names)}
    _, freqs, mean_psd, fits = _session_fit(epochs)
    return {"freqs": freqs, "psd_uv2": mean_psd,
            "ap_fit_uv2": np.array([10.0 ** f["ap_log"] for f in fits]),
            "ch_names": list(epochs.ch_names)}


def _empty(warnings: list[str]) -> tuple[dict, pd.DataFrame]:
    feats = {k: np.nan for k in SESSION_KEYS}
    feats.update(paf_fallback=False, insufficient_data=True, n_epochs=0, warnings=warnings)
    return feats, pd.DataFrame(columns=EPOCH_COLUMNS)


def extract(epochs: mne.Epochs, preset: str) -> tuple[dict, pd.DataFrame]:
    """Compute session features (dict) and a per-epoch feature table (DataFrame).

    Session dict = SESSION_KEYS + insufficient_data, n_epochs, warnings.
    """
    warnings: list[str] = []
    if len(epochs) == 0:
        warnings.append("No clean epochs: features not computed")
        return _empty(warnings)

    ch_names = list(epochs.ch_names)
    psd_ep, freqs, mean_psd, fits = _session_fit(epochs)
    for ch, f in zip(ch_names, fits):
        if not f["ok"]:
            warnings.append(f"FOOOF fit failed/poor on {ch}")

    # ---- per channel, session level
    rows = []
    for i, f in enumerate(fits):
        band = _band_features(freqs, mean_psd[i], f["ap_log"])
        fallback = not np.isfinite(f["peak_cf"])
        rows.append({**band, "ap_exponent": f["ap_exponent"], "ap_offset": f["ap_offset"],
                     "fooof_r2": f["fooof_r2"], "peak_cf": f["peak_cf"],
                     "cog": _cog(freqs, mean_psd[i]), "fallback": fallback})
    ch_df = pd.DataFrame(rows, index=ch_names)

    feats: dict = {}
    for k in ["ap_exponent", "ap_offset", "fooof_r2"] + [f"{b}_{t}" for b in BAND_NAMES for t in ("abs", "osc")]:
        feats[k] = float(np.nanmedian(ch_df[k])) if ch_df[k].notna().any() else np.nan
    real = ch_df["peak_cf"].dropna()
    feats["paf"] = float(real.median()) if len(real) else float(np.nanmedian(ch_df["cog"]))
    feats["paf_fallback_frac"] = float(ch_df["fallback"].mean())
    feats["paf_fallback"] = feats["paf_fallback_frac"] > 0.5
    feats["tbr_classic"] = _ratio(feats["theta_abs"], feats["beta_abs"])
    feats["tbr_osc"] = _ratio(feats["theta_osc"], feats["beta_osc"])
    feats["faa"] = _faa(ch_df["alpha_abs"].to_numpy(), ch_names, preset)

    # ---- per epoch (ADR-007: session aperiodic fit reused, no per-epoch FOOOF)
    data = epochs.get_data(copy=False)
    epoch_rows, ent_all = [], []
    for e in range(psd_ep.shape[0]):
        per_ch = [_band_features(freqs, psd_ep[e, i], fits[i]["ap_log"]) for i in range(len(ch_names))]
        ep_df = pd.DataFrame(per_ch, index=ch_names)
        ent = np.array([ant.sample_entropy(data[e, i]) for i in range(len(ch_names))])
        ent_all.append(ent)
        row = {"epoch": e}
        for col in ep_df.columns:
            row[col] = float(np.nanmedian(ep_df[col])) if ep_df[col].notna().any() else np.nan
        row["tbr_classic"] = _ratio(row["theta_abs"], row["beta_abs"])
        row["tbr_osc"] = _ratio(row["theta_osc"], row["beta_osc"])
        row["paf"] = float(np.nanmedian([_cog(freqs, psd_ep[e, i]) for i in range(len(ch_names))]))
        row["faa"] = _faa(ep_df["alpha_abs"].to_numpy(), ch_names, preset)
        row["samp_entropy"] = float(np.nanmedian(ent))
        epoch_rows.append(row)
    per_epoch = pd.DataFrame(epoch_rows, columns=EPOCH_COLUMNS)

    ent_all = np.array(ent_all)                       # (n_epochs, n_ch)
    feats["samp_entropy"] = float(np.nanmedian(np.nanmean(ent_all, axis=0)))
    feats.update(insufficient_data=False, n_epochs=int(len(epochs)), warnings=warnings)
    log.info("extract: %d epochs, paf=%.2f (fallback %.0f%%), r2=%.3f",
             len(epochs), feats["paf"], feats["paf_fallback_frac"] * 100, feats["fooof_r2"])
    return feats, per_epoch
