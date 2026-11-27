"""Tests for src/io_utils.py.

Tests on data/raw/ skip on a clean clone (raw data is gitignored); the committed
sample file and the hard-coded EEGMMI label list keep the rest runnable everywhere.
Expected shapes come from the source file's own n_times, never a magic number.
"""
import mne
import numpy as np
import pytest

from src import config
from src.io_utils import load_eeg, normalise_label

SAMPLE = config.DATA_SAMPLE / "sample_frontal8_raw.fif"
S060R01 = config.DATA_RAW / "S060" / "S060R01.edf"
S060R03 = config.DATA_RAW / "S060" / "S060R03.edf"
needs_raw = pytest.mark.skipif(not S060R01.exists(), reason="data/raw not downloaded")

# Raw labels exactly as stored in EEGMMI EDF headers (64 channels).
EEGMMI_RAW_LABELS = (
    "Fc5. Fc3. Fc1. Fcz. Fc2. Fc4. Fc6. C5.. C3.. C1.. Cz.. C2.. C4.. C6.. Cp5. Cp3. "
    "Cp1. Cpz. Cp2. Cp4. Cp6. Fp1. Fpz. Fp2. Af7. Af3. Afz. Af4. Af8. F7.. F5.. F3.. "
    "F1.. Fz.. F2.. F4.. F6.. F8.. Ft7. Ft8. T7.. T8.. T9.. T10. Tp7. Tp8. P7.. P5.. "
    "P3.. P1.. Pz.. P2.. P4.. P6.. P8.. Po7. Po3. Poz. Po4. Po8. O1.. Oz.. O2.. Iz.."
).split()


@pytest.mark.parametrize("raw_name, expected", [
    ("Fp1.", "Fp1"), ("Fpz.", "Fpz"), ("Afz.", "AFz"), ("Fc5.", "FC5"), ("Cz..", "Cz"),
    ("Tp7.", "TP7"), ("Iz..", "Iz"), ("Poz.", "POz"), ("T9..", "T9"),
])
def test_normalise_label_each_mapping_class(raw_name, expected):
    assert normalise_label(raw_name) == expected


def test_all_64_labels_unique_and_cover_presets():
    names = [normalise_label(n) for n in EEGMMI_RAW_LABELS]
    assert len(names) == 64
    assert len(set(names)) == 64
    for preset in config.PRESETS.values():
        assert set(preset["channels"]) <= set(names)


def test_normalise_is_idempotent_on_standard_names():
    for name in ["Fp1", "AFz", "FC5", "TP7", "Iz", "POz"]:
        assert normalise_label(name) == name


@needs_raw
@pytest.mark.parametrize("preset", ["frontal8", "muse4"])
def test_gate_s060r01_shapes(preset):
    source = mne.io.read_raw_edf(S060R01, verbose="ERROR")
    raw, meta = load_eeg(str(S060R01), preset)
    channels = config.PRESETS[preset]["channels"]
    assert raw.get_data().shape == (len(channels), source.n_times)
    assert meta["channels"] == channels                     # preset order
    assert meta["sfreq"] == 160.0
    assert meta["n_samples"] == source.n_times
    assert meta["duration_s"] == source.n_times / meta["sfreq"]
    print(f"{preset}: {raw.get_data().shape}, duration_s={meta['duration_s']}")


@needs_raw
def test_annotations_survive_load_for_t0_blocks():
    raw, _ = load_eeg(str(S060R03), "frontal8")
    assert "T0" in set(raw.annotations.description)


def test_sample_fif_loads_with_meta():
    raw, meta = load_eeg(str(SAMPLE), "frontal8")
    assert set(meta) == {"sfreq", "n_samples", "duration_s", "channels", "preset", "source"}
    assert meta["n_samples"] == raw.n_times
    assert meta["duration_s"] == raw.n_times / meta["sfreq"]
    assert meta["source"] == SAMPLE.name


def test_values_stay_in_volts():
    raw, _ = load_eeg(str(SAMPLE), "frontal8")
    assert np.median(np.abs(raw.get_data())) < 1e-3       # < 1 mV → volts, not µV


def test_fif_round_trip_preserves_data(tmp_path):
    raw, _ = load_eeg(str(SAMPLE), "frontal8")
    out = tmp_path / "copy_raw.fif"
    raw.save(out, verbose="ERROR")
    raw2, meta2 = load_eeg(str(out), "frontal8")
    np.testing.assert_allclose(raw2.get_data(), raw.get_data(), rtol=1e-6)
    assert meta2["channels"] == config.PRESETS["frontal8"]["channels"]


def test_missing_channel_error_lists_missing_and_available():
    # sample has only frontal8 channels, so muse4 channels are missing
    with pytest.raises(ValueError) as err:
        load_eeg(str(SAMPLE), "muse4")
    msg = str(err.value)
    assert "AF7" in msg and "TP8" in msg and "Available" in msg and "Fp1" in msg


def test_unknown_preset_rejected():
    with pytest.raises(ValueError, match="Unknown preset"):
        load_eeg(str(SAMPLE), "nonsense")


def test_unsupported_extension_rejected(tmp_path):
    bad = tmp_path / "x.csv"
    bad.write_text("a,b\n")
    with pytest.raises(ValueError, match="Unsupported file type"):
        load_eeg(str(bad), "frontal8")
