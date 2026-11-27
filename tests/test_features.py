"""Tests for src/features.py — synthetic 1/f signals with known rhythms + the committed sample."""
import mne
import numpy as np
import pytest

from src import config
from src.features import EPOCH_COLUMNS, SESSION_KEYS, extract, session_spectrum
from src.io_utils import load_eeg
from src.preprocess import clean

SFREQ = 160.0
FRONTAL8 = config.PRESETS["frontal8"]["channels"]
SAMPLE = config.DATA_SAMPLE / "sample_frontal8_raw.fif"


def _pink(n: int, exponent: float, rng: np.random.Generator) -> np.ndarray:
    """Noise with PSD ∝ 1/f^exponent (FFT shaping), unit variance."""
    spec = np.fft.rfft(rng.normal(size=n))
    f = np.fft.rfftfreq(n, 1 / SFREQ)
    f[0] = f[1]
    x = np.fft.irfft(spec / f ** (exponent / 2), n)
    return x / x.std()


def _epochs(signals: np.ndarray, channels: list[str] = FRONTAL8) -> mne.Epochs:
    raw = mne.io.RawArray(signals, mne.create_info(channels, SFREQ, "eeg"), verbose="ERROR")
    return mne.make_fixed_length_epochs(raw, duration=4.0, overlap=2.0, preload=True, verbose="ERROR")


