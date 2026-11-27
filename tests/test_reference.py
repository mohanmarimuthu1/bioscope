"""Tests for src/reference.py (ADR-010) and the built models/reference.json."""
import json

import numpy as np
import pytest
from scipy.stats import norm

from src import config, reference


def test_transforms_handle_zero_and_domain():
    assert reference.transform("alpha_exc", 0.0) == 0.0          # ln1p(0) = 0, no -inf
    assert reference.transform("tbr_osc", 0.0) == 0.0
    assert reference.transform("tbr_classic", np.e) == pytest.approx(1.0)
    assert np.isnan(reference.transform("tbr_classic", 0.0))     # ln(0) -> NaN, not -inf
    assert reference.transform("paf", 10.2) == 10.2
    assert np.isnan(reference.transform("paf", np.nan))


def test_build_entry_picks_method_by_skew():
    rng = np.random.default_rng(42)
    normal = reference.build_entry("paf", list(rng.normal(10, 1, 200)))
    skewed = reference.build_entry("paf", list(rng.lognormal(0, 1, 200)))
    assert normal["method"] == "zscore" and "values" not in normal
    assert skewed["method"] == "percentile" and len(skewed["values"]) == 200
    assert skewed["values"] == sorted(skewed["values"])


def test_build_entry_drops_nan_and_rejects_tiny_sample():
    e = reference.build_entry("paf", [9.0, 10.0, np.nan, 11.0])
    assert e["n"] == 3
    with pytest.raises(ValueError):
        reference.build_entry("paf", [9.0, np.nan])


def test_zscore_at_mean_is_zero():
    e = reference.build_entry("paf", [9.0, 10.0, 11.0])
    assert reference.to_z("paf", 10.0, e) == pytest.approx(0.0)
    assert reference.to_z("paf", 11.0, e) == pytest.approx(1.0)


def _pct_entry(values):
    t = np.sort(np.asarray(values, dtype=float))
    return {"transform": "none", "method": "percentile", "mean": float(t.mean()),
            "std": float(t.std(ddof=1)), "n": len(t), "skew": 2.0,
            "min": float(t[0]), "max": float(t[-1]), "values": list(t)}


def test_percentile_inside_range_uses_midrank():
    e = _pct_entry(range(1, 10))                       # 1..9, n = 9
    assert reference.to_z("paf", 5.0, e) == pytest.approx(0.0)          # rank 5 / 10
    assert reference.to_z("paf", 9.0, e) == pytest.approx(norm.ppf(9 / 10))
    assert reference.to_z("paf", 4.5, e) == pytest.approx(norm.ppf(4.5 / 10))


def test_percentile_outside_range_takes_larger_and_caps():
    e = _pct_entry(range(1, 10))                       # mean 5, std ~2.74
    z_near = reference.to_z("paf", 9.5, e)             # just above max: larger of pct / param
    assert z_near == pytest.approx(max(norm.ppf(9.5 / 10), (9.5 - 5) / e["std"]))
    assert reference.to_z("paf", 100.0, e) == config.PERCENTILE_Z_CAP   # param z ~34.7 -> capped
    assert reference.to_z("paf", -100.0, e) == -config.PERCENTILE_Z_CAP
    assert reference.to_z("paf", 0.9, e) == pytest.approx(norm.ppf(0.5 / 10))  # pct larger than param


def test_to_z_nan_input_is_nan():
    e = reference.build_entry("paf", [9.0, 10.0, 11.0])
    assert np.isnan(reference.to_z("paf", np.nan, e))


def test_leak_guard():
    reference.assert_no_leak(["S001", "S050"])
    with pytest.raises(AssertionError):
        reference.assert_no_leak(["S001", config.DEMO_SUBJECT])
    with pytest.raises(AssertionError):
        reference.assert_no_leak(["S061"])


# ---------------------------------------------------------------- built artefact
needs_ref = pytest.mark.skipif(not config.REFERENCE_PATH.exists(), reason="reference.json not built")


@needs_ref
def test_reference_json_cells_and_no_leak():
    ref = json.loads(config.REFERENCE_PATH.read_text(encoding="utf-8"))
    for preset in config.PRESETS:
        for cond in config.CONDITIONS:
            cell = ref["presets"][preset][cond]
            used = cell["subjects_used"]
            reference.assert_no_leak(used)
            assert set(used) <= set(config.REFERENCE_SUBJECTS)
            assert not set(used) & {s["subject"] for s in cell["subjects_skipped"]}
            assert set(cell["features"]) == set(config.REFERENCE_TRANSFORMS)
            for e in cell["features"].values():
                assert e["std"] > 0 and e["n"] >= 30
                assert ("values" in e) == (e["method"] == "percentile")


@needs_ref
def test_load_reference_and_sanity():
    eo = reference.load_reference("eyes_open", "frontal8")
    ec = reference.load_reference("eyes_closed", "frontal8")
    assert 9.0 <= eo["paf"]["mean"] <= 11.0
    assert ec["alpha_exc"]["mean"] > eo["alpha_exc"]["mean"]      # ln1p scale, monotone
    with pytest.raises(ValueError):
        reference.load_reference("eyes_open", "muse8")
