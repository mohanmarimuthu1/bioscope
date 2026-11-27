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


def clean(raw: mne.io.Raw, line_freq: float) -> tuple[mne.Epochs, dict]:
    """Preprocess a preset-picked Raw into clean 4 s epochs plus a QC dict.

    qc keys: n_total, n_kept, retained_frac, ica_used, ica_excluded, warnings,
    notch_applied, ica_eog_scores, epoch_ptp_uv (additive keys after `warnings`).
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

    epochs = mne.make_fixed_length_epochs(
        raw, duration=config.EPOCH_LENGTH_S, overlap=config.EPOCH_OVERLAP_S,
        preload=True, verbose="ERROR",
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
    }
    log.info("clean: kept %d/%d epochs (%.0f%%), ica_used=%s", n_kept, n_total, retained * 100, ica_used)
    return epochs, qc
