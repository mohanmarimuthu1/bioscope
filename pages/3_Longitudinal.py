"""Longitudinal: score trend, EMA, Bayesian posterior band, flags and deltas versus the personal baseline."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import config, db, longitudinal, ui

NAMED = {"tbr_osc": "TBR (rhythm)", "tbr_classic": "TBR (classic)", "paf": "PAF (Hz)", "hibeta_exc": "High beta (µV²)"}


def _trend_fig(x, scores, e, post, flags, base) -> go.Figure:
    pm = np.array([m for m, _ in post])
    ps = np.array([s for _, s in post])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=list(x) + list(x)[::-1], y=list(pm + ps) + list(pm - ps)[::-1], fill="toself",
                             fillcolor="rgba(90,110,200,0.18)", line=dict(width=0), hoverinfo="skip", name="Posterior ±1 sd"))
    fig.add_trace(go.Scatter(x=x, y=pm, mode="lines", line=dict(width=1.5, dash="dot"), name="Posterior mean"))
    fig.add_trace(go.Scatter(x=x, y=scores, mode="lines+markers", name="Composite", line=dict(width=2.5), marker=dict(size=8)))
    fig.add_trace(go.Scatter(x=x, y=e, mode="lines", name=f"EMA (α = {config.EMA_ALPHA})", line=dict(width=2)))
    fx = [xi for xi, f in zip(x, flags) if f]
    if fx:
        fig.add_trace(go.Scatter(x=fx, y=[s for s, f in zip(scores, flags) if f], mode="markers", name="Flagged shift (> 2 SD)",
                                 marker=dict(size=16, symbol="x", color="rgb(214,69,65)")))
    fig.add_hrect(y0=base["mean"] - config.FLAG_Z * base["std"], y1=base["mean"] + config.FLAG_Z * base["std"],
                  fillcolor="rgba(46,160,67,0.10)", line_width=0)
    fig.add_hline(y=base["mean"], line_dash="dash", opacity=0.6,
                  annotation_text=f"Baseline {base['mean']:.1f} ± {base['std']:.2f} (first {base['n']}; band = ±2 SD)")
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10), xaxis_title="Session", yaxis_title="Composite (0–100)",
                      legend=dict(orientation="h", y=-0.2))
    return fig


def _mini(x, y, title: str) -> go.Figure:
    fig = go.Figure(go.Scatter(x=x, y=y, mode="lines+markers", line=dict(width=2)))
    fig.update_layout(height=200, margin=dict(l=10, r=10, t=35, b=10), title=dict(text=title, font=dict(size=14)),
                      yaxis=dict(range=[0, 100]), showlegend=False)
    return fig


def body() -> None:
    st.title("Longitudinal tracking")
    ui.ensure_seeded()
    subjects = db.list_subjects(db_path=ui.db_path())
    if not subjects:
        st.info("No sessions yet.")
        return
    default = config.DEMO_LONGITUDINAL_SUBJECT
    subj = st.selectbox("Subject", subjects, index=subjects.index(default) if default in subjects else 0)
    if subj == config.DEMO_LONGITUDINAL_SUBJECT:
        st.info(f"Demo subject {subj}: {config.DEMO_LABEL}")

    df = db.load_subject(subj, db_path=ui.db_path())
    ok = df[df["composite"].notna()].reset_index(drop=True)
    skipped = len(df) - len(ok)
    if len(ok) == 0:
        st.warning("No scored sessions for this subject yet.")
        return
    if skipped:
        st.warning(f"{skipped} session(s) had no clean signal and are left out of the trend.")
    scores = ok["composite"].astype(float).tolist()
    conf = ok["confidence"].astype(float).tolist()
    x = ok["session_index"].tolist()
    base = longitudinal.compute_baseline(scores)
    if base["provisional"]:
        st.caption(f"Provisional baseline: only {base['n']} session(s) so far (needs {config.BASELINE_N}).")
    e = longitudinal.ema(scores)
    post = longitudinal.bayesian_track(scores, longitudinal.obs_sd_from_confidence(conf))
    flags = longitudinal.flag_shifts(scores, base)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sessions scored", len(ok))
    c2.metric("Baseline", f"{base['mean']:.1f} ± {base['std']:.2f}")
    c3.metric("Latest posterior", f"{post[-1][0]:.1f} ± {post[-1][1]:.1f}")
    c4.metric("Flagged sessions", sum(flags))
    st.plotly_chart(_trend_fig(x, scores, e, post, flags, base), width="stretch", theme="streamlit")

    st.subheader("Dimensions over time")
    cols = st.columns(4)
    dims = {k: [ (s.get("dimensions") or {}).get(k) for s in ok["score"]] for k in ui.DIMENSION_LABELS}
    for col, (k, label) in zip(cols, ui.DIMENSION_LABELS.items()):
        col.plotly_chart(_mini(x, [v if v is not None else np.nan for v in dims[k]], label), width="stretch",
                         theme="streamlit", key=f"mini_{k}")

    st.subheader(f"Change versus baseline (mean of the first {base['n']} sessions)")
    table = {"Session": [f"#{i}" for i in x], "Label": ok["label"].tolist(), "Composite": scores,
             "Δ composite": longitudinal.deltas_vs_baseline(scores)}
    for k, label in ui.DIMENSION_LABELS.items():
        table[f"Δ {label}"] = longitudinal.deltas_vs_baseline([v if v is not None else np.nan for v in dims[k]])
    for k, label in NAMED.items():
        vals = [(s.get("named_metrics") or {}).get(k) for s in ok["score"]]
        table[f"Δ {label}"] = longitudinal.deltas_vs_baseline([v if v is not None else np.nan for v in vals])
    table["Flag"] = ["shift" if f else "" for f in flags]
    out = pd.DataFrame(table)
    num = [c for c in out.columns if c.startswith("Δ") or c == "Composite"]
    st.dataframe(out.style.format({c: "{:+.2f}" if c.startswith("Δ") else "{:.1f}" for c in num}, na_rep="—"),
                 hide_index=True, width="stretch")
    st.caption("A session is flagged when it is more than 2 baseline SDs from the baseline mean (baseline sessions are never flagged).")


ui.setup_page("Longitudinal")
ui.guard(body)
