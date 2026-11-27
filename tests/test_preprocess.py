"""Tests for src/preprocess.py (synthetic signals + committed sample; no data/raw needed)."""
import mne
import numpy as np
import pytest

from src import config
from src.io_utils import load_eeg
from src.preprocess import clean

SAMPLE = config.DATA_SAMPLE / "sample_frontal8_raw.fif"
QC_KEYS = {"n_total", "n_kept", "retained_frac", "ica_used", "ica_excluded", "warnings",
           "notch_applied", "ica_eog_scores", "epoch_ptp_uv"}


def _synthetic(channels: list[str], seconds: float, sd_v: float, seed: int = 42) -> mne.io.RawArray:
    rng = np.random.default_rng(seed)
    n = int(seconds * 160)
    info = mne.create_info(channels, 160.0, "eeg")
    return mne.io.RawArray(rng.normal(0, sd_v, (len(channels), n)), info, verbose="ERROR")


@pytest.fixture(scope="module")
def sample_result():
    raw, _ = load_eeg(str(SAMPLE), "frontal8")
    return raw, *clean(raw, 60.0)


def test_qc_contract_keys_and_retained_frac(sample_result):
    _, epochs, qc = sample_result
    assert QC_KEYS <= set(qc)
    assert qc["n_kept"] == len(epochs)
    assert qc["retained_frac"] == pytest.approx(qc["n_kept"] / qc["n_total"])
    assert qc["n_total"] == 29                    # 61 s, 4 s windows, 2 s step → floor((61-4)/2)+1
    print("sample qc:", {k: qc[k] for k in ["n_kept", "n_total", "ica_excluded"]})


def test_frontal8_runs_ica_with_capped_exclusion(sample_result):
    _, _, qc = sample_result
    assert qc["ica_used"] is True
    assert len(qc["ica_eog_scores"]) == 7         # n_ch − 1 components
    assert len(qc["ica_excluded"]) <= config.PRESETS["frontal8"]["ica"]["max_exclude"]
    for comp in qc["ica_excluded"]:
        assert qc["ica_eog_scores"][comp] >= config.ICA_EOG_THRESHOLD


def test_muse4_runs_three_component_ica():
    raw = _synthetic(config.PRESETS["muse4"]["channels"], 20, 10e-6)
    _, qc = clean(raw, 60.0)
    assert qc["ica_used"] is True
    assert len(qc["ica_eog_scores"]) == 3
    assert len(qc["ica_excluded"]) <= 1


def test_unknown_montage_skips_ica():
    raw = _synthetic(["Fp1", "Fp2", "AF3", "AF4"], 20, 10e-6)
    _, qc = clean(raw, 60.0)
    assert qc["ica_used"] is False and qc["ica_excluded"] == []


def test_caller_raw_is_not_modified():
    raw, _ = load_eeg(str(SAMPLE), "frontal8")
    before = raw.get_data().copy()
    clean(raw, 60.0)
    np.testing.assert_array_equal(raw.get_data(), before)


def test_all_epochs_rejected_warns_not_crashes():
    raw = _synthetic(config.PRESETS["muse4"]["channels"], 10, 500e-6)
    epochs, qc = clean(raw, 60.0)
    assert len(epochs) == 0 and qc["n_kept"] == 0 and qc["retained_frac"] == 0.0
    assert f"Insufficient clean data: 0/{qc['n_total']} epochs passed rejection" in qc["warnings"]


def test_rejection_threshold_comes_from_config(monkeypatch):
    raw = _synthetic(["Fp1", "Fp2", "AF3", "AF4"], 20, 10e-6)
    _, qc_default = clean(raw, 60.0)
    monkeypatch.setattr(config, "REJECT_PTP_V", 1e-6)   # 1 µV: everything fails
    _, qc_strict = clean(raw, 60.0)
    assert qc_default["n_kept"] == qc_default["n_total"]
    assert qc_strict["n_kept"] == 0


def test_short_recording_raises():
    raw = _synthetic(["Fp1", "Fp2", "AF3", "AF4"], 3, 10e-6)
    with pytest.raises(ValueError, match="at least 4 s"):
        clean(raw, 60.0)


@pytest.mark.parametrize("line_freq, expected", [(30.0, True), (50.0, False), (60.0, False)])
def test_notch_only_below_lowpass(line_freq, expected):
    raw = _synthetic(["Fp1", "Fp2", "AF3", "AF4"], 10, 10e-6)
    _, qc = clean(raw, line_freq)
    assert qc["notch_applied"] is expected


def test_ica_failure_degrades_with_warning(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("forced failure")
    monkeypatch.setattr(mne.preprocessing.ICA, "fit", boom)
    raw = _synthetic(config.PRESETS["muse4"]["channels"], 20, 10e-6)
    epochs, qc = clean(raw, 60.0)
    assert qc["ica_used"] is False
    assert any("ICA failed" in w for w in qc["warnings"])
    assert len(epochs) > 0
