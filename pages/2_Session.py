"""Session: full breakdown of one saved session."""
import streamlit as st

from src import config, db, ui


def _pick_session():
    subjects = db.list_subjects(db_path=ui.db_path())
    if not subjects:
        st.info("No sessions yet. Upload a recording first.")
        st.page_link("pages/1_Upload.py", label="Go to Upload →")
        return None
    last = st.session_state.get("last_subject")
    c1, c2 = st.columns([1, 2])
    subj = c1.selectbox("Subject", subjects, index=subjects.index(last) if last in subjects else 0)
    df = db.load_subject(subj, db_path=ui.db_path())
    ids = df["id"].tolist()
    labels = {r.id: f"#{r.session_index} · {r.label or ''}" for r in df.itertuples()}
    last_id = st.session_state.get("last_session_id")
    sid = c2.selectbox("Session", ids, index=ids.index(last_id) if last_id in ids else len(ids) - 1, format_func=labels.get)
    return df[df["id"] == sid].iloc[0]


def _named_metrics(nm: dict) -> None:
    st.subheader("Named metrics")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Theta/beta ratio — rhythm", ui.fmt(nm.get("tbr_osc")), help="Theta / beta power above the 1/f background (used in the score)")
    c2.metric("Theta/beta ratio — classic", ui.fmt(nm.get("tbr_classic")), help="Classic absolute band-power ratio, shown for comparison")
    frac = nm.get("paf_fallback_frac")
    c3.metric("Peak alpha frequency", ui.fmt(nm.get("paf"), 2, " Hz"),
              help="Strongest alpha peak 8–13 Hz; channels without a peak use the 7–13 Hz centre of gravity")
    c3.caption(f"Fallback share: {ui.fmt(frac * 100 if frac is not None else None, 0, '%')} of channels had no alpha peak")
    c4.metric("High beta (20–30 Hz)", ui.fmt(nm.get("hibeta_exc"), 2, " µV²"), help="Rhythm power above the 1/f background")
    c4.caption(f"Classic: {ui.fmt(nm.get('hibeta_abs'), 2, ' µV²')}")


def _validation(ml: dict, preset: str) -> None:
    st.subheader("Feature-pipeline validation (never feeds the score)")
    if preset != config.ML_PRESET:
        st.info(f"Validation model is trained on {config.ML_PRESET} only.")
        return
    if not ml or not ml.get("available"):
        st.info((ml or {}).get("reason") or "No validation result stored for this session.")
        return
    st.caption(ui.validation_sentence())
    p = ml["p_eyes_closed"]
    lean = "eyes-closed" if p > 0.5 else "eyes-open"
    st.markdown(f"For this recording the check leans **{lean}** (mean model output {p:.2f} over {ml['n_epochs']} epochs). "
                "Read this as a direction, not a calibrated probability: on unseen subjects it reads about 2 in 3 epochs "
                "correctly, so a single recording can be misread. It checks the features; it does not judge this person.")
    st.plotly_chart(ui.shap_fig(ml), width="stretch", theme="streamlit")


def body() -> None:
    st.title("Session breakdown")
    ui.ensure_seeded()
    row = _pick_session()
    if row is None:
        return
    sc, extras = row["score"], row["extras"] or {}
    preset, condition = row["preset"], row["condition"]
    _named_metrics(sc.get("named_metrics") or {})

    st.subheader("Score")
    ref_txt = f"vs {ui.CONDITION_LABELS[condition].lower()} {preset} reference, n = {ui.reference_n(condition, preset)}"
    if sc.get("composite") is None:
        st.error(f"No composite score: not enough clean signal ({ref_txt}). See the warnings below.")
    else:
        c1, c2 = st.columns([1, 2])
        c1.metric("Composite (typicality, 0–100)", f"{sc['composite']:.1f}", help="100 = matches the reference mean on every feature")
        c1.markdown(f"Confidence **{sc['confidence']:.2f}**  \n{ref_txt}")
        c2.info("Typicality, not health: a high score means close to the reference group, not 'better'.")
    cols = st.columns(4)
    for col, (key, label) in zip(cols, ui.DIMENSION_LABELS.items()):
        col.plotly_chart(ui.gauge((sc.get("dimensions") or {}).get(key), label), width="stretch", theme="streamlit",
                         key=f"gauge_{key}")

    left, right = st.columns([3, 2])
    with left:
        fz = {k: v for k, v in (sc.get("feature_z") or {}).items() if k in ui.FEATURE_LABELS}
        if fz:
            st.plotly_chart(ui.z_bars(fz), width="stretch", theme="streamlit")
    with right:
        st.markdown("**Explanations**")
        for e in sc.get("explanations") or ["All features are within 1 SD of the reference."]:
            st.markdown(f"- {e}")
        warns = sc.get("warnings") or []
        if warns:
            st.markdown("**Warnings**")
            for w in warns:
                st.warning(w)

    if extras.get("spectrum"):
        st.plotly_chart(ui.psd_fig(extras["spectrum"]), width="stretch", theme="streamlit")
    else:
        st.info("No spectrum stored for this session.")
    _validation(extras.get("ml") or {}, preset)


ui.setup_page("Session")
ui.guard(body)
