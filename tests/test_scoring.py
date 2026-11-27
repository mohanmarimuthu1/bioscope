"""Tests for src/scoring.py (§7.6, ADR-011). Uses the committed models/reference.json."""
import logging
import warnings

import mne
import numpy as np
import pytest

from src import config, features, io_utils, preprocess, reference, scoring

mne.set_log_level("ERROR")
needs_ref = pytest.mark.skipif(not config.REFERENCE_PATH.exists(), reason="reference.json not built")
pytestmark = needs_ref

INV = {"none": lambda t: t, "ln": np.exp, "ln1p": np.expm1}
SAMPLE = config.DATA_SAMPLE / "sample_frontal8_raw.fif"
S060_R02 = config.DATA_RAW / "S060" / "S060R02.edf"
S060_R01 = config.DATA_RAW / "S060" / "S060R01.edf"


def _typical(condition="eyes_open", preset="frontal8") -> tuple[dict, dict]:
    """Features at the reference mean (back-transformed) and perfect QC."""
    ref = reference.load_reference(condition, preset)
    feats = {f: float(INV[e["transform"]](e["mean"] if e["method"] == "zscore" else np.median(e["values"])))
             for f, e in ref.items()}
    feats.update(fooof_r2=1.0, paf_fallback_frac=0.0, hibeta_abs=1.0, insufficient_data=False,
                 n_epochs=29, warnings=[])
    qc = {"n_total": 29, "n_kept": 29, "retained_frac": 1.0, "duration_s": 61.0, "warnings": []}
    return feats, qc


def _session(path, preset):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw, meta = io_utils.load_eeg(str(path), preset)
        ep, qc = preprocess.clean(raw, config.DATASET_LINE_FREQ)
        qc["duration_s"] = meta["duration_s"]
        f, _ = features.extract(ep, preset)
    return f, qc


def test_weights_sum_to_one():
    assert sum(config.WEIGHTS.values()) == pytest.approx(1.0)
    assert set(config.WEIGHTS) == set(config.DIMENSIONS) | {"signal_quality"}


@pytest.mark.parametrize("preset", list(config.PRESETS))
@pytest.mark.parametrize("condition", config.CONDITIONS)
def test_typical_session_scores_near_100(condition, preset):
    f, qc = _typical(condition, preset)
    r = scoring.score(f, qc, condition, preset)
    assert all(abs(z) < 0.15 for z in r["feature_z"].values()), r["feature_z"]
    assert all(s > 97 for s in r["feature_scores"].values())
    assert r["confidence"] == pytest.approx(1.0)
    assert r["composite"] > 97 and r["explanations"] == []


def test_bounds_on_extreme_values():
    f, qc = _typical()
    f.update(paf=30.0, alpha_exc=1e6, faa=-50.0, hibeta_exc=0.0, ap_exponent=9.0, tbr_osc=1e4, fooof_r2=0.1)
    qc.update(retained_frac=0.2, n_kept=3, duration_s=10.0)
    r = scoring.score(f, qc, "eyes_open", "frontal8")
    assert 0 <= r["composite"] <= 100 and 0 <= r["confidence"] <= 1
    assert all(0 <= v <= 100 for v in r["dimensions"].values())
    assert any("Low clean data" in w for w in r["warnings"])
    assert any("SD" in e for e in r["explanations"])


def test_nan_tbr_uses_paf_only_with_warning():
    f, qc = _typical()
    f["tbr_osc"] = np.nan
    f["paf"] = f["paf"] + 1.0
    r = scoring.score(f, qc, "eyes_open", "frontal8")
    assert r["dimensions"]["attention"] == pytest.approx(r["feature_scores"]["paf"])
    assert "tbr_osc" not in r["feature_scores"]
    assert any("Attention uses peak alpha frequency only" in w for w in r["warnings"])


def test_missing_feature_warns_and_uses_rest():
    f, qc = _typical()
    f["faa"] = np.nan
    r = scoring.score(f, qc, "eyes_open", "frontal8")
    assert r["dimensions"]["relaxation"] == pytest.approx(r["feature_scores"]["alpha_exc"])
    assert any(w.startswith("faa missing") for w in r["warnings"])