def _synthetic(exponent: float = 1.5, rhythms: dict | None = None, seconds: float = 60,
               seed: int = 42, gains: list[float] | None = None) -> mne.Epochs:
    """8 channels of 1/f background (20 µV sd) + sinusoids {freq: amplitude µV}, per-channel gain on rhythms."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SFREQ)
    t = np.arange(n) / SFREQ
    gains = gains or [1.0] * 8
    sig = []
    for ch in range(8):
        x = 20e-6 * _pink(n, exponent, rng)
        for freq, amp in (rhythms or {}).items():
            x += gains[ch] * amp * 1e-6 * np.sin(2 * np.pi * freq * t + rng.uniform(0, 2 * np.pi))
        sig.append(x)
    return _epochs(np.array(sig))


def test_paf_recovers_10hz_within_half_hz():
    feats, _ = extract(_synthetic(rhythms={10.0: 15.0}), "frontal8")
    print("PAF:", feats["paf"], "fallback frac:", feats["paf_fallback_frac"])
    assert abs(feats["paf"] - 10.0) <= 0.5
    assert feats["paf_fallback"] is False
    assert feats["paf_fallback_frac"] == 0.0


@pytest.mark.parametrize("amp", [2.0, 6.0])
def test_tbr_osc_robust_to_slope_change(amp):
    """ADR-008 regression: excess-power TBR barely moves when only the 1/f slope changes."""
    rhythms = {6.0: amp, 20.0: amp}
    flat, _ = extract(_synthetic(exponent=1.0, rhythms=rhythms), "frontal8")
    steep, _ = extract(_synthetic(exponent=2.0, rhythms=rhythms), "frontal8")
    d_classic = abs(np.log(steep["tbr_classic"] / flat["tbr_classic"]))
    d_osc = abs(np.log(steep["tbr_osc"] / flat["tbr_osc"]))
    print(f"amp {amp}: tbr_classic {flat['tbr_classic']:.3f}->{steep['tbr_classic']:.3f} (|dlog| {d_classic:.3f}); "
          f"tbr_osc {flat['tbr_osc']:.3f}->{steep['tbr_osc']:.3f} (|dlog| {d_osc:.3f})")
    assert d_osc < 0.1
    assert d_osc < d_classic


def test_no_beta_rhythm_guard_direct():
    from src.features import _tbr_osc
    assert np.isnan(_tbr_osc(1.0, 0.04, 1.0))           # 4% < 5%
    assert _tbr_osc(1.0, 0.5, 1.0) == pytest.approx(2.0)


def test_no_beta_rhythm_gives_nan_and_warning(monkeypatch):
    from src.features import NO_BETA_WARNING
    monkeypatch.setattr(config, "TBR_MIN_BETA_EXC_FRAC", 1.01)   # excess can never exceed abs
    feats, per_epoch = extract(_synthetic(rhythms={6.0: 6.0, 20.0: 6.0}), "frontal8")
    assert np.isnan(feats["tbr_osc"]) and NO_BETA_WARNING in feats["warnings"]
    assert per_epoch["tbr_osc"].isna().all()
    assert np.isfinite(feats["tbr_classic"])


def test_faa_positive_when_right_alpha_larger():
    right = [ch in config.PRESETS["frontal8"]["faa_right"] for ch in FRONTAL8]
    gains = [2.0 if r else 1.0 for r in right]
    feats, _ = extract(_synthetic(rhythms={10.0: 10.0}, gains=gains), "frontal8")
    assert feats["faa"] > 0


def test_pure_1_over_f_uses_fallback_without_crash():
    # 300 s → PSD noise ~0.02 log10 units, far below min_peak_height 0.1, so no spurious peaks.
    feats, per_epoch = extract(_synthetic(rhythms=None, seconds=300), "frontal8")
    assert feats["paf_fallback"] is True and feats["paf_fallback_frac"] > 0.5
    assert config.PAF_COG_RANGE[0] <= feats["paf"] <= config.PAF_COG_RANGE[1]
    assert len(per_epoch) == feats["n_epochs"]


def test_flat_channel_gives_nan_and_warning_not_crash():
    ep = _synthetic(rhythms={10.0: 15.0})
    data = ep.get_data(copy=True)
    data[:, 0, :] = 0.0                                    # Fp1 flat
    bad = mne.EpochsArray(data, ep.info, verbose="ERROR")
    feats, _ = extract(bad, "frontal8")
    assert "FOOOF fit failed/poor on Fp1" in feats["warnings"]
    assert np.isfinite(feats["paf"]) and np.isfinite(feats["ap_exponent"])   # nanmedian over the rest


def test_zero_epochs_returns_nan_and_flag():
    ep = _synthetic(rhythms={10.0: 15.0})
    empty = ep.copy().drop(list(range(len(ep))), verbose="ERROR")
    feats, per_epoch = extract(empty, "frontal8")
    assert feats["insufficient_data"] is True and feats["n_epochs"] == 0
    assert all(np.isnan(feats[k]) for k in SESSION_KEYS if k != "paf_fallback")
    assert per_epoch.empty and list(per_epoch.columns) == EPOCH_COLUMNS


@pytest.fixture(scope="module")
def sample_feats():
    raw, _ = load_eeg(str(SAMPLE), "frontal8")
    epochs, _ = clean(raw, 60.0)
    return epochs, *extract(epochs, "frontal8")


def test_sample_keys_ranges_and_units(sample_feats):
    _, feats, per_epoch = sample_feats
    assert set(SESSION_KEYS) <= set(feats)
    assert 0 <= feats["fooof_r2"] <= 1
    assert config.PAF_PEAK_RANGE[0] <= feats["paf"] <= config.PAF_PEAK_RANGE[1]
    # µV² check: a missing ×1e12 conversion would give ~1e-11 here
    assert 1.0 < feats["alpha_abs"] < 1e4
    assert all(feats[f"{b}_abs"] > 0 for b in config.BANDS)
    assert list(per_epoch.columns) == EPOCH_COLUMNS and len(per_epoch) == feats["n_epochs"]
    assert "ap_exponent" not in per_epoch.columns                    # ADR-007: session-only
    print("sample alpha_abs µV²:", round(feats["alpha_abs"], 2))


def test_session_spectrum_shapes(sample_feats):
    epochs, _, _ = sample_feats
    spec = session_spectrum(epochs)
    assert spec["psd_uv2"].shape == (8, len(spec["freqs"])) == spec["ap_fit_uv2"].shape
    assert spec["freqs"][0] == pytest.approx(1.0) and spec["freqs"][-1] == pytest.approx(40.0)
