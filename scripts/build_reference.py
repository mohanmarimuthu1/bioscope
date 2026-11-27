"""Build models/reference.json from S001–S050 R01 (eyes open) / R02 (eyes closed).

WHAT:  For each preset × condition: load → clean → extract every reference recording,
       skip recordings with insufficient_data or n_kept < MIN_EPOCHS, then summarise each reference feature with
       src.reference.build_entry (ADR-010 transform, zscore or percentile method).
       Also writes models/reference_features.csv (one row per recording) for traceability.
WHY:   Scores are typicality versus a condition- and preset-matched public reference.
CHECKS (exit 1 if any fails): no demo/holdout subject used; EO PAF mean in 9–11 Hz;
       EC alpha_exc mean > EO alpha_exc mean (both presets).
Usage: python scripts/build_reference.py [--workers 8]
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")   # one BLAS thread per worker process
os.environ.setdefault("MKL_NUM_THREADS", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from src import config, reference  # noqa: E402

EO_PAF_RANGE = (9.0, 11.0)   # CLAUDE.md §7.6 sanity check


def _extract_one(job: tuple[str, str, str]) -> dict:
    """Session features + QC for one (preset, subject, condition). Runs in a worker."""
    import logging

    import mne

    from src import features, io_utils, preprocess
    mne.set_log_level("ERROR")
    logging.disable(logging.WARNING)
    preset, subj, cond = job
    path = config.DATA_RAW / subj / f"{subj}{config.REFERENCE_RUNS[cond]}.edf"
    raw, meta = io_utils.load_eeg(str(path), preset)
    epochs, qc = preprocess.clean(raw, config.DATASET_LINE_FREQ)
    feats, _ = features.extract(epochs, preset)
    row = {k: v for k, v in feats.items() if k != "warnings"}
    row.update(preset=preset, subject=subj, condition=cond, n_total=qc["n_total"],
               n_kept=qc["n_kept"], retained_frac=qc["retained_frac"],
               duration_s=meta["duration_s"], warnings=" | ".join(qc["warnings"] + feats["warnings"]))
    return row


def _usable(g: pd.DataFrame) -> pd.Series:
    """Reference inclusion: features computed and n_kept ≥ MIN_EPOCHS (same as the low-data warning)."""
    return ~g.insufficient_data.astype(bool) & (g.n_kept >= config.MIN_EPOCHS)


def build(df: pd.DataFrame) -> tuple[dict, list[str]]:
    """reference dict from the per-recording table, plus a list of failed sanity checks."""
    reference.assert_no_leak(df["subject"].unique().tolist())
    presets: dict = {}
    for preset in config.PRESETS:
        presets[preset] = {}
        for cond in config.CONDITIONS:
            g = df[(df.preset == preset) & (df.condition == cond)]
            keep = _usable(g)
            bad, good = g[~keep], g[keep]
            reference.assert_no_leak(good.subject.tolist())
            presets[preset][cond] = {
                "subjects_used": sorted(good.subject),
                "subjects_skipped": [{"subject": r.subject,
                                      "reason": f"{r.n_kept}/{r.n_total} epochs kept (< {config.MIN_EPOCHS})"}
                                     for r in bad.itertuples()],
                "features": {f: reference.build_entry(f, good[f].tolist()) for f in config.REFERENCE_TRANSFORMS},
            }
    failed = []
    print("\nSanity checks")
    for preset in config.PRESETS:
        ok = df[(df.preset == preset)]
        ok = ok[_usable(ok)]
        paf = ok[ok.condition == "eyes_open"].paf.mean()
        eo = ok[ok.condition == "eyes_open"].alpha_exc.mean()
        ec = ok[ok.condition == "eyes_closed"].alpha_exc.mean()
        c1 = EO_PAF_RANGE[0] <= paf <= EO_PAF_RANGE[1]
        c2 = ec > eo
        print(f"  {preset:8s} EO PAF mean {paf:.2f} Hz in {EO_PAF_RANGE}: {'PASS' if c1 else 'FAIL'}")
        print(f"  {preset:8s} alpha_exc mean EC {ec:.2f} > EO {eo:.2f} uV^2: {'PASS' if c2 else 'FAIL'}")
        failed += [f"{preset} EO PAF"] * (not c1) + [f"{preset} EC alpha_exc > EO"] * (not c2)
    ref = {
        "build_date": datetime.now().isoformat(timespec="seconds"),
        "command": "python scripts/build_reference.py",
        "dataset": "PhysioNet EEGMMI v1.0.0 (ODC-By)",
        "runs": config.REFERENCE_RUNS,
        "candidate_subjects": config.REFERENCE_SUBJECTS,
        "excluded_subjects": {"demo": config.DEMO_SUBJECT, "longitudinal_demo": config.DEMO_LONGITUDINAL_SUBJECT,
                              "holdout": config.HOLDOUT_SUBJECTS},
        "settings": {"transforms": config.REFERENCE_TRANSFORMS,
                     "skew_percentile_threshold": config.SKEW_PERCENTILE_THRESHOLD,
                     "percentile_z_cap": config.PERCENTILE_Z_CAP},
        "presets": presets,
    }
    return ref, failed


def _print_summary(ref: dict) -> None:
    print(f"\n{'preset':8s} {'cond':11s} {'feature':12s} {'tf':5s} {'n':>3s} {'skew':>6s} {'method':10s} {'mean':>8s} {'std':>7s}")
    for p, conds in ref["presets"].items():
        for c, cell in conds.items():
            for f, e in cell["features"].items():
                print(f"{p:8s} {c:11s} {f:12s} {e['transform']:5s} {e['n']:3d} {e['skew']:6.2f} "
                      f"{e['method']:10s} {e['mean']:8.3f} {e['std']:7.3f}")
    print("\nSkipped recordings")
    for p, conds in ref["presets"].items():
        for c, cell in conds.items():
            print(f"  {p:8s} {c:11s} used {len(cell['subjects_used'])}/50, skipped: "
                  + (", ".join(s["subject"] for s in cell["subjects_skipped"]) or "none"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    jobs = [(p, s, c) for p in config.PRESETS for s in config.REFERENCE_SUBJECTS for c in config.CONDITIONS]
    reference.assert_no_leak([s for _, s, _ in jobs])
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(_extract_one, jobs))
    print(f"Extracted {len(rows)} recordings in {time.time() - t0:.0f} s")
    df = pd.DataFrame(rows)
    ref, failed = build(df)
    config.MODELS_DIR.mkdir(exist_ok=True)
    df.round(6).to_csv(config.REFERENCE_FEATURES_PATH, index=False)
    config.REFERENCE_PATH.write_text(json.dumps(ref, indent=1, allow_nan=False), encoding="utf-8")
    _print_summary(ref)
    print(f"\nWrote {config.REFERENCE_PATH.name} and {config.REFERENCE_FEATURES_PATH.name}")
    if failed:
        print(f"SANITY FAILED: {failed}")
        return 1
    print("All sanity checks PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
