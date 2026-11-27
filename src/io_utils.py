"""EEG file loading and channel-label normalisation.

WHAT:  `load_eeg(path, preset)` reads an EDF or FIF file, normalises channel labels to
       standard 10-10 names, and returns only the preset's channels (in preset order)
       plus a metadata dict.
WHY:   Every downstream step (preprocess, features, scoring) needs the same channels
       in the same order, with consistent names, whatever the file's source.
CAVEATS:
  - Values stay in volts (MNE convention). Nothing is rescaled here.
  - Annotations (e.g. EEGMMI T0/T1/T2 markers) are kept; the demo builder needs T0.
  - ASSUMPTION: input labels follow EEGMMI style (trailing dots, odd case) or are
    already standard; any other naming scheme must already match the preset names.
"""
import logging
from pathlib import Path

import mne

from src import config

log = logging.getLogger(__name__)

_READERS = {
    ".edf": mne.io.read_raw_edf,
    ".fif": mne.io.read_raw_fif,
}


def normalise_label(name: str) -> str:
    """Map an EEGMMI label to its standard 10-10 name.

    Rule: strip dots → uppercase → 'FP' prefix back to 'Fp' → trailing 'Z' back to 'z'.
    Examples: 'Fp1.'→'Fp1', 'Fpz.'→'Fpz', 'Afz.'→'AFz', 'Fc5.'→'FC5', 'Cz..'→'Cz',
    'Tp7.'→'TP7', 'Iz..'→'Iz', 'Poz.'→'POz', 'T9..'→'T9'.
    """
    label = name.strip().replace(".", "").upper()
    if label.startswith("FP"):
        label = "Fp" + label[2:]
    if label.endswith("Z"):
        label = label[:-1] + "z"
    return label


def load_eeg(path: str, preset: str) -> tuple[mne.io.Raw, dict]:
    """Load an EDF/FIF file and return (raw restricted to preset channels, meta).

    meta keys: sfreq, n_samples, duration_s, channels, preset, source.
    Raises ValueError for an unknown preset, an unsupported extension, or missing channels.
    """
    if preset not in config.PRESETS:
        raise ValueError(f"Unknown preset '{preset}'. Valid presets: {sorted(config.PRESETS)}")
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix not in _READERS:
        raise ValueError(f"Unsupported file type '{suffix}' for {p.name}. Use .edf or .fif")

    raw = _READERS[suffix](str(p), preload=False, verbose="ERROR")
    raw.rename_channels({ch: normalise_label(ch) for ch in raw.ch_names})

    wanted = config.PRESETS[preset]["channels"]
    missing = [ch for ch in wanted if ch not in raw.ch_names]
    if missing:
        raise ValueError(
            f"Preset '{preset}' needs channels missing from {p.name}: {missing}. "
            f"Available: {raw.ch_names}"
        )

    raw.pick(wanted)          # pick keeps annotations
    raw.reorder_channels(wanted)
    raw.load_data(verbose="ERROR")

    sfreq = float(raw.info["sfreq"])
    meta = {
        "sfreq": sfreq,
        "n_samples": int(raw.n_times),
        "duration_s": raw.n_times / sfreq,
        "channels": list(raw.ch_names),
        "preset": preset,
        "source": p.name,
    }
    log.info("Loaded %s: %d ch, %d samples, %.1f s @ %.0f Hz",
             p.name, len(wanted), meta["n_samples"], meta["duration_s"], sfreq)
    return raw, meta
