"""Tests for src/ml_sanity.py: predictions on real S060 data, SHAP shape/additivity, no pickled explainer, leak guard."""
import logging
import warnings

import joblib
import mne
import numpy as np
import pandas as pd
import pytest

from src import config, features, io_utils, ml_sanity, preprocess

mne.set_log_level("ERROR")
logging.disable(logging.WARNING)
warnings.filterwarnings("ignore")

needs_model = pytest.mark.skipif(not config.MODEL_PATH.exists(), reason="model not trained")
SAMPLE = config.DATA_SAMPLE / "sample_frontal8_raw.fif"          # S060 R01, eyes open (committed)
S060_R02 = config.DATA_RAW / "S060" / "S060R02.edf"              # eyes closed (downloaded, gitignored)


def _per_epoch(path) -> pd.DataFrame:
    raw, _ = io_utils.load_eeg(str(path), config.ML_PRESET)
    epochs, _ = preprocess.clean(raw, config.DATASET_LINE_FREQ)
    return features.extract(epochs, config.ML_PRESET)[1]


@pytest.fixture(scope="module")
def eo_table() -> pd.DataFrame:
    return _per_epoch(SAMPLE)


@needs_model
def test_eyes_open_sample_below_half(eo_table):
    res = ml_sanity.predict(eo_table)
    print(f"S060 R01 (EO) p_eyes_closed = {res['p_eyes_closed']:.3f} over {len(eo_table)} epochs")
    assert res["p_eyes_closed"] < 0.5
    assert len(res["p_epochs"]) == len(eo_table)
    assert res["warnings"] == []


@needs_model
@pytest.mark.skipif(not S060_R02.exists(), reason="raw S060 R02 not downloaded")
def test_eyes_closed_above_half():
    res = ml_sanity.predict(_per_epoch(S060_R02))
    print(f"S060 R02 (EC) p_eyes_closed = {res['p_eyes_closed']:.3f}")
    assert res["p_eyes_closed"] > 0.5


@needs_model
def test_shap_shape_and_additivity(eo_table):
    res = ml_sanity.predict(eo_table)
    assert res["shap_values"].shape == (len(eo_table), len(ml_sanity.FEATURES)) == (len(eo_table), 17)
    assert res["feature_names"] == ml_sanity.FEATURES
    margin = ml_sanity.load_model()["lgbm"].predict_proba(eo_table[ml_sanity.FEATURES].astype(float), raw_score=True)
    np.testing.assert_allclose(res["shap_values"].sum(axis=1) + res["base_value"], margin, atol=1e-6)


@needs_model
def test_artifact_has_no_explainer_and_no_leak():
    art = joblib.load(config.MODEL_PATH)
    assert not any(type(v).__module__.startswith("shap") for v in art.values())
    train = set(art["train_subjects"])
    held_out = {config.DEMO_SUBJECT, config.DEMO_LONGITUDINAL_SUBJECT} | set(config.HOLDOUT_SUBJECTS)
    assert train <= set(config.REFERENCE_SUBJECTS)
    assert not train & held_out
    assert art["preset"] == config.ML_PRESET and art["feature_names"] == ml_sanity.FEATURES


@needs_model
def test_empty_table_no_crash():
    res = ml_sanity.predict(pd.DataFrame(columns=features.EPOCH_COLUMNS))
    assert res["p_eyes_closed"] is None
    assert res["shap_values"].shape == (0, 17)
    assert res["warnings"] == [ml_sanity.EMPTY_WARNING]


@needs_model
def test_missing_column_raises(eo_table):
    with pytest.raises(ValueError, match="alpha_osc"):
        ml_sanity.predict(eo_table.drop(columns=["alpha_osc"]))


def test_lr_log_power_only_touches_power_columns():
    x = np.full((2, len(ml_sanity.FEATURES)), 3.0)
    out = ml_sanity._log_power(x)
    for i, name in enumerate(ml_sanity.FEATURES):
        expected = np.log1p(3.0) if name.endswith(("_abs", "_exc")) else 3.0
        assert out[0, i] == pytest.approx(expected), name
