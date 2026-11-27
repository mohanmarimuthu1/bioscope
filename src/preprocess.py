"""Preprocessing: reference, filter, (ICA), epoch and reject.

WHAT:  `clean(raw, line_freq)` → (epochs, qc). Follows CLAUDE.md §7.4.
WHY:   Spectral features are only meaningful on artefact-reduced, fixed-length windows.
CAVEATS:
  - Works on a copy; the caller's Raw is never modified.
  - Zero kept epochs is NOT an error: empty epochs are returned with a warning and
    downstream code must refuse to score. Unrejected epochs are never used as a fallback.
  - A recording shorter than one epoch raises ValueError (nothing to analyse).
"""
import logging

import mne
import numpy as np

from src import config

log = logging.getLogger(__name__)


def _epoch_ptp_uv(epochs: mne.Epochs) -> list[float]:
    """Max-over-channels peak-to-peak amplitude per epoch, in µV."""
    data = epochs.get_data(copy=True)
    if data.size == 0:
        return []
    return (np.ptp(data, axis=2).max(axis=1) * 1e6).round(1).tolist()


def _filter(raw: mne.io.Raw, line_freq: float) -> bool:
    """Average reference + band-pass + conditional notch, in place. Returns notch_applied."""
    raw.set_eeg_reference("average", projection=False, verbose="ERROR")
    raw.filter(config.L_FREQ, config.H_FREQ, method="fir", phase="zero", verbose="ERROR")
    if line_freq < config.NOTCH_ONLY_IF_BELOW:
        raw.notch_filter(line_freq, verbose="ERROR")
        log.info("Notch applied at %.1f Hz", line_freq)
        return True
    log.info("Notch skipped: %.1f Hz is above the %.0f Hz low-pass", line_freq, config.H_FREQ)
    return False


def _ica_settings(ch_names: list[str]) -> dict | None:
    """ICA settings of the preset whose channel set matches, else None (no ICA)."""
    for preset in config.PRESETS.values():
        if set(preset["channels"]) == set(ch_names):
            return preset.get("ica")
    return None


def _run_ica(raw: mne.io.Raw, settings: dict, warnings: list[str]) -> tuple[bool, list[int], list[float]]:
    """Fit ICA and remove blink components in place, using the preset's EOG proxies.

    Returns (ica_used, excluded_components, per-component max |r| with the EOG proxies).
    Exclusion = components with |r| ≥ ICA_EOG_THRESHOLD, capped at the top
    ICA_MAX_EXCLUDE by |r|. Correlation, not z-score: with n−1 = 7 components a
    z-score can never exceed √6 ≈ 2.45, so z ≥ 3 never fires (ADR-005).
    Any failure → no ICA, a warning, and processing continues.
    """
    eog = [ch for ch in settings["eog_proxy"] if ch in raw.ch_names]
    if not eog:
        warnings.append("ICA skipped: no channel to use as an eye-blink reference")
        return False, [], []
    try:
        ica = mne.preprocessing.ICA(
            n_components=len(raw.ch_names) - 1, method=config.ICA_METHOD,
            random_state=config.RANDOM_STATE, max_iter="auto", verbose="ERROR",
        )
        ica.fit(raw, verbose="ERROR")
        inds, scores = ica.find_bads_eog(
            raw, ch_name=eog, threshold=config.ICA_EOG_THRESHOLD,
            measure=config.ICA_EOG_MEASURE, verbose="ERROR",
        )
        combined = np.abs(np.atleast_2d(np.asarray(scores))).max(axis=0)
        chosen = sorted({int(i) for i in inds}, key=lambda i: -combined[i])[: settings["max_exclude"]]
        ica.exclude = chosen
        ica.apply(raw, verbose="ERROR")
        log.info("ICA excluded %s; EOG |z| per component %s", chosen, combined.round(2).tolist())
        return True, chosen, combined.round(3).tolist()
    except Exception as exc:  # noqa: BLE001 — any ICA failure must degrade, not crash
        warnings.append(f"ICA failed ({type(exc).__name__}: {exc}); continued without blink removal")
        log.warning("ICA failed: %s", exc)
        return False, [], []


