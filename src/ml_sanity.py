"""ml_sanity — eyes-open / eyes-closed validation model (CLAUDE.md §7.8).

WHAT:  `predict(per_epoch)` → probability that a recording is eyes-closed, per-epoch SHAP values and feature names.
       Also holds the model builders (`make_lgbm`, `make_lr`) used by scripts/train_sanity_model.py, so the pickled
       LR pipeline can always be unpickled from an importable module.
WHY:   Pitch anchor 4: if the per-epoch features separate EO from EC on unseen subjects, the feature pipeline carries
       real signal. The model NEVER feeds the score.
CAVEATS:
  - Trained on frontal8 only (config.ML_PRESET). Callers must pass frontal8 per-epoch features.
  - The SHAP TreeExplainer is built at runtime and cached in memory; it is never pickled (§7.8).
  - SHAP values are in log-odds of eyes-closed; row sum + base_value = the model's raw margin.
  - Empty per-epoch table (0 clean epochs) → p_eyes_closed None + warning, no crash.
"""
from __future__ import annotations

import logging
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from src import config
from src.features import EPOCH_COLUMNS

log = logging.getLogger(__name__)

FEATURES: list[str] = [c for c in EPOCH_COLUMNS if c != "epoch"]   # 17 per-epoch features (ADR-007)
# ASSUMPTION: *_abs and *_exc are non-negative powers (µV²); heavy right tail, so LR sees log1p of them.
_POWER_IDX = [i for i, c in enumerate(FEATURES) if c.endswith(("_abs", "_exc"))]
EMPTY_WARNING = "No clean epochs: eyes-open/closed check not run"


def _log_power(x: np.ndarray) -> np.ndarray:
    """log1p of the power columns (negative values clipped to 0); other columns unchanged."""
    x = np.array(x, dtype=float, copy=True)
    x[:, _POWER_IDX] = np.log1p(np.clip(x[:, _POWER_IDX], 0.0, None))
    return x


def make_lgbm() -> LGBMClassifier:
    """LightGBM with the fixed, untuned parameters from config (NaN handled natively)."""
    return LGBMClassifier(**config.LGBM_PARAMS)


def make_lr() -> Pipeline:
    """Logistic Regression baseline: log1p powers → median impute → standardise → LR."""
    return Pipeline([
        ("log_power", FunctionTransformer(_log_power)),
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("lr", LogisticRegression(max_iter=config.LR_MAX_ITER, random_state=config.RANDOM_STATE)),
    ])


@lru_cache(maxsize=1)
def load_model() -> dict:
    """Load models/lgbm_eyes.joblib once: {lgbm, lr, feature_names, preset, train_subjects, ...}."""
    if not config.MODEL_PATH.exists():
        raise FileNotFoundError(f"{config.MODEL_PATH.name} missing: run python scripts/train_sanity_model.py")
    return joblib.load(config.MODEL_PATH)


@lru_cache(maxsize=1)
def _explainer():
    """SHAP TreeExplainer for the saved LightGBM model, built at runtime (never pickled)."""
    import shap
    return shap.TreeExplainer(load_model()["lgbm"])


def shap_matrix(expl, x: pd.DataFrame) -> tuple[np.ndarray, float]:
    """SHAP values (n_epochs, n_features) for the eyes-closed class and the base value, version-robust."""
    vals = expl.shap_values(x)
    base = np.atleast_1d(expl.expected_value)
    if isinstance(vals, list):                 # older shap: one array per class
        vals, base = vals[-1], base[-1:]
    vals = np.asarray(vals)
    if vals.ndim == 3:                         # (n, f, classes)
        vals, base = vals[..., -1], base[-1:]
    return vals, float(base[-1])


def predict(per_epoch: pd.DataFrame) -> dict:
    """Probability of eyes-closed for one recording's per-epoch features, with SHAP explanations.

    Returns {"p_eyes_closed": mean over epochs or None, "p_epochs": [...], "shap_values": (n_epochs, n_features),
    "base_value": float, "feature_names": [...], "warnings": [...]}.
    Raises ValueError if feature columns are missing.
    """
    model = load_model()
    names = list(model["feature_names"])
    missing = [c for c in names if c not in per_epoch.columns]
    if missing:
        raise ValueError(f"per-epoch table is missing feature columns: {missing}")
    if per_epoch.empty:
        return {"p_eyes_closed": None, "p_epochs": [], "shap_values": np.empty((0, len(names))),
                "base_value": float("nan"), "feature_names": names, "warnings": [EMPTY_WARNING]}
    x = per_epoch[names].astype(float)
    p = model["lgbm"].predict_proba(x)[:, 1]
    shap_vals, base = shap_matrix(_explainer(), x)
    log.info("ml_sanity: %d epochs, p_eyes_closed=%.3f", len(x), float(p.mean()))
    return {"p_eyes_closed": float(p.mean()), "p_epochs": p.tolist(), "shap_values": shap_vals,
            "base_value": base, "feature_names": names, "warnings": []}
