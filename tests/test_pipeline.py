"""Tests for src/pipeline.py: sample run, friendly errors, 0-epoch path, save indexing, demo seeding reproduces P5."""
import logging
import warnings

import mne
import numpy as np
import pytest

from src import config, db, pipeline

mne.set_log_level("ERROR")
logging.disable(logging.WARNING)
warnings.filterwarnings("ignore")

SAMPLE = config.DATA_SAMPLE / "sample_frontal8_raw.fif"
# DEVLOG 2026-11-27 22:02 (P5): composites of the 13 S051 demo sessions from scripts/build_demo_sessions.py
P5_COMPOSITES = [87.0, 83.5, 82.1, 85.1, 85.6, 86.6, 82.8, 84.8, 85.9, 85.4, 82.6, 79.8, 84.8]


@pytest.fixture(scope="module")
def sample_result() -> dict:
    return pipeline.run(SAMPLE, "frontal8", "eyes_open", 60.0)


def test_sample_run_complete_and_fast(sample_result):
    r = sample_result
    print(f"sample: composite {r['score']['composite']:.1f}, p_EC {r['ml']['p_eyes_closed']:.3f}, timings {r['timings_s']}")
    assert 0 <= r["score"]["composite"] <= 100
    assert r["ml"]["available"] and len(r["ml"]["mean_shap"]) == 17
    assert len(r["spectrum"]["ch_names"]) == 8 and len(r["spectrum"]["psd_uv2"][0]) == len(r["spectrum"]["freqs"])
    assert r["timings_s"]["total"] < 10.0


def test_bad_extension(tmp_path):
    f = tmp_path / "x.csv"
    f.write_text("a,b")
    with pytest.raises(pipeline.PipelineError, match="Unsupported file type '.csv'"):
        pipeline.run(f, "frontal8", "eyes_open", 60.0)


def test_missing_channels_listed():
    with pytest.raises(pipeline.PipelineError, match="AF7"):
        pipeline.run(SAMPLE, "muse4", "eyes_open", 60.0)


def test_too_short(tmp_path):
    raw = mne.io.read_raw_fif(SAMPLE, preload=True).crop(0, 2.0)
    f = tmp_path / "short_raw.fif"
    raw.save(f)
    with pytest.raises(pipeline.PipelineError, match="too short"):
        pipeline.run(f, "frontal8", "eyes_open", 60.0)


def test_zero_clean_epochs_is_not_an_error(tmp_path):
    ch = config.PRESETS["frontal8"]["channels"]
    rng = np.random.default_rng(config.RANDOM_STATE)
    data = rng.normal(0, 500e-6, (len(ch), int(30 * config.DATASET_SFREQ)))     # 500 µV noise: every epoch rejected
    f = tmp_path / "noisy_raw.fif"
    mne.io.RawArray(data, mne.create_info(ch, config.DATASET_SFREQ, "eeg")).save(f)
    r = pipeline.run(f, "frontal8", "eyes_open", 60.0)
    assert r["score"]["composite"] is None
    assert r["ml"]["available"] is False and r["spectrum"] == {}
    assert any("Insufficient clean data" in w for w in r["score"]["warnings"])


def test_save_increments_index_and_stores_extras(sample_result, tmp_path):
    p = tmp_path / "t.db"
    pipeline.save(sample_result, "T1", "first", "sample", db_path=p)
    pipeline.save(sample_result, " T1 ", "second", "sample", db_path=p)
    df = db.load_subject("T1", db_path=p)
    assert df["session_index"].tolist() == [1, 2]
    assert df["extras"].iloc[0]["ml"]["available"] is True
    with pytest.raises(pipeline.PipelineError):
        pipeline.save(sample_result, "  ", "x", "sample", db_path=p)


def test_demo_label():
    assert pipeline.demo_label(config.DATA_DEMO / "S051_s01_R01_raw.fif") == "s01 R01 eyes-open rest"
    assert pipeline.demo_label(config.DATA_DEMO / "S051_s07_R08_raw.fif") == "s07 R08 T0 rest blocks"


def test_seed_demo_reproduces_p5(tmp_path):
    p = tmp_path / "seed.db"
    assert pipeline.seed_demo(db_path=p) == 13
    df = db.load_subject(config.DEMO_LONGITUDINAL_SUBJECT, db_path=p)
    got = [round(c, 1) for c in df["composite"]]
    print("seeded composites:", got)
    assert got == P5_COMPOSITES