def test_whole_dimension_missing_renormalises():
    f, qc = _typical()
    f["hibeta_exc"] = f["ap_exponent"] = np.nan
    r = scoring.score(f, qc, "eyes_open", "frontal8")
    assert r["dimensions"]["load"] is None
    w = {d: config.WEIGHTS[d] for d in r["dimensions"] if r["dimensions"][d] is not None}
    expect = sum(w[d] * r["dimensions"][d] for d in w) / sum(w.values())
    assert r["composite"] == pytest.approx(expect)
    assert any("weights renormalised" in x for x in r["warnings"])


def test_missing_duration_warns():
    f, qc = _typical()
    del qc["duration_s"]
    r = scoring.score(f, qc, "eyes_open", "frontal8")
    assert r["confidence"] == pytest.approx(1.0 - config.CONF_W_DURATION)
    assert any("duration unknown" in w for w in r["warnings"])


def test_bad_condition_or_preset_raises():
    f, qc = _typical()
    with pytest.raises(ValueError):
        scoring.score(f, qc, "eyes_shut", "frontal8")
    with pytest.raises(ValueError):
        scoring.score(f, qc, "eyes_open", "muse8")


def test_zero_epochs_end_to_end():
    """500 µV synthetic noise → every epoch rejected → no score, confidence 0."""
    rng = np.random.default_rng(42)
    chans = config.PRESETS["frontal8"]["channels"]
    info = mne.create_info(chans, config.DATASET_SFREQ, "eeg")
    raw = mne.io.RawArray(rng.normal(0, 500e-6, (len(chans), int(60 * config.DATASET_SFREQ))), info)
    raw.set_montage("standard_1020")
    logging.disable(logging.WARNING)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ep, qc = preprocess.clean(raw, config.DATASET_LINE_FREQ)
        f, _ = features.extract(ep, "frontal8")
    logging.disable(logging.NOTSET)
    qc["duration_s"] = 60.0
    r = scoring.score(f, qc, "eyes_open", "frontal8")
    assert qc["n_kept"] == 0
    assert r["composite"] is None and r["confidence"] == 0.0
    assert all(v is None for v in r["dimensions"].values())
    assert any(w.startswith("Insufficient clean data: 0/") for w in r["warnings"])


@pytest.mark.skipif(not SAMPLE.exists(), reason="sample missing")
def test_sample_scores_with_frontal8():
    f, qc = _session(SAMPLE, "frontal8")
    r = scoring.score(f, qc, "eyes_open", "frontal8")
    assert 0 <= r["composite"] <= 100 and 0 < r["confidence"] <= 1
    assert set(r["named_metrics"]) == set(scoring.NAMED_METRICS)


@pytest.mark.skipif(not (S060_R01.exists() and S060_R02.exists()), reason="raw S060 not downloaded")
@pytest.mark.parametrize("preset", list(config.PRESETS))
def test_s060_eyes_open_more_typical_vs_eo_reference(preset):
    eo = scoring.score(*_session(S060_R01, preset), "eyes_open", preset)
    ec = scoring.score(*_session(S060_R02, preset), "eyes_open", preset)
    assert eo["composite"] > ec["composite"]
    assert ec["feature_z"]["alpha_exc"] > 2        # eyes-closed alpha is atypical for eyes-open


def test_none_feature_value_treated_as_missing():
    """Regression: a None value (e.g. read back from the DB) crashed to_z with TypeError."""
    f, qc = _typical()
    f["faa"] = None
    r = scoring.score(f, qc, "eyes_open", "frontal8")
    assert "faa" not in r["feature_z"] and r["composite"] is not None


def test_all_eeg_features_missing_gives_no_composite():
    """Regression: signal quality alone produced composite 100."""
    f, qc = _typical()
    for k in [k for v in config.DIMENSIONS.values() for k in v]:
        f[k] = np.nan
    r = scoring.score(f, qc, "eyes_open", "frontal8")
    assert r["composite"] is None
    assert any("composite not computed" in w for w in r["warnings"])
