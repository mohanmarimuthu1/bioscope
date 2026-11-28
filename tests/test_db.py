"""Tests for src/db.py: None-safe JSON round trip in a temporary database."""
import numpy as np
import pytest

from src import db


def _record(i, composite=80.0, subject="T001"):
    return {"subject_id": subject, "session_index": i, "label": f"s{i}", "condition": "eyes_open",
            "preset": "frontal8", "source": f"s{i}.fif", "recorded_at": None,
            "features": {"paf": np.float64(9.8), "tbr_osc": np.nan, "faa": None, "flag": np.bool_(True),
                         "warnings": ["no beta rhythm above background"]},
            "qc": {"n_kept": np.int64(14), "epoch_ptp_uv": np.array([12.5, np.inf]), "retained_frac": 0.93},
            "score": {"composite": composite, "confidence": 0.9, "dimensions": {"attention": None, "load": 88.0},
                      "feature_z": {"paf": float("-inf")}}}


def test_round_trip_none_safe(tmp_path):
    p = tmp_path / "t.db"
    rid = db.save_session(_record(1), db_path=p)
    df = db.load_subject("T001", db_path=p)
    assert rid == 1 and len(df) == 1
    r = df.iloc[0]
    assert r["features"]["paf"] == pytest.approx(9.8)
    assert r["features"]["tbr_osc"] is None and r["features"]["faa"] is None
    assert r["features"]["flag"] is True and r["qc"]["n_kept"] == 14
    assert r["qc"]["epoch_ptp_uv"] == [12.5, None]
    assert r["score"]["dimensions"]["attention"] is None and r["score"]["feature_z"]["paf"] is None
    assert r["composite"] == pytest.approx(80.0) and r["confidence"] == pytest.approx(0.9)


def test_none_composite_and_ordering(tmp_path):
    p = tmp_path / "t.db"
    for i, c in [(3, 70.0), (1, 80.0), (2, None)]:
        db.save_session(_record(i, composite=c), db_path=p)
    df = db.load_subject("T001", db_path=p)
    assert df["session_index"].tolist() == [1, 2, 3]
    assert df["composite"].tolist() == [80.0, None, 70.0]


def test_list_and_delete(tmp_path):
    p = tmp_path / "t.db"
    db.save_session(_record(1, subject="B"), db_path=p)
    db.save_session(_record(1, subject="A"), db_path=p)
    assert db.list_subjects(db_path=p) == ["A", "B"]
    assert db.delete_subject("A", db_path=p) == 1
    assert db.list_subjects(db_path=p) == ["B"]
    assert len(db.load_subject("missing", db_path=p)) == 0


def test_extras_round_trip_and_default(tmp_path):
    p = tmp_path / "t.db"
    rec = _record(1)
    rec["extras"] = {"spectrum": {"freqs": np.array([1.0, 1.5]), "psd": [[np.nan, 2.0]]}, "ml": {"p_eyes_closed": np.float64(0.2)}}
    db.save_session(rec, db_path=p)
    db.save_session(_record(2), db_path=p)                       # no extras key
    df = db.load_subject("T001", db_path=p)
    assert df["extras"].iloc[0] == {"spectrum": {"freqs": [1.0, 1.5], "psd": [[None, 2.0]]}, "ml": {"p_eyes_closed": 0.2}}
    assert df["extras"].iloc[1] == {}


def test_pre_adr014_db_is_migrated(tmp_path):
    import sqlite3
    p = tmp_path / "old.db"
    con = sqlite3.connect(p)
    con.execute(db._SCHEMA.replace(",\n    extras_json TEXT NOT NULL DEFAULT '{}'", ""))
    con.execute("INSERT INTO sessions (subject_id, session_index, condition, preset, features_json, qc_json, score_json, created_at)"
                " VALUES ('OLD', 1, 'eyes_open', 'frontal8', '{}', '{}', '{}', 'x')")
    con.commit()
    con.close()
    df = db.load_subject("OLD", db_path=p)
    assert df["extras"].tolist() == [{}]
    db.save_session(_record(2, subject="OLD"), db_path=p)
    assert len(db.load_subject("OLD", db_path=p)) == 2
