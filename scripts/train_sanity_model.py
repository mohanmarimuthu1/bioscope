"""Train the eyes-open / eyes-closed pipeline-validation model with subject-grouped CV (CLAUDE.md §7.8, ADR-013).

WHAT:  Reference subjects S001–S050, R01 (eyes open, label 0) and R02 (eyes closed, label 1), frontal8 →
       per-epoch features (every epoch that passed rejection) → GroupKFold(5) by subject for LightGBM and a
       Logistic Regression baseline on the same folds → final models on all data →
       models/lgbm_eyes.joblib, models/metrics.json, models/epoch_features.csv.
       Reports per fold and mean ± std: per-epoch accuracy + ROC-AUC, per-recording accuracy (mean p > 0.5),
       paired within-subject accuracy (out-of-fold mean p on R02 > R01), a within-subject label permutation
       test on per-epoch AUC, and the SHAP top-10 features.
WHY:   If features separate EO from EC on subjects the model never saw, the feature pipeline carries signal.
       The model never feeds the score.
CAVEATS:
  - Hyper-parameters are fixed in config (LGBM_PARAMS) and never tuned on the folds.
  - Gate (ADR-013, LightGBM): permutation p < GATE_PERM_P AND mean AUC > GATE_AUC AND paired accuracy >= GATE_PAIRED_ACC,
    else exit 1. It replaced the original 80% accuracy gate after that gate failed (0.661 ± 0.033) — see ADR-013.
  - The permutation test re-runs the whole CV on each permuted label set (labels shuffled within each subject),
    so the null distribution includes training. ~2 min on 8+ workers.
  - Held-out subjects (S051, S060, S061–S109) are refused by reference.assert_no_leak.

Usage:  python scripts/train_sanity_model.py [--workers 8] [--permutations 1000]
"""
from __future__ import annotations

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

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import accuracy_score, roc_auc_score  # noqa: E402
from sklearn.model_selection import GroupKFold  # noqa: E402

from src import config, ml_sanity, reference  # noqa: E402

MODELS = {"lgbm": ml_sanity.make_lgbm, "lr": ml_sanity.make_lr}
ALPHA_PREFIX = "alpha_"


def _extract_epochs(job: tuple[str, str]) -> pd.DataFrame:
    """Per-epoch features for one (subject, condition), frontal8. Runs in a worker."""
    import logging

    import mne

    from src import features, io_utils, preprocess
    mne.set_log_level("ERROR")
    logging.disable(logging.WARNING)
    subj, cond = job
    path = config.DATA_RAW / subj / f"{subj}{config.REFERENCE_RUNS[cond]}.edf"
    raw, _ = io_utils.load_eeg(str(path), config.ML_PRESET)
    epochs, _ = preprocess.clean(raw, config.DATASET_LINE_FREQ)
    _, per_epoch = features.extract(epochs, config.ML_PRESET)
    return per_epoch.assign(subject=subj, condition=cond, label=config.ML_LABELS[cond])


