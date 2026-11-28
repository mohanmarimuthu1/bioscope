"""External holdout test on S061–S109 (P6b): saved model and reference, no refitting.

WHAT:  For 49 subjects never used by the reference or the model, R01 (eyes open) + R02 (eyes closed), frontal8 →
       one pass per recording (load → clean → extract → score) → models/holdout.json + models/holdout_features.csv.
       ML (LightGBM + LR, saved models): per-epoch accuracy + ROC-AUC, per-recording accuracy (mean p > 0.5), paired
       within-subject accuracy (mean p R02 > R01), within-subject label permutation test (1000), subject-level bootstrap
       95% CIs, SHAP top-10. Scores: composite median/IQR/n for EO-vs-EO, EC-vs-EC, EC-vs-EO reference.
       Features/QC: PAF mean/SD, retention, paf_fallback rate, warning counts, crashes.
WHY:   CV estimates generalisation from the training subjects; a holdout set checks it on data never touched.
CAVEATS:
  - No training here, so the permutation test shuffles labels (within each subject) against the fixed predictions.
  - The ADR-013 thresholds are reported for information; any miss prints FAIL and exits 1 (stop and show the owner).
  - A recording that raises is listed in `crashes` and skipped; the run never aborts.

Usage:  python scripts/evaluate_holdout.py [--workers 8]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import accuracy_score, roc_auc_score  # noqa: E402

from src import config, ml_sanity  # noqa: E402
from train_sanity_model import ALPHA_PREFIX, paired_accuracy, recording_accuracy  # noqa: E402

MODEL_NAMES = ("lgbm", "lr")
SCORE_CELLS = (("eo_vs_eo", "eyes_open", "eyes_open"), ("ec_vs_ec", "eyes_closed", "eyes_closed"),
               ("ec_vs_eo", "eyes_closed", "eyes_open"))     # (name, recording condition, reference condition)


def _one(job: tuple[str, str]) -> dict:
    """Session features, qc, per-epoch table and scores for one recording; errors are returned, not raised."""
    import logging

    import mne

    from src import features, io_utils, preprocess, scoring
    mne.set_log_level("ERROR")
    logging.disable(logging.WARNING)
    subj, cond = job
    path = config.DATA_RAW / subj / f"{subj}{config.REFERENCE_RUNS[cond]}.edf"
    try:
        raw, meta = io_utils.load_eeg(str(path), config.ML_PRESET)
        epochs, qc = preprocess.clean(raw, config.DATASET_LINE_FREQ)
        qc["duration_s"] = meta["duration_s"]
        feats, per_epoch = features.extract(epochs, config.ML_PRESET)
        scores = {ref: scoring.score(feats, qc, ref, config.ML_PRESET)["composite"]
                  for ref in {c[2] for c in SCORE_CELLS if c[1] == cond}}
    except Exception as exc:  # noqa: BLE001 — every failure is reported in holdout.json
        return {"subject": subj, "condition": cond, "error": f"{type(exc).__name__}: {exc}"}
    return {"subject": subj, "condition": cond, "sfreq": meta["sfreq"], "feats": feats, "qc": qc,
            "per_epoch": per_epoch.assign(subject=subj, condition=cond, label=config.ML_LABELS[cond]), "scores": scores}


def assert_holdout_clean(holdout: list[str]) -> None:
    """Raise if any holdout subject was used by the reference, the model or a demo."""
    ref = json.loads(config.REFERENCE_PATH.read_text(encoding="utf-8"))
    used = {s for cells in ref["presets"].values() for cell in cells.values() for s in cell["subjects_used"]}
    used |= set(config.REFERENCE_SUBJECTS) | set(ml_sanity.load_model()["train_subjects"])
    used |= {config.DEMO_SUBJECT, config.DEMO_LONGITUDINAL_SUBJECT}
    leaked = sorted(set(holdout) & used)
    if leaked:
        raise AssertionError(f"Holdout subjects used elsewhere: {leaked}")


def _subject_index(df: pd.DataFrame) -> list[np.ndarray]:
    return [np.flatnonzero(df.subject.to_numpy() == s) for s in sorted(df.subject.unique())]


def permutation_p(y: np.ndarray, p: np.ndarray, idx: list[np.ndarray], n: int) -> dict:
    """Within-subject label shuffles against fixed predictions; statistic = pooled per-epoch AUC."""
    obs = roc_auc_score(y, p)
    rng = np.random.default_rng(config.RANDOM_STATE)
    null = np.empty(n)
    for i in range(n):
        yp = y.copy()
        for ix in idx:
            yp[ix] = rng.permutation(yp[ix])
        null[i] = roc_auc_score(yp, p)
    return {"observed_auc": float(obs), "null_mean": float(null.mean()), "null_std": float(null.std(ddof=1)),
            "null_max": float(null.max()), "n_permutations": n, "p_value": float((1 + (null >= obs).sum()) / (1 + n))}


def bootstrap_ci(df: pd.DataFrame, p: np.ndarray, n: int) -> dict:
    """Subject-level bootstrap 95% CI for pooled AUC and paired accuracy."""
    rng = np.random.default_rng(config.RANDOM_STATE)
    idx = _subject_index(df)
    auc, paired = [], []
    for _ in range(n):
        pick = rng.integers(0, len(idx), len(idx))
        rows = np.concatenate([idx[k] for k in pick])
        y = df.label.to_numpy()[rows]
        if len(set(y)) == 2:
            auc.append(roc_auc_score(y, p[rows]))
        sub = df.iloc[rows].assign(subject=np.repeat([f"b{j}" for j in range(len(pick))], [len(idx[k]) for k in pick]))
        paired.append(paired_accuracy(sub, p[rows])[0])
    q = lambda v: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]  # noqa: E731
    return {"auc_ci95": q(auc), "paired_acc_ci95": q(paired), "n_bootstrap": n}


def ml_metrics(df: pd.DataFrame) -> dict:
    """Saved LightGBM + LR on holdout epochs (no refit), same metrics as P6, plus bootstrap CIs and SHAP top-10."""
    art = ml_sanity.load_model()
    x, y = df[art["feature_names"]].astype(float), df.label.to_numpy()
    idx = _subject_index(df)
    out = {}
    for name in MODEL_NAMES:
        p = art[name].predict_proba(x)[:, 1]
        pa, n_pa = paired_accuracy(df, p)
        out[name] = {"acc": float(accuracy_score(y, (p > 0.5).astype(int))), "auc": float(roc_auc_score(y, p)),
                     "rec_acc": recording_accuracy(df, p), "paired_acc": pa, "paired_n": n_pa,
                     "permutation": permutation_p(y, p, idx, config.N_PERMUTATIONS), **bootstrap_ci(df, p, config.N_BOOTSTRAP)}
    vals, _ = ml_sanity.shap_matrix(ml_sanity._explainer(), x)
    imp = pd.Series(np.abs(vals).mean(axis=0), index=x.columns).sort_values(ascending=False)
    ranks = {f: int(r) for r, f in enumerate(imp.index, start=1) if f.startswith(ALPHA_PREFIX)}
    out["shap"] = {"top": [{"feature": f, "mean_abs_shap": round(float(v), 4)} for f, v in imp.head(config.SHAP_TOP_N).items()],
                   "alpha_ranks": ranks, "alpha_leads": imp.index[0].startswith(ALPHA_PREFIX)}
    return out


def _norm_warning(w: str) -> str:
    """Group per-channel warnings: 'FOOOF fit failed/poor on F7' → '... on <ch>'; digits → '#'."""
    return re.sub(r"\d+", "#", re.sub(r" on [A-Za-z0-9]+$", " on <ch>", w))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    holdout = list(config.HOLDOUT_SUBJECTS)
    assert_holdout_clean(holdout)
    jobs = [(s, c) for s in holdout for c in config.CONDITIONS]
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        res = list(ex.map(_one, jobs))
    ok = [r for r in res if "error" not in r]
    crashes = [{"file": f"{r['subject']}{config.REFERENCE_RUNS[r['condition']]}.edf", "error": r["error"]} for r in res if "error" in r]
    print(f"Processed {len(jobs)} recordings in {time.time() - t0:.0f} s: {len(ok)} ok, {len(crashes)} crashed")
    for c in crashes:
        print(f"  CRASH {c['file']}: {c['error']}")
    off_rate = sorted(f"{r['subject']} {r['condition']} {r['sfreq']}" for r in ok if r["sfreq"] != config.DATASET_SFREQ)
    print(f"Sampling rate: {len(ok) - len(off_rate)}/{len(ok)} at {config.DATASET_SFREQ:.0f} Hz" + (f"; other: {off_rate}" if off_rate else ""))

    # ---- per-recording table
    rows = []
    for r in ok:
        row = {k: v for k, v in r["feats"].items() if k != "warnings"}
        row.update(subject=r["subject"], condition=r["condition"], n_total=r["qc"]["n_total"], n_kept=r["qc"]["n_kept"],
                   retained_frac=r["qc"]["retained_frac"], **{f"composite_vs_{k}": v for k, v in r["scores"].items()},
                   warnings=" | ".join(r["qc"]["warnings"] + r["feats"]["warnings"]))
        rows.append(row)
    rec = pd.DataFrame(rows)

    # ---- ML
    ep = pd.concat([r["per_epoch"] for r in ok if not r["per_epoch"].empty], ignore_index=True)
    ml = ml_metrics(ep)
    print(f"\nML on holdout: {len(ep)} epochs (EO {int((ep.label == 0).sum())}, EC {int((ep.label == 1).sum())}), "
          f"{ep.subject.nunique()} subjects; saved models, no refit")
    for name, label in (("lgbm", "LightGBM"), ("lr", "LogReg  ")):
        m = ml[name]
        print(f"{label}: acc {m['acc']:.3f} | AUC {m['auc']:.3f} [{m['auc_ci95'][0]:.3f}, {m['auc_ci95'][1]:.3f}] | "
              f"rec acc {m['rec_acc']:.3f} | paired {m['paired_acc']:.3f} (n={m['paired_n']}) "
              f"[{m['paired_acc_ci95'][0]:.3f}, {m['paired_acc_ci95'][1]:.3f}] | perm p {m['permutation']['p_value']:.4f} "
              f"(null {m['permutation']['null_mean']:.3f} ± {m['permutation']['null_std']:.3f}, max {m['permutation']['null_max']:.3f})")
    print("SHAP top-10: " + ", ".join(f"{t['feature']} {t['mean_abs_shap']:.3f}" for t in ml["shap"]["top"]))
    print(f"Alpha features lead: {ml['shap']['alpha_leads']} (ranks {ml['shap']['alpha_ranks']})")

    # ---- scores
    scores = {}
    print(f"\n{'cell':9s} {'n':>3s} {'None':>4s} {'median':>7s} {'IQR':>13s}")
    for name, cond, ref_cond in SCORE_CELLS:
        v = rec.loc[rec.condition == cond, f"composite_vs_{ref_cond}"]
        good = v.dropna().astype(float)
        q1, med, q3 = (np.percentile(good, [25, 50, 75]) if len(good) else (np.nan,) * 3)
        scores[name] = {"n": int(len(good)), "n_unscorable": int(v.isna().sum()), "median": float(med), "q1": float(q1), "q3": float(q3)}
        print(f"{name:9s} {len(good):3d} {int(v.isna().sum()):4d} {med:7.1f} {q1:6.1f}–{q3:6.1f}")

    # ---- features / QC
    feat = {}
    for cond in config.CONDITIONS:
        g = rec[rec.condition == cond]
        usable = g[g.n_kept > 0]
        feat[cond] = {"n_recordings": int(len(g)), "n_zero_kept": int((g.n_kept == 0).sum()),
                      "paf_mean": float(usable.paf.mean()), "paf_sd": float(usable.paf.std(ddof=1)),
                      "retention_median": float(g.retained_frac.median()),
                      "paf_fallback_rate": float(usable.paf_fallback.astype(bool).mean())}
        print(f"{cond:11s}: n {len(g)}, 0 kept {feat[cond]['n_zero_kept']}, PAF {feat[cond]['paf_mean']:.2f} ± {feat[cond]['paf_sd']:.2f} Hz, "
              f"retention median {feat[cond]['retention_median']:.2f}, paf_fallback {feat[cond]['paf_fallback_rate']:.0%}")
    warn = Counter(_norm_warning(w) for r in ok for w in r["qc"]["warnings"] + r["feats"]["warnings"])
    print("Warnings (recordings): " + "; ".join(f"{k} ×{v}" for k, v in warn.most_common()))

    # ---- thresholds (information; ADR-013 values)
    m = ml["lgbm"]
    checks = {"perm_p": m["permutation"]["p_value"] < config.GATE_PERM_P, "auc": m["auc"] > config.GATE_AUC,
              "paired_acc": m["paired_acc"] >= config.GATE_PAIRED_ACC}
    passed = all(checks.values())
    out = {"build_date": datetime.now().isoformat(timespec="seconds"), "command": "python scripts/evaluate_holdout.py",
           "subjects": holdout, "preset": config.ML_PRESET, "n_recordings": len(jobs), "n_ok": len(ok), "crashes": crashes,
           "sfreq_other": off_rate, "n_epochs": int(len(ep)), "ml": ml, "scores": scores, "features": feat,
           "warning_counts": dict(warn.most_common()),
           "thresholds": {"rule": "ADR-013 values applied to LightGBM on the holdout (information; FAIL stops for owner review)",
                          "checks": checks, "passed": passed},
           "cv_reference": json.loads(config.METRICS_PATH.read_text(encoding="utf-8"))["summary"]}
    config.HOLDOUT_PATH.write_text(json.dumps(out, indent=1, allow_nan=False, default=float), encoding="utf-8")
    rec.round(6).to_csv(config.HOLDOUT_FEATURES_PATH, index=False)
    print(f"\nWrote {config.HOLDOUT_PATH.name}, {config.HOLDOUT_FEATURES_PATH.name}")
    print(f"THRESHOLDS {'PASS' if passed else 'FAIL'} (ADR-013 values, holdout): perm p {m['permutation']['p_value']:.4f} {checks['perm_p']} | "
          f"AUC {m['auc']:.3f} {checks['auc']} | paired {m['paired_acc']:.3f} {checks['paired_acc']}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