def _segment_events(raw: mne.io.Raw) -> tuple[np.ndarray, int]:
    """Fixed-length epoch events restarted at every concatenation boundary (ADR-012).

    WHY: `mne.concatenate_raws` marks joins with "BAD boundary"/"EDGE boundary". A single 2 s grid
    from t = 0 puts most 4 s epochs across a join (S060 T0 blocks are 4.1 s → 1 epoch per session).
    Here each segment gets its own grid from its first sample, and no epoch crosses a join.
    For a file without boundaries the events equal `mne.make_fixed_length_events`.
    """
    sfreq = raw.info["sfreq"]
    dur = int(round(config.EPOCH_LENGTH_S * sfreq))
    step = sfreq * (config.EPOCH_LENGTH_S - config.EPOCH_OVERLAP_S)
    ann = raw.annotations
    is_b = np.isin(ann.description, ["BAD boundary", "EDGE boundary"])
    cuts = raw.time_as_index(ann.onset[is_b], use_rounding=True, origin=ann.orig_time) if is_b.any() else []
    edges = sorted({0, raw.n_times} | {int(c) for c in cuts if 0 < c < raw.n_times})
    starts = [np.arange(s, e - dur + 1, step).astype(int) for s, e in zip(edges[:-1], edges[1:])]
    ts = np.concatenate(starts) if starts else np.array([], dtype=int)
    if len(ts) == 0:
        raise ValueError(f"No {config.EPOCH_LENGTH_S:.0f} s segment without a boundary in this recording")
    events = np.c_[ts + raw.first_samp, np.zeros(len(ts), dtype=int), np.ones(len(ts), dtype=int)]
    return events, len(edges) - 1


def clean(raw: mne.io.Raw, line_freq: float) -> tuple[mne.Epochs, dict]:
    """Preprocess a preset-picked Raw into clean 4 s epochs plus a QC dict.

    qc keys: n_total, n_kept, retained_frac, ica_used, ica_excluded, warnings,
    notch_applied, ica_eog_scores, epoch_ptp_uv, n_segments (additive keys after `warnings`).
    """
    if raw.times[-1] + 1 / raw.info["sfreq"] < config.EPOCH_LENGTH_S:
        raise ValueError(
            f"Recording is {raw.n_times / raw.info['sfreq']:.1f} s; at least "
            f"{config.EPOCH_LENGTH_S:.0f} s is needed for one epoch"
        )
    raw = raw.copy().load_data(verbose="ERROR")
    warnings: list[str] = []
    notch_applied = _filter(raw, line_freq)

    ica_used, ica_excluded, ica_scores = False, [], []
    settings = _ica_settings(raw.ch_names)
    if settings:
        ica_used, ica_excluded, ica_scores = _run_ica(raw, settings, warnings)
    else:
        log.info("ICA skipped: no ICA settings for channels %s", raw.ch_names)

    events, n_segments = _segment_events(raw)
    # Events never cross a join by construction. Zero-length boundary marks sit on a segment's first
    # sample and MNE's rounding then rejected some valid epochs (4/15 on S060 R03) → drop them here;
    # other BAD_ annotations still reject (BUG-002).
    ann = raw.annotations
    raw.set_annotations(ann[[i for i, d in enumerate(ann.description) if d not in ("BAD boundary", "EDGE boundary")]])
    epochs = mne.Epochs(
        raw, events, event_id=[1], tmin=0, tmax=config.EPOCH_LENGTH_S - 1 / raw.info["sfreq"],
        baseline=None, preload=True, reject_by_annotation=True, verbose="ERROR",
    )
    n_total = len(epochs)
    ptp_uv = _epoch_ptp_uv(epochs)
    epochs.drop_bad(reject={"eeg": config.REJECT_PTP_V}, verbose="ERROR")
    n_kept = len(epochs)
    retained = n_kept / n_total if n_total else 0.0

    if n_kept == 0:
        warnings.append(f"Insufficient clean data: 0/{n_total} epochs passed rejection")
    elif retained < config.MIN_RETAINED_FRAC or n_kept < config.MIN_EPOCHS:
        warnings.append(
            f"Low clean data: {n_kept}/{n_total} epochs kept ({retained:.0%}); "
            f"confidence is reduced"
        )

    qc = {
        "n_total": n_total,
        "n_kept": n_kept,
        "retained_frac": retained,
        "ica_used": ica_used,
        "ica_excluded": ica_excluded,
        "warnings": warnings,
        "notch_applied": notch_applied,
        "ica_eog_scores": ica_scores,
        "epoch_ptp_uv": ptp_uv,
        "n_segments": n_segments,
    }
    log.info("clean: kept %d/%d epochs (%.0f%%), ica_used=%s", n_kept, n_total, retained * 100, ica_used)
    return epochs, qc