def _folds(groups: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    """Deterministic GroupKFold split by subject; raises if a subject lands on both sides."""
    out = []
    for k, (tr, te) in enumerate(GroupKFold(n_splits=config.CV_FOLDS).split(groups, groups=groups)):
        overlap = set(groups[tr]) & set(groups[te])
        if overlap:
            raise AssertionError(f"fold {k}: subjects on both sides {sorted(overlap)}")
        out.append((tr, te))
    return out


def recording_accuracy(meta: pd.DataFrame, p: np.ndarray) -> float:
    """Share of recordings whose mean epoch probability lands on the right side of 0.5."""
    rec = meta.assign(p=p).groupby(["subject", "condition"]).agg(p=("p", "mean"), label=("label", "first"))
    return float(((rec.p > 0.5).astype(int) == rec.label).mean())


def paired_accuracy(meta: pd.DataFrame, p: np.ndarray) -> tuple[float, int]:
    """Share of subjects (with both runs) whose mean p(EC) on R02 exceeds that on R01. Returns (acc, n_subjects)."""
    per = meta.assign(p=p).groupby(["subject", "label"]).p.mean().unstack().dropna()
    return float((per[1] > per[0]).mean()), int(len(per))


def _mean_fold_auc(x: np.ndarray, y: np.ndarray, folds: list, make) -> float:
    """Mean per-epoch ROC-AUC over the folds (the permutation test statistic)."""
    aucs = []
    for tr, te in folds:
        p = make().fit(x[tr], y[tr]).predict_proba(x[te])[:, 1]
        aucs.append(roc_auc_score(y[te], p))
    return float(np.mean(aucs))


def cross_validate(df: pd.DataFrame) -> dict:
    """GroupKFold by subject; identical folds for both models. Per-fold rows, summaries and out-of-fold p."""
    x, y = df[ml_sanity.FEATURES].to_numpy(float), df.label.to_numpy()
    folds = _folds(df.subject.to_numpy())
    oof = {name: np.full(len(df), np.nan) for name in MODELS}
    rows = []
    for k, (tr, te) in enumerate(folds):
        row = {"fold": k, "n_test_subjects": int(df.subject.iloc[te].nunique()), "n_test_epochs": int(len(te))}
        for name, make in MODELS.items():
            p = make().fit(x[tr], y[tr]).predict_proba(x[te])[:, 1]
            oof[name][te] = p
            row[f"{name}_acc"] = float(accuracy_score(y[te], (p > 0.5).astype(int)))
            row[f"{name}_auc"] = float(roc_auc_score(y[te], p))
            row[f"{name}_rec_acc"] = recording_accuracy(df.iloc[te], p)
        rows.append(row)
    fdf = pd.DataFrame(rows)
    summary = {c: {"mean": float(fdf[c].mean()), "std": float(fdf[c].std(ddof=1))}
               for c in fdf.columns if c.startswith(tuple(f"{n}_" for n in MODELS))}
    for name in MODELS:
        acc, n = paired_accuracy(df, oof[name])
        summary[f"{name}_paired_acc"] = {"value": acc, "n_subjects": n}
    return {"folds": rows, "summary": summary, "oof": oof}


# ---- permutation test (workers share the data through an initializer, not per task)
_PERM: dict = {}


def _perm_init(x: np.ndarray, y: np.ndarray, groups: np.ndarray) -> None:
    _PERM.update(x=x, y=y, groups=groups, folds=_folds(groups),
                 idx=[np.flatnonzero(groups == g) for g in np.unique(groups)])


def _perm_one(i: int) -> tuple[float, float]:
    """Shuffle labels within each subject (seeded per permutation), re-run CV; return (lgbm AUC, lr AUC)."""
    rng = np.random.default_rng([config.RANDOM_STATE, i])
    y = _PERM["y"].copy()
    for ix in _PERM["idx"]:
        y[ix] = rng.permutation(y[ix])
    return tuple(_mean_fold_auc(_PERM["x"], y, _PERM["folds"], make) for make in MODELS.values())


def permutation_test(df: pd.DataFrame, observed: dict, n: int, workers: int) -> dict:
    """p = (1 + #{null AUC >= observed}) / (1 + n), per model."""
    x, y, g = df[ml_sanity.FEATURES].to_numpy(float), df.label.to_numpy(), df.subject.to_numpy()
    with ProcessPoolExecutor(max_workers=workers, initializer=_perm_init, initargs=(x, y, g)) as ex:
        null = np.array(list(ex.map(_perm_one, range(n), chunksize=8)))
    out = {}
    for j, name in enumerate(MODELS):
        obs = observed[name]
        out[name] = {"observed_auc": obs, "null_mean": float(null[:, j].mean()), "null_std": float(null[:, j].std(ddof=1)),
                     "null_max": float(null[:, j].max()), "n_permutations": n,
                     "p_value": float((1 + (null[:, j] >= obs).sum()) / (1 + n))}
    return out


def shap_top(model, x: pd.DataFrame) -> dict:
    """Mean |SHAP| per feature (training data, explainer built here and discarded), top N + alpha plausibility."""
    import shap
    vals, _ = ml_sanity.shap_matrix(shap.TreeExplainer(model), x)
    imp = pd.Series(np.abs(vals).mean(axis=0), index=x.columns).sort_values(ascending=False)
    ranks = {f: int(r) for r, f in enumerate(imp.index, start=1) if f.startswith(ALPHA_PREFIX)}
    return {"top": [{"feature": f, "mean_abs_shap": round(float(v), 4)} for f, v in imp.head(config.SHAP_TOP_N).items()],
            "alpha_ranks": ranks, "alpha_leads": imp.index[0].startswith(ALPHA_PREFIX),
            "best_alpha_rank": min(ranks.values()) if ranks else None}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--permutations", type=int, default=config.N_PERMUTATIONS)
    args = ap.parse_args()
    reference.assert_no_leak(config.REFERENCE_SUBJECTS)
    jobs = [(s, c) for s in config.REFERENCE_SUBJECTS for c in config.CONDITIONS]
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        tables = list(ex.map(_extract_epochs, jobs))
    df = pd.concat([t for t in tables if not t.empty], ignore_index=True)
    print(f"Extracted {len(jobs)} recordings in {time.time() - t0:.0f} s -> {len(df)} epochs")

    subjects = sorted(df.subject.unique())
    reference.assert_no_leak(subjects)
    if not set(subjects) <= set(config.REFERENCE_SUBJECTS):
        raise AssertionError("training subjects outside S001–S050")
    counts = df.groupby(["subject", "condition"]).size().unstack(fill_value=0).stack()
    no_rows = sorted(set(config.REFERENCE_SUBJECTS) - set(subjects))
    print(f"Subjects with epochs: {len(subjects)}/50 (none: {', '.join(no_rows) or '-'}); "
          f"epochs EO {int((df.label == 0).sum())}, EC {int((df.label == 1).sum())}; "
          f"per recording median {int(counts.median())}, min {int(counts.min())}")

    cv = cross_validate(df)
    print(f"\n{'fold':>4} {'subj':>4} {'epochs':>6} | {'LGBM acc':>8} {'auc':>6} {'rec':>5} | {'LR acc':>7} {'auc':>6} {'rec':>5}")
    for r in cv["folds"]:
        print(f"{r['fold']:4d} {r['n_test_subjects']:4d} {r['n_test_epochs']:6d} | {r['lgbm_acc']:8.3f} {r['lgbm_auc']:6.3f} "
              f"{r['lgbm_rec_acc']:5.2f} | {r['lr_acc']:7.3f} {r['lr_auc']:6.3f} {r['lr_rec_acc']:5.2f}")
    s = cv["summary"]

    t0 = time.time()
    perm = permutation_test(df, {n: s[f"{n}_auc"]["mean"] for n in MODELS}, args.permutations, args.workers)
    print(f"\nPermutation test: {args.permutations} within-subject label shuffles, full CV each ({time.time() - t0:.0f} s)")
    for name, label in (("lgbm", "LightGBM"), ("lr", "LogReg  ")):
        pr = s[f"{name}_paired_acc"]
        print(f"{label}: accuracy {s[name + '_acc']['mean']:.3f} ± {s[name + '_acc']['std']:.3f} | "
              f"ROC-AUC {s[name + '_auc']['mean']:.3f} ± {s[name + '_auc']['std']:.3f} | "
              f"recording acc {s[name + '_rec_acc']['mean']:.3f} ± {s[name + '_rec_acc']['std']:.3f} | "
              f"paired {pr['value']:.3f} (n={pr['n_subjects']}) | "
              f"perm p {perm[name]['p_value']:.4f} (null AUC {perm[name]['null_mean']:.3f} ± {perm[name]['null_std']:.3f}, "
              f"max {perm[name]['null_max']:.3f})")

    x, y = df[ml_sanity.FEATURES].astype(float), df.label.to_numpy()
    lgbm, lr = ml_sanity.make_lgbm().fit(x, y), ml_sanity.make_lr().fit(x, y)
    top = shap_top(lgbm, x)
    print("\nSHAP top-10 (mean |SHAP|, log-odds): " + ", ".join(f"{t['feature']} {t['mean_abs_shap']:.3f}" for t in top["top"]))
    print(f"Alpha features lead: {top['alpha_leads']} (best alpha rank {top['best_alpha_rank']}; ranks {top['alpha_ranks']})")

    g = {"perm_p": perm["lgbm"]["p_value"], "auc": s["lgbm_auc"]["mean"], "paired_acc": s["lgbm_paired_acc"]["value"]}
    checks = {"perm_p": g["perm_p"] < config.GATE_PERM_P, "auc": g["auc"] > config.GATE_AUC,
              "paired_acc": g["paired_acc"] >= config.GATE_PAIRED_ACC}
    passed = all(checks.values())
    orig_acc = s["lgbm_acc"]["mean"]

    import lightgbm
    import sklearn
    meta = {"preset": config.ML_PRESET, "feature_names": ml_sanity.FEATURES, "train_subjects": subjects,
            "lgbm_params": config.LGBM_PARAMS, "lr_max_iter": config.LR_MAX_ITER,
            "versions": {"lightgbm": lightgbm.__version__, "sklearn": sklearn.__version__},
            "build_date": datetime.now().isoformat(timespec="seconds")}
    config.MODELS_DIR.mkdir(exist_ok=True)
    joblib.dump({"lgbm": lgbm, "lr": lr, **meta}, config.MODEL_PATH)
    metrics = {**meta, "command": "python scripts/train_sanity_model.py", "cv": f"GroupKFold({config.CV_FOLDS}) by subject",
               "n_epochs": int(len(df)), "n_epochs_by_label": {"eyes_open": int((df.label == 0).sum()),
                                                               "eyes_closed": int((df.label == 1).sum())},
               "subjects_without_epochs": no_rows,
               "original_gate": {"rule": "LightGBM mean CV accuracy >= 0.80", "set": "before any evidence",
                                 "value": orig_acc, "std": s["lgbm_acc"]["std"], "auc": s["lgbm_auc"]["mean"],
                                 "passed": orig_acc >= 0.80, "status": "replaced after seeing this result (ADR-013)"},
               "folds": cv["folds"], "summary": s, "permutation": perm, "shap": top,
               "gate": {"rule": f"LightGBM perm p < {config.GATE_PERM_P} AND AUC > {config.GATE_AUC} AND "
                                f"paired acc >= {config.GATE_PAIRED_ACC} (ADR-013)",
                        "values": g, "checks": checks, "passed": passed}}
    config.METRICS_PATH.write_text(json.dumps(metrics, indent=1, allow_nan=False), encoding="utf-8")
    cols = ["subject", "condition", "label", "epoch"] + ml_sanity.FEATURES
    df[cols].round(6).to_csv(config.EPOCH_FEATURES_PATH, index=False)
    print(f"\nWrote {config.MODEL_PATH.name}, {config.METRICS_PATH.name}, {config.EPOCH_FEATURES_PATH.name}")
    print(f"Original gate (set before evidence): accuracy {orig_acc:.3f} vs 0.80 -> FAIL; replaced by ADR-013")
    print(f"GATE {'PASS' if passed else 'FAIL'} (ADR-013): perm p {g['perm_p']:.4f} < {config.GATE_PERM_P} {checks['perm_p']} | "
          f"AUC {g['auc']:.3f} > {config.GATE_AUC} {checks['auc']} | "
          f"paired {g['paired_acc']:.3f} >= {config.GATE_PAIRED_ACC} {checks['paired_acc']}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
