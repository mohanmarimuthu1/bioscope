"""Tests for src/longitudinal.py with hand-computed values (§7.7)."""
import numpy as np
import pytest

from src import config, longitudinal as lg


def test_ema_hand_computed():
    # alpha 0.3: 80 → 0.3·90 + 0.7·80 = 83 → 0.3·70 + 0.7·83 = 79.1
    assert lg.ema([80, 90, 70]) == pytest.approx([80.0, 83.0, 79.1])


def test_baseline_mean_std_and_floor():
    b = lg.compute_baseline([80, 82, 84, 10])
    assert b["mean"] == pytest.approx(82.0) and b["std"] == pytest.approx(2.0)   # sd = 2.0 exactly
    flat = lg.compute_baseline([80, 80, 80, 99])
    assert flat["raw_std"] == 0.0 and flat["std"] == config.BASELINE_STD_FLOOR
    assert not b["provisional"] and lg.compute_baseline([80])["provisional"]


def test_bayesian_hand_computed():
    # prior N(80, 225); obs 80 sd 5 → var 1/(1/225+1/25) = 22.5, mean 80
    # next obs 90 sd 5 → var 1/(1/22.5+1/25) = 11.842, mean = 11.842·(80/22.5 + 90/25) = 84.737
    out = lg.bayesian_track([80, 90], [5, 5])
    assert out[0] == pytest.approx((80.0, np.sqrt(22.5)))
    assert out[1][0] == pytest.approx(84.7368, abs=1e-3)
    assert out[1][1] == pytest.approx(np.sqrt(1 / (1 / 22.5 + 1 / 25)))


def test_posterior_sd_monotone_decreasing_and_low_confidence_weighs_less():
    rng = np.random.default_rng(42)
    scores = list(rng.normal(80, 5, 13))
    sd = lg.obs_sd_from_confidence(list(rng.uniform(0.3, 1.0, 13)))
    post_sd = [s for _, s in lg.bayesian_track(scores, sd)]
    assert np.all(np.diff(post_sd) < 0)
    hi = lg.bayesian_track([80, 100], lg.obs_sd_from_confidence([1.0, 1.0]))[1][0]
    lo = lg.bayesian_track([80, 100], lg.obs_sd_from_confidence([1.0, 0.0]))[1][0]
    assert hi > lo > 80
    assert lg.obs_sd_from_confidence([1.0, 0.0]) == [5.0, 20.0]


def test_flag_on_jump_but_not_baseline():
    scores = [80, 82, 84, 83, 60]
    b = lg.compute_baseline(scores)              # mean 82, std 2
    assert lg.flag_shifts(scores, b) == [False, False, False, False, True]
    # a wild baseline session is never flagged itself
    assert lg.flag_shifts([80, 20, 84], lg.compute_baseline([80, 20, 84]))[:3] == [False] * 3


def test_deltas_vs_baseline():
    assert lg.deltas_vs_baseline([1, 2, 3, 5]) == pytest.approx([-1, 0, 1, 3])
    assert np.isnan(lg.deltas_vs_baseline([np.nan, np.nan, np.nan, 1])[3])


def test_rejects_none_and_mismatch():
    with pytest.raises(ValueError):
        lg.ema([80, None])
    with pytest.raises(ValueError):
        lg.bayesian_track([80, 81], [5])
    with pytest.raises(ValueError):
        lg.compute_baseline([])
