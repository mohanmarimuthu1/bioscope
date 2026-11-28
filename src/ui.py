"""ui — shared Streamlit helpers for app.py and pages/ (P7).

WHAT:  page setup, cached loaders (model, reference, metrics, holdout), first-run demo seeding, an error guard that
       turns any exception into st.error (never a traceback), display labels and the plotly chart builders.
WHY:   Pages stay short and consistent; all science lives in src/ and is only displayed here.
CAVEATS:
  - DB path = env var BIOSCOPE_DB if set (tests), else config.DB_PATH.
  - Charts use no hard-coded text colours and semi-transparent bands, so they read in light and dark mode
    (st.plotly_chart(theme="streamlit") supplies fonts/background).
"""
from __future__ import annotations

import json
import logging
import os
import warnings
from pathlib import Path
from typing import Callable

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from src import config, db, ml_sanity, pipeline

log = logging.getLogger("bioscope.ui")

CONDITION_LABELS = {"eyes_open": "Eyes open", "eyes_closed": "Eyes closed"}
PRESET_LABELS = {"frontal8": "frontal8 (8-ch frontal)", "muse4": "muse4 (Muse-like 4-ch)"}
DIMENSION_LABELS = {"attention": "Attention", "relaxation": "Relaxation", "load": "Arousal / Load", "signal_quality": "Signal quality"}
FEATURE_LABELS = {
    "tbr_osc": "Theta/beta ratio (rhythm)", "tbr_classic": "Theta/beta ratio (classic)", "paf": "Peak alpha frequency",
    "alpha_exc": "Alpha rhythm power", "faa": "Frontal alpha asymmetry", "hibeta_exc": "High-beta rhythm power",
    "ap_exponent": "1/f slope (aperiodic exponent)",
}
RED, AMBER, GREEN = "rgba(214,69,65,0.45)", "rgba(240,173,78,0.45)", "rgba(46,160,67,0.45)"
VALIDATION_WORDING = ("Validation: features separate eyes-open from eyes-closed well above chance (AUC {auc:.2f}, paired {paired:.0%} "
                      "of subjects, p < 0.01); frontal-only EEG limits per-epoch accuracy.")


# --------------------------------------------------------------------------- setup
def setup_page(title: str) -> None:
    """Page config + quiet library logs. Call first on every page."""
    st.set_page_config(page_title=f"{title} · BioScope EEG", layout="wide")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    import mne
    mne.set_log_level("ERROR")
    warnings.filterwarnings("ignore")


def db_path() -> Path:
    return Path(os.environ.get(config.DB_ENV_VAR) or config.DB_PATH)


def guard(fn: Callable[[], None]) -> None:
    """Run a page body; any error becomes a friendly st.error (details go to the log, not the screen)."""
    try:
        fn()
    except pipeline.PipelineError as exc:
        st.error(str(exc))
    except FileNotFoundError as exc:
        log.exception("missing file")
        st.error(f"A required file is missing: {Path(str(exc.filename or exc)).name}. See README → Setup.")
    except Exception as exc:  # noqa: BLE001 — last line of defence for the demo
        log.exception("page error")
        st.error(f"Something went wrong ({type(exc).__name__}). The details were written to the terminal log.")


# --------------------------------------------------------------------------- cached loaders
@st.cache_resource
def model() -> dict:
    return ml_sanity.load_model()


@st.cache_resource
def _json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def reference_json() -> dict:
    return _json(str(config.REFERENCE_PATH))


def metrics_json() -> dict:
    return _json(str(config.METRICS_PATH))


def holdout_json() -> dict | None:
    return _json(str(config.HOLDOUT_PATH)) if config.HOLDOUT_PATH.exists() else None


def reference_n(condition: str, preset: str) -> int:
    return len(reference_json()["presets"][preset][condition]["subjects_used"])


def validation_sentence() -> str:
    s = metrics_json()["summary"]
    return VALIDATION_WORDING.format(auc=s["lgbm_auc"]["mean"], paired=s["lgbm_paired_acc"]["value"])


# --------------------------------------------------------------------------- demo seeding
def _needs_seed() -> bool:
    df = db.load_subject(config.DEMO_LONGITUDINAL_SUBJECT, db_path=db_path())
    return len(df) == 0 or not df["extras"].iloc[0]       # missing, or seeded before ADR-014 (no spectrum)


def ensure_seeded() -> None:
    """First run: score the 13 committed demo sessions into the DB (no raw data needed)."""
    if st.session_state.get("seed_checked"):
        return
    if _needs_seed():
        bar = st.progress(0.0, text="First run: scoring the 13 demo sessions (S051)…")
        with st.spinner("Preparing the longitudinal demo — about 20 s, only once."):
            pipeline.seed_demo(progress=lambda i, n, name: bar.progress(i / n, text=f"Scoring demo session {i + 1}/{n}: {name}"),
                               db_path=db_path())
        bar.empty()
    st.session_state["seed_checked"] = True


