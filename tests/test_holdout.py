"""Tests for models/holdout.json (P6b): leak-free subject sets, consistent counts, values in range."""
import json

import joblib
import pytest

from src import config

pytestmark = pytest.mark.skipif(not config.HOLDOUT_PATH.exists(), reason="holdout.json not built")


@pytest.fixture(scope="module")
def holdout() -> dict:
    return json.loads(config.HOLDOUT_PATH.read_text(encoding="utf-8"))


def test_holdout_subjects_disjoint_from_reference_and_model(holdout):
    hold = set(holdout["subjects"])
    assert hold == set(config.HOLDOUT_SUBJECTS) and len(hold) == 49
    ref = json.loads(config.REFERENCE_PATH.read_text(encoding="utf-8"))
    used = {s for cells in ref["presets"].values() for c in cells.values() for s in c["subjects_used"]}
    train = set(joblib.load(config.MODEL_PATH)["train_subjects"])
    assert not hold & used
    assert not hold & train
    assert not hold & {config.DEMO_SUBJECT, config.DEMO_LONGITUDINAL_SUBJECT}


def test_counts_add_up(holdout):
    assert holdout["n_recordings"] == 2 * len(holdout["subjects"]) == 98
    assert holdout["n_ok"] + len(holdout["crashes"]) == holdout["n_recordings"]
    for cond, f in holdout["features"].items():
        assert f["n_recordings"] == 49, cond
    s = holdout["scores"]
    assert s["eo_vs_eo"]["n"] + s["eo_vs_eo"]["n_unscorable"] == holdout["features"]["eyes_open"]["n_recordings"]
    assert s["ec_vs_ec"]["n"] + s["ec_vs_ec"]["n_unscorable"] == holdout["features"]["eyes_closed"]["n_recordings"]


def test_metrics_in_range(holdout):
    for name in ("lgbm", "lr"):
        m = holdout["ml"][name]
        for k in ("acc", "auc", "rec_acc", "paired_acc"):
            assert 0.0 <= m[k] <= 1.0, (name, k)
        lo, hi = m["auc_ci95"]
        assert 0.0 <= lo <= m["auc"] <= hi <= 1.0
        assert 1 / (1 + m["permutation"]["n_permutations"]) <= m["permutation"]["p_value"] <= 1.0
    for cell in holdout["scores"].values():
        assert 0.0 <= cell["q1"] <= cell["median"] <= cell["q3"] <= 100.0
