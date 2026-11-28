"""pipeline — one recording end to end, shared by the Upload page, demo seeding and tests (P7).

WHAT:  run(path, preset, condition, line_freq, progress) → result dict:
         meta, qc, features, per_epoch, score, spectrum, ml, timings_s.
       save(result, subject_id, label, source) → DB row id (next session_index for that subject).
       seed_demo() → re-seeds the longitudinal demo subject (S051) from the committed data/demo/*.fif.
WHY:   One code path for every caller, so the UI shows exactly what the scripts and tests compute. No streamlit here.
CAVEATS:
  - User-facing problems (wrong extension, missing channels, file shorter than one epoch) raise PipelineError with a
    plain-language message. 0 clean epochs is NOT an error: score() returns composite None and a warning.
  - ml is computed for frontal8 only (the validation model's preset); otherwise ml = {"available": False, ...}.
  - p_eyes_closed is a direction, not a calibrated probability (LightGBM is overconfident; see DEVLOG 2026-11-28).
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Callable

import numpy as np

from src import config, db, features, io_utils, ml_sanity, preprocess, scoring

log = logging.getLogger(__name__)

ALLOWED_SUFFIXES = (".edf", ".fif")
STEPS = ("Load file", "Clean signal (filter, ICA, epochs)", "Extract features", "Score vs reference",
         "Eyes-open/closed check")
_DEMO_NAME = re.compile(r"_(s\d{2})_(R\d{2})_raw\.fif$")


class PipelineError(Exception):
    """A problem the user can fix (file type, channels, length). Message is safe to show as is."""


def _sig(values, digits: int = 4) -> list:
    """Round to `digits` significant figures for compact JSON storage (NaN kept; db stores it as null)."""
    arr = np.asarray(values, dtype=float)
    out = np.array([float(f"{v:.{digits}g}") if np.isfinite(v) else np.nan for v in arr.ravel()]).reshape(arr.shape)
    return out.tolist()


def _spectrum(epochs) -> dict:
    spec = features.session_spectrum(epochs)
    return {"freqs": _sig(spec["freqs"]), "psd_uv2": _sig(spec["psd_uv2"]),
            "ap_fit_uv2": _sig(spec["ap_fit_uv2"]), "ch_names": spec["ch_names"]}


def _ml(per_epoch, preset: str) -> dict:
    if preset != config.ML_PRESET:
        return {"available": False, "reason": f"Validation model is trained on {config.ML_PRESET} only"}
    res = ml_sanity.predict(per_epoch)
    if res["p_eyes_closed"] is None:
        return {"available": False, "reason": res["warnings"][0]}
    return {"available": True, "p_eyes_closed": res["p_eyes_closed"], "n_epochs": len(res["p_epochs"]),
            "base_value": res["base_value"], "feature_names": res["feature_names"],
            "mean_shap": np.asarray(res["shap_values"]).mean(axis=0).tolist()}


def run(path: str | Path, preset: str, condition: str, line_freq: float,
        progress: Callable[[int, str], None] | None = None) -> dict:
    """Run load → clean → features → score → validation check on one file. Raises PipelineError for user errors."""
    path = Path(path)
    say = progress or (lambda i, s: None)
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        raise PipelineError(f"Unsupported file type '{path.suffix or '(none)'}'. Please upload an .edf or .fif EEG file.")
    if condition not in config.CONDITIONS:
        raise PipelineError(f"Unknown condition '{condition}'. Use one of {list(config.CONDITIONS)}.")
    t, timings = time.perf_counter(), {}

    say(0, STEPS[0])
    try:
        raw, meta = io_utils.load_eeg(str(path), preset)
    except ValueError as exc:
        raise PipelineError(str(exc)) from exc
    except (OSError, RuntimeError) as exc:      # unreadable / corrupt file
        raise PipelineError(f"Could not read {path.name} as EEG ({type(exc).__name__}). Is it a valid .edf/.fif file?") from exc
    if meta["duration_s"] < config.MIN_DURATION_S:
        raise PipelineError(f"Recording is too short: {meta['duration_s']:.1f} s. At least {config.MIN_DURATION_S:.0f} s "
                            f"(one epoch) is needed; 60 s gives full confidence.")
    timings["load"] = time.perf_counter() - t

    say(1, STEPS[1])
    epochs, qc = preprocess.clean(raw, line_freq)
    qc["duration_s"] = meta["duration_s"]
    timings["clean"] = time.perf_counter() - t

    say(2, STEPS[2])
    feats, per_epoch = features.extract(epochs, preset)
    spectrum = _spectrum(epochs) if len(epochs) else {}
    timings["features"] = time.perf_counter() - t

    say(3, STEPS[3])
    score = scoring.score(feats, qc, condition, preset)
    timings["score"] = time.perf_counter() - t

    say(4, STEPS[4])
    ml = _ml(per_epoch, preset)
    timings["total"] = time.perf_counter() - t
    log.info("pipeline %s: composite %s in %.1f s", path.name, score["composite"], timings["total"])
    return {"meta": meta, "qc": qc, "features": feats, "per_epoch": per_epoch, "score": score,
            "spectrum": spectrum, "ml": ml, "preset": preset, "condition": condition, "line_freq": line_freq,
            "timings_s": {k: round(v, 2) for k, v in timings.items()}}


def save(result: dict, subject_id: str, label: str, source: str, db_path: Path | str | None = None) -> int:
    """Store a run() result as the subject's next session; returns the DB row id."""
    subject_id = subject_id.strip()
    if not subject_id:
        raise PipelineError("Please enter a subject ID.")
    prev = db.load_subject(subject_id, db_path=db_path)
    idx = int(prev["session_index"].max()) + 1 if len(prev) else 1
    return db.save_session({"subject_id": subject_id, "session_index": idx, "label": label,
                            "condition": result["condition"], "preset": result["preset"], "source": source,
                            "recorded_at": None, "features": result["features"], "qc": result["qc"],
                            "score": result["score"], "extras": {"spectrum": result["spectrum"], "ml": result["ml"],
                                                                 "timings_s": result["timings_s"]}},
                           db_path=db_path)


def demo_label(path: Path) -> str:
    """'S051_s01_R01_raw.fif' → 's01 R01 eyes-open rest'; R03–R14 → 'sNN RXX T0 rest blocks' (as build_demo_sessions)."""
    m = _DEMO_NAME.search(path.name)
    if not m:
        return path.stem
    sess, run_id = m.groups()
    return f"{sess} {run_id} eyes-open rest" if run_id == "R01" else f"{sess} {run_id} T0 rest blocks"


def seed_demo(progress: Callable[[int, int, str], None] | None = None, db_path: Path | str | None = None) -> int:
    """Re-seed the demo subject from data/demo/*.fif (scoring only; no raw data needed). Returns sessions saved."""
    files = sorted(config.DATA_DEMO.glob(f"{config.DEMO_LONGITUDINAL_SUBJECT}_s*_raw.fif"))
    if not files:
        raise PipelineError(f"No demo files found in {config.DATA_DEMO.name}/")
    db.delete_subject(config.DEMO_LONGITUDINAL_SUBJECT, db_path=db_path)
    for i, f in enumerate(files):
        if progress:
            progress(i, len(files), f.name)
        res = run(f, config.ML_PRESET, "eyes_open", config.DATASET_LINE_FREQ)
        save(res, config.DEMO_LONGITUDINAL_SUBJECT, demo_label(f), str(f.relative_to(config.ROOT).as_posix()), db_path=db_path)
    return len(files)
