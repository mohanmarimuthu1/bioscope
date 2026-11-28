"""SQLite session store (stdlib sqlite3; CLAUDE.md §6, ADR-012).

WHAT:  save_session(record) → row id; load_subject(subject_id) → DataFrame in session order;
       list_subjects() → sorted ids; delete_subject(subject_id) for idempotent demo seeding.
WHY:   Longitudinal tracking needs every session's features, QC and score kept together.
       One table, JSON columns: the score dict is stored whole, so the UI can re-explain old sessions.
CAVEATS:
  - JSON has no NaN/inf: they are stored as null and come back as None (callers treat None as missing).
    numpy scalars/arrays are converted to Python types.
  - record keys: subject_id, session_index, label, condition, preset, source, recorded_at (str or None),
    features, qc, score (dicts); optional extras (dict: spectrum + validation-model summary for the UI, ADR-014).
    composite/confidence are copied from score for quick queries.
  - A DB created before ADR-014 gains the extras_json column on first connect; its rows load with extras = {}.
"""
import json
import logging
import math
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src import config

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id TEXT NOT NULL,
    session_index INTEGER NOT NULL,
    label TEXT,
    condition TEXT NOT NULL,
    preset TEXT NOT NULL,
    source TEXT,
    recorded_at TEXT,
    composite REAL,
    confidence REAL,
    features_json TEXT NOT NULL,
    qc_json TEXT NOT NULL,
    score_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    extras_json TEXT NOT NULL DEFAULT '{}'
)"""
_JSON_COLS = {"features_json": "features", "qc_json": "qc", "score_json": "score", "extras_json": "extras"}


def _clean(obj):
    """Recursively make obj JSON-safe: NaN/inf → None, numpy → Python."""
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, np.ndarray)):
        return [_clean(v) for v in list(obj)]
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        return float(obj) if math.isfinite(float(obj)) else None
    return obj


def _dumps(obj) -> str:
    return json.dumps(_clean(obj), allow_nan=False)


def _connect(db_path: Path | str | None) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path or config.DB_PATH))
    con.execute(_SCHEMA)
    cols = {row[1] for row in con.execute("PRAGMA table_info(sessions)")}
    if "extras_json" not in cols:                      # ADR-014: migrate a pre-extras DB in place
        con.execute("ALTER TABLE sessions ADD COLUMN extras_json TEXT NOT NULL DEFAULT '{}'")
        con.commit()
        log.info("db: added extras_json column (ADR-014)")
    return con


def save_session(record: dict, db_path: Path | str | None = None) -> int:
    """Insert one session; returns its row id."""
    score = record.get("score") or {}
    row = (record["subject_id"], int(record["session_index"]), record.get("label"), record["condition"],
           record["preset"], record.get("source"), record.get("recorded_at"),
           _clean(score.get("composite")), _clean(score.get("confidence")),
           _dumps(record.get("features", {})), _dumps(record.get("qc", {})), _dumps(score),
           datetime.now().isoformat(timespec="seconds"), _dumps(record.get("extras") or {}))
    with _connect(db_path) as con:
        cur = con.execute(
            "INSERT INTO sessions (subject_id, session_index, label, condition, preset, source, recorded_at,"
            " composite, confidence, features_json, qc_json, score_json, created_at, extras_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", row)
        rid = int(cur.lastrowid)
    con.close()
    log.info("saved session %s #%s (id %d)", record["subject_id"], record["session_index"], rid)
    return rid


def load_subject(subject_id: str, db_path: Path | str | None = None) -> pd.DataFrame:
    """All sessions of one subject ordered by session_index; JSON columns parsed into dicts."""
    con = _connect(db_path)
    df = pd.read_sql_query("SELECT * FROM sessions WHERE subject_id = ? ORDER BY session_index, id",
                           con, params=(subject_id,))
    con.close()
    for col, name in _JSON_COLS.items():
        df[name] = df.pop(col).map(json.loads) if len(df) else pd.Series(dtype=object)
    df["composite"] = df["composite"].astype(object).where(df["composite"].notna(), None)
    return df


def list_subjects(db_path: Path | str | None = None) -> list[str]:
    con = _connect(db_path)
    rows = con.execute("SELECT DISTINCT subject_id FROM sessions ORDER BY subject_id").fetchall()
    con.close()
    return [r[0] for r in rows]


def delete_subject(subject_id: str, db_path: Path | str | None = None) -> int:
    """Delete all sessions of a subject; returns the number of rows removed."""
    with _connect(db_path) as con:
        n = con.execute("DELETE FROM sessions WHERE subject_id = ?", (subject_id,)).rowcount
    con.close()
    return int(n)