# --------------------------------------------------------------------------- formatting
def fmt(x, nd: int = 2, unit: str = "") -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x:.{nd}f}{unit}"


def band_color(v: float | None) -> str:
    if v is None:
        return "rgba(128,128,128,0.4)"
    return RED if v < config.GAUGE_RED_BELOW else AMBER if v <= config.GAUGE_GREEN_ABOVE else GREEN


# --------------------------------------------------------------------------- charts
def _layout(fig: go.Figure, height: int, **kw) -> go.Figure:
    kw.setdefault("margin", dict(l=10, r=10, t=40, b=10))
    fig.update_layout(height=height, **kw)
    return fig


def gauge(value: float | None, title: str) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value if value is not None else 0,
        number={"suffix": "" if value is not None else " (n/a)", "valueformat": ".0f"},
        title={"text": title, "font": {"size": 15}},
        gauge={"axis": {"range": [0, 100]}, "bar": {"color": "rgba(90,110,200,0.9)", "thickness": 0.3},
               "steps": [{"range": [0, config.GAUGE_RED_BELOW], "color": RED},
                         {"range": [config.GAUGE_RED_BELOW, config.GAUGE_GREEN_ABOVE], "color": AMBER},
                         {"range": [config.GAUGE_GREEN_ABOVE, 100], "color": GREEN}]}))
    return _layout(fig, 210, margin=dict(l=20, r=20, t=50, b=0))


def z_bars(feature_z: dict) -> go.Figure:
    items = [(FEATURE_LABELS.get(k, k), v) for k, v in feature_z.items() if v is not None]
    names, zs = [n for n, _ in items], [z for _, z in items]
    colors = [GREEN if abs(z) < 1 else AMBER if abs(z) < 2 else RED for z in zs]
    fig = go.Figure(go.Bar(x=zs, y=names, orientation="h", marker_color=colors, text=[f"{z:+.2f}" for z in zs],
                           textposition="outside", hovertemplate="%{y}: z = %{x:+.2f}<extra></extra>"))
    fig.add_vline(x=0, line_width=1, opacity=0.5)
    lim = max(4.0, max((abs(z) for z in zs), default=0) + 0.8)
    return _layout(fig, 300, title="Feature z vs reference (0 = reference mean; |z| > 2 is unusual)",
                   xaxis=dict(range=[-lim, lim], title="z"), yaxis=dict(autorange="reversed"))


def psd_fig(spectrum: dict) -> go.Figure:
    f = np.asarray(spectrum["freqs"], dtype=float)
    psd = np.asarray(spectrum["psd_uv2"], dtype=float)
    ap = np.asarray(spectrum["ap_fit_uv2"], dtype=float)
    fig = go.Figure()
    for i, ch in enumerate(spectrum["ch_names"]):
        fig.add_trace(go.Scatter(x=f, y=psd[i], mode="lines", name=ch, opacity=0.35, line=dict(width=1),
                                 legendgroup="ch", showlegend=False, hovertemplate=f"{ch}: %{{y:.3g}} µV²/Hz at %{{x}} Hz<extra></extra>"))
    fig.add_trace(go.Scatter(x=f, y=np.nanmedian(psd, axis=0), mode="lines", name="Median spectrum", line=dict(width=3)))
    fig.add_trace(go.Scatter(x=f, y=np.nanmedian(ap, axis=0), mode="lines", name="Aperiodic (1/f) fit", line=dict(width=2, dash="dash")))
    for lo, hi, name in ((4, 8, "θ"), (8, 13, "α"), (20, 30, "high β")):
        fig.add_vrect(x0=lo, x1=hi, opacity=0.08, line_width=0, annotation_text=name, annotation_position="top left")
    return _layout(fig, 360, title="Power spectrum (thin lines = channels) with the 1/f background fit",
                   xaxis_title="Frequency (Hz)", yaxis=dict(type="log", title="Power (µV²/Hz)"),
                   legend=dict(orientation="h", y=-0.2))


def shap_fig(ml: dict, top: int = 8) -> go.Figure:
    vals = np.asarray(ml["mean_shap"], dtype=float)
    order = np.argsort(np.abs(vals))[::-1][:top]
    names = [ml["feature_names"][i] for i in order]
    v = vals[order]
    fig = go.Figure(go.Bar(x=v, y=names, orientation="h", marker_color=["rgba(90,110,200,0.8)" if x > 0 else "rgba(240,140,60,0.8)" for x in v],
                           hovertemplate="%{y}: %{x:+.3f} log-odds<extra></extra>"))
    fig.add_vline(x=0, line_width=1, opacity=0.5)
    return _layout(fig, 300, title="What pushed the check (mean SHAP; right = toward eyes-closed, left = toward eyes-open)",
                   xaxis_title="Mean SHAP (log-odds)", yaxis=dict(autorange="reversed"))
