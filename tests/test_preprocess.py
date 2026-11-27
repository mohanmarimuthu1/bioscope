"""Tests for src/preprocess.py (synthetic signals + committed sample; no data/raw needed)."""
import mne
import numpy as np
import pytest

from src import config
from src.io_utils import load_eeg
from src.preprocess import clean

SAMPLE = config.DATA_SAMPLE / "sample_frontal8_raw.fif"
QC_KEYS = {"n_total", "n_kept", "retained_frac", "ica_used", "ica_excluded", "warnings",
           "notch_applied", "ica_eog_scores", "epoch_ptp_uv", "n_segments"}


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


# ---------------------------------------------------------------- ADR-012 segment-aware epoching
from src.preprocess import _segment_events  # noqa: E402


def test_continuous_file_events_match_mne():
    raw = load_eeg(str(SAMPLE), "frontal8")[0]
    ours, n_seg = _segment_events(raw)
    ref = mne.make_fixed_length_events(raw, duration=config.EPOCH_LENGTH_S, overlap=config.EPOCH_OVERLAP_S)
    assert n_seg == 1
    np.testing.assert_array_equal(ours, ref)


def test_concatenated_segments_epoch_per_segment_without_crossing():
    chans = config.PRESETS["frontal8"]["channels"]
    segs = [_synthetic(chans, s, 10e-6, seed=i) for i, s in enumerate([4.1, 9.0, 4.1])]
    cat = mne.concatenate_raws(segs, verbose="ERROR")
    cat.set_montage("standard_1020")
    events, n_seg = _segment_events(cat)
    assert n_seg == 3
    # 4.1 s → 1 epoch; 9.0 s → starts 0, 2, 4 (4+4 ≤ 9) → 3 epochs
    assert len(events) == 5
    ann = cat.annotations
    cuts = cat.time_as_index(ann.onset[ann.description == "BAD boundary"], origin=ann.orig_time)
    dur = int(config.EPOCH_LENGTH_S * 160)
    for s in events[:, 0] - cat.first_samp:
        assert not any(s < c < s + dur for c in cuts)
    epochs, qc = clean(cat, config.DATASET_LINE_FREQ)
    assert qc["n_segments"] == 3 and qc["n_total"] == 5
