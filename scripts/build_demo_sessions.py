"""Build the 13-session longitudinal demo (S051, ADR-012 addendum) (CLAUDE.md §7.7) and seed the SQLite DB.

WHAT:  s01 = S051 R01 (eyes-open rest, whole run). s02–s13 = the T0 rest blocks (eyes open, ~4.1 s each)
       of R03–R14, joined with mne.concatenate_raws so each join carries BAD/EDGE boundary annotations:
       filters run per block and no epoch crosses a join (ADR-012). Saved as 8-ch frontal8 .fif in data/demo/.
       Each file is then scored (eyes_open reference, frontal8) and stored as one session of subject S051.
WHY:   One held-out subject gives a reproducible longitudinal demo. S051 replaced S060, whose between-task rest
       blocks were too noisy (0–5 of 15 epochs kept; screening table in ADR-012). These are sequential rest blocks from a
       single visit — they demonstrate tracker mechanics, not multi-day change.
Usage: python scripts/build_demo_sessions.py
"""
import logging
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mne  # noqa: E402
import numpy as np  # noqa: E402

from src import config, db, features, io_utils, longitudinal, preprocess, scoring  # noqa: E402

PRESET = "frontal8"
CONDITION = "eyes_open"
BOUNDARY = ("BAD boundary", "EDGE boundary")
DEMO_LABEL = "Sequential rest blocks from a single visit — demonstrates tracker mechanics, not multi-day change."


def _t0_session(run: str, subject: str = config.DEMO_LONGITUDINAL_SUBJECT) -> mne.io.Raw:
    """Concatenate the T0 blocks of one run (frontal8 channels) with boundary annotations."""
    raw, _ = io_utils.load_eeg(str(config.DATA_RAW / subject / f"{subject}{run}.edf"), PRESET)
    raw.load_data(verbose="ERROR")
    blocks = [(a["onset"] - raw.first_time, a["duration"]) for a in raw.annotations
              if a["description"] == config.DEMO_REST_LABEL]
    segs = [raw.copy().crop(o, min(o + d, raw.times[-1]), include_tmax=False) for o, d in blocks]
    cat = mne.concatenate_raws(segs, verbose="ERROR")
    drop = [i for i, d in enumerate(cat.annotations.description) if d not in BOUNDARY + (config.DEMO_REST_LABEL,)]
    cat.annotations.delete(drop)            # T1/T2 fragments overlapping a block edge
    return cat


def _crossings(raw: mne.io.Raw, epochs: mne.Epochs) -> int:
    """Number of epochs that contain a boundary strictly inside them (must be 0)."""
    ann = raw.annotations
    m = np.isin(ann.description, BOUNDARY)
    if not m.any():
        return 0
    cuts = raw.time_as_index(ann.onset[m], use_rounding=True, origin=ann.orig_time)
    starts = epochs.events[:, 0] - raw.first_samp
    n = len(epochs.times)
    return int(sum(any(s < c < s + n for c in cuts) for s in starts))


def build_files() -> list[tuple[str, str, Path]]:
    config.DATA_DEMO.mkdir(parents=True, exist_ok=True)
    out = []
    r01, _ = io_utils.load_eeg(str(config.DATA_RAW / config.DEMO_LONGITUDINAL_SUBJECT / f"{config.DEMO_LONGITUDINAL_SUBJECT}R01.edf"), PRESET)
    p = config.DATA_DEMO / f"{config.DEMO_LONGITUDINAL_SUBJECT}_s01_R01_raw.fif"
    r01.load_data(verbose="ERROR").save(p, overwrite=True, fmt="single", verbose="ERROR")
    out.append(("s01", "R01 eyes-open rest", p))
    for i, run in enumerate(config.DEMO_RUNS[2:], start=2):          # R03–R14
        p = config.DATA_DEMO / f"{config.DEMO_LONGITUDINAL_SUBJECT}_s{i:02d}_{run}_raw.fif"
        _t0_session(run).save(p, overwrite=True, fmt="single", verbose="ERROR")
        out.append((f"s{i:02d}", f"{run} T0 rest blocks", p))
    return out


def main() -> int:
    mne.set_log_level("ERROR")
    logging.disable(logging.WARNING)
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    files = build_files()
    removed = db.delete_subject(config.DEMO_LONGITUDINAL_SUBJECT)
    print(f"Wrote {len(files)} files to {config.DATA_DEMO.relative_to(config.ROOT)}; removed {removed} old DB rows\n")
    print(f"{'sess':4s} {'source':20s} {'dur s':>6s} {'segs':>4s} {'total':>5s} {'kept':>4s} {'cross':>5s} {'comp':>6s} {'conf':>5s}")
    rows = []
    for idx, (label, desc, path) in enumerate(files, start=1):
        raw, meta = io_utils.load_eeg(str(path), PRESET)
        epochs, qc = preprocess.clean(raw, config.DATASET_LINE_FREQ)
        qc["duration_s"] = meta["duration_s"]                       # ADR-011: score() reads duration from qc
        cross = _crossings(raw, epochs)
        assert cross == 0, f"{label}: {cross} epochs span a boundary"
        feats, _ = features.extract(epochs, PRESET)
        res = scoring.score(feats, qc, CONDITION, PRESET)
        db.save_session({"subject_id": config.DEMO_LONGITUDINAL_SUBJECT, "session_index": idx, "label": f"{label} {desc}",
                         "condition": CONDITION, "preset": PRESET, "source": str(path.relative_to(config.ROOT)),
                         "recorded_at": None, "features": feats, "qc": qc, "score": res})
        comp = "None" if res["composite"] is None else f"{res['composite']:.1f}"
        print(f"{label:4s} {desc:20s} {meta['duration_s']:6.1f} {qc['n_segments']:4d} {qc['n_total']:5d} "
              f"{qc['n_kept']:4d} {cross:5d} {comp:>6s} {res['confidence']:5.2f}")
        rows.append((label, res))

    ok = [(lab, r) for lab, r in rows if r["composite"] is not None]
    scores = [r["composite"] for _, r in ok]
    conf = [r["confidence"] for _, r in ok]
    base = longitudinal.compute_baseline(scores)
    e = longitudinal.ema(scores)
    post = longitudinal.bayesian_track(scores, longitudinal.obs_sd_from_confidence(conf))
    flags = longitudinal.flag_shifts(scores, base)
    print(f"\nBaseline (first {base['n']}): {base['mean']:.1f} ± {base['std']:.2f} (raw sd {base['raw_std']:.2f})")
    print(f"{'sess':4s} {'comp':>6s} {'conf':>5s} {'EMA':>6s} {'post mean ± sd':>15s} {'flag':>5s}")
    for (lab, r), s, c, m, (pm, ps), f in zip(ok, scores, conf, e, post, flags):
        print(f"{lab:4s} {s:6.1f} {c:5.2f} {m:6.1f} {pm:8.1f} ± {ps:4.1f} {'FLAG' if f else '':>5s}")
    skipped = [lab for lab, r in rows if r["composite"] is None]
    if skipped:
        print(f"Not scored (no clean data): {skipped}")
    print(f"\nUI label: {DEMO_LABEL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
