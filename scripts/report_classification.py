"""Report-only classification detail for the eyes-open/closed validation model (no retraining, no tuning).

WHAT:  CV: out-of-fold predictions recomputed with the same fixed GroupKFold(5) folds and config params as
       scripts/train_sanity_model.py (deterministic; checked against metrics.json). Holdout: the saved models on
       S061–S109 per-epoch features. For LightGBM and LR → confusion matrix at 0.5 (per epoch and per recording;
       EO = negative, EC = positive), precision, recall, specificity, F1, balanced accuracy, log-loss, Brier score
       (+ chance baselines), 5-bin calibration. Writes metrics.json["cv_extra"], holdout.json["extra"] and
       docs/figures/confusion_matrix.png.
WHY:   Accuracy and AUC alone hide which class is missed and whether probabilities are trustworthy.
CAVEATS:
  - Report only: the score never uses this model; nothing here changes either model.
  - CV features are re-extracted from the raw EDFs at full precision (the committed CSV is rounded to 6 dp, which
    shifts LightGBM splits); the OOF recomputation must reproduce the stored fold metrics, else the script stops.

Usage:  python scripts/report_classification.py [--workers 8]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import brier_score_loss, confusion_matrix, log_loss  # noqa: E402

from src import config, ml_sanity  # noqa: E402
from train_sanity_model import _extract_epochs, cross_validate  # noqa: E402

FIG_PATH = ROOT / "docs" / "figures" / "confusion_matrix.png"
CAL_EDGES = np.linspace(0.0, 1.0, 6)          # 5 equal-width bins (report choice)
MODEL_NAMES = ("lgbm", "lr")
LABELS = {"lgbm": "LightGBM", "lr": "LogReg"}


def _counts(y: np.ndarray, p: np.ndarray) -> dict:
    """Confusion counts at 0.5 and the derived rates (EC = positive)."""
    tn, fp, fn, tp = (int(v) for v in confusion_matrix(y, (p > 0.5).astype(int), labels=[0, 1]).ravel())
    prec = tp / (tp + fp) if tp + fp else float("nan")
    rec = tp / (tp + fn) if tp + fn else float("nan")
    spec = tn / (tn + fp) if tn + fp else float("nan")
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else float("nan")
    return {"tn": tn, "fp": fp, "fn": fn, "tp": tp, "n": tn + fp + fn + tp, "precision": prec, "recall": rec,
            "specificity": spec, "f1": f1, "balanced_accuracy": (rec + spec) / 2, "accuracy": (tp + tn) / (tn + fp + fn + tp)}


def _calibration(y: np.ndarray, p: np.ndarray) -> list[dict]:
    """Mean predicted p vs observed EC rate in 5 equal-width bins (empty bins reported with n = 0)."""
    out = []
    for lo, hi in zip(CAL_EDGES[:-1], CAL_EDGES[1:]):
        m = (p >= lo) & ((p < hi) if hi < 1 else (p <= hi))
        out.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": int(m.sum()),
                    "mean_p": float(p[m].mean()) if m.any() else None,
                    "observed_rate": float(y[m].mean()) if m.any() else None})
    return out


def report(meta: pd.DataFrame, p: np.ndarray) -> dict:
    """All metrics for one model on one dataset; meta has subject, condition, label per epoch."""
    y = meta.label.to_numpy()
    prior = float(y.mean())
    rec = meta.assign(p=p).groupby(["subject", "condition"]).agg(p=("p", "mean"), label=("label", "first"))
    return {"per_epoch": _counts(y, p), "per_recording": _counts(rec.label.to_numpy(), rec.p.to_numpy()),
            "log_loss": float(log_loss(y, p, labels=[0, 1])),
            "log_loss_chance": float(-(prior * np.log(prior) + (1 - prior) * np.log(1 - prior))),
            "brier": float(brier_score_loss(y, p)), "brier_chance": 0.25,
            "brier_prior": float(prior * (1 - prior)), "ec_prior": prior,
            "calibration": _calibration(y, p)}


def _holdout_epochs(workers: int) -> pd.DataFrame:
    """Per-epoch holdout features through the same one-pass worker as evaluate_holdout.py."""
    from evaluate_holdout import _one
    jobs = [(s, c) for s in config.HOLDOUT_SUBJECTS for c in config.CONDITIONS]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(_one, jobs))
    return pd.concat([r["per_epoch"] for r in res if "error" not in r and not r["per_epoch"].empty], ignore_index=True)


def _figure(results: dict) -> None:
    """2 × 2 per-epoch confusion matrices (rows: CV, holdout; cols: LightGBM, LR) with counts and row %."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(8, 7.2))
    for i, ds in enumerate(("cv", "holdout")):
        for j, name in enumerate(MODEL_NAMES):
            c = results[ds][name]["per_epoch"]
            mat = np.array([[c["tn"], c["fp"]], [c["fn"], c["tp"]]])
            rowp = mat / mat.sum(axis=1, keepdims=True)
            ax = axes[i, j]
            ax.imshow(rowp, cmap="Blues", vmin=0, vmax=1)
            for a in range(2):
                for b in range(2):
                    ax.text(b, a, f"{mat[a, b]}\n{rowp[a, b]:.0%}", ha="center", va="center",
                            color="white" if rowp[a, b] > 0.55 else "black", fontsize=11)
            ax.set_xticks([0, 1], ["pred EO", "pred EC"])
            ax.set_yticks([0, 1], ["true EO", "true EC"])
            ax.set_title(f"{'CV (S001–S050, OOF)' if ds == 'cv' else 'Holdout (S061–S109)'} · {LABELS[name]}\n"
                         f"bal. acc {c['balanced_accuracy']:.2f} · n {c['n']}", fontsize=10)
    fig.suptitle("Eyes-open vs eyes-closed, per 4 s epoch, threshold 0.5 (frontal8)", fontsize=11)
    fig.tight_layout()
    FIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_PATH, dpi=130)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    metrics = json.loads(config.METRICS_PATH.read_text(encoding="utf-8"))
    holdout = json.loads(config.HOLDOUT_PATH.read_text(encoding="utf-8"))

    # ---- CV: recompute OOF with the identical folds/params and verify against the stored run
    # Full-precision features (epoch_features.csv is rounded to 6 dp, which shifts LightGBM splits).
    jobs = [(s, c) for s in config.REFERENCE_SUBJECTS for c in config.CONDITIONS]
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        tables = list(ex.map(_extract_epochs, jobs))
    train = pd.concat([t for t in tables if not t.empty], ignore_index=True)
    cv = cross_validate(train)
    for stored, new in zip(metrics["folds"], cv["folds"]):
        for k in ("lgbm_acc", "lr_acc", "lgbm_auc", "lr_auc"):
            if abs(stored[k] - new[k]) > 1e-3:
                raise AssertionError(f"OOF recomputation differs from metrics.json: fold {stored['fold']} {k} {stored[k]} vs {new[k]}")
    print("CV OOF recomputed: fold accuracies/AUCs match metrics.json (|diff| <= 1e-3)")

    # ---- holdout: saved models, no refit
    art = ml_sanity.load_model()
    ho = _holdout_epochs(args.workers)
    if len(ho) != holdout["n_epochs"]:
        raise AssertionError(f"holdout epochs {len(ho)} != holdout.json {holdout['n_epochs']}")
    x_ho = ho[art["feature_names"]].astype(float)

    results = {"cv": {}, "holdout": {}}
    for name in MODEL_NAMES:
        results["cv"][name] = report(train, cv["oof"][name])
        results["holdout"][name] = report(ho, art[name].predict_proba(x_ho)[:, 1])

    for ds in ("cv", "holdout"):
        print(f"\n== {ds.upper()} ==")
        for name in MODEL_NAMES:
            r = results[ds][name]
            for level in ("per_epoch", "per_recording"):
                c = r[level]
                print(f"{LABELS[name]:8s} {level:13s} TN {c['tn']:4d} FP {c['fp']:4d} FN {c['fn']:4d} TP {c['tp']:4d} | "
                      f"prec {c['precision']:.3f} rec {c['recall']:.3f} spec {c['specificity']:.3f} "
                      f"F1 {c['f1']:.3f} bal {c['balanced_accuracy']:.3f}")
            print(f"{'':8s} log-loss {r['log_loss']:.3f} (chance {r['log_loss_chance']:.3f}) | Brier {r['brier']:.3f} "
                  f"(chance 0.25, prior {r['brier_prior']:.3f})")
            print(f"{'':8s} calibration " + "; ".join(
                f"{b['bin']}: n {b['n']}, p {b['mean_p']:.2f} obs {b['observed_rate']:.2f}" if b["n"] else f"{b['bin']}: n 0"
                for b in r["calibration"]))

    command = "python scripts/report_classification.py"
    metrics["cv_extra"] = {"command": command, "threshold": 0.5, "positive": "eyes_closed", **results["cv"]}
    holdout["extra"] = {"command": command, "threshold": 0.5, "positive": "eyes_closed", **results["holdout"]}
    config.METRICS_PATH.write_text(json.dumps(metrics, indent=1, allow_nan=False), encoding="utf-8")
    config.HOLDOUT_PATH.write_text(json.dumps(holdout, indent=1, allow_nan=False, default=float), encoding="utf-8")
    _figure(results)
    print(f"\nWrote metrics.json[cv_extra], holdout.json[extra], {FIG_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
