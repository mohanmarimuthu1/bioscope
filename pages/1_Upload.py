"""Upload: run one recording through the pipeline and save it as a session."""
import tempfile
from pathlib import Path

import streamlit as st

from src import config, pipeline, ui

SAMPLE = config.DATA_SAMPLE / "sample_frontal8_raw.fif"
LINE_FREQS = {"60 Hz (Americas; the PhysioNet sample)": 60.0, "50 Hz (India, Europe)": 50.0}


def _process(path: Path, name: str, subject: str, preset: str, condition: str, line_freq: float) -> None:
    if not subject.strip():
        st.error("Please enter a subject ID before processing.")
        return
    bar = st.progress(0.0)
    with st.status("Running the pipeline…", expanded=True) as status:
        def step(i: int, label: str) -> None:
            bar.progress(i / len(pipeline.STEPS), text=label)
            st.write(f"{i + 1}. {label}")
        try:
            res = pipeline.run(path, preset, condition, line_freq, progress=step)
        except pipeline.PipelineError as exc:
            status.update(label="Could not process this file", state="error")
            bar.empty()
            st.error(str(exc))
            return
        st.write(f"{len(pipeline.STEPS) + 1}. Save session")
        sid = pipeline.save(res, subject, f"Upload: {name}", name, db_path=ui.db_path())
        bar.progress(1.0, text="Done")
        status.update(label=f"Done in {res['timings_s']['total']:.1f} s", state="complete", expanded=False)
    st.session_state["last_session_id"] = sid
    st.session_state["last_subject"] = subject.strip()

    qc, sc = res["qc"], res["score"]
    if sc["composite"] is None:
        st.error(f"No score: {qc['n_kept']}/{qc['n_total']} epochs survived artefact rejection, so there is no clean signal to score. "
                 "The session was saved with its warnings. Try a longer or cleaner recording.")
    else:
        st.success(f"Composite **{sc['composite']:.1f}** (confidence {sc['confidence']:.2f}) — "
                   f"{qc['n_kept']}/{qc['n_total']} clean epochs, {res['meta']['duration_s']:.0f} s, "
                   f"vs {ui.CONDITION_LABELS[condition].lower()} {preset} reference.")
    for w in sc["warnings"]:
        st.warning(w)
    st.page_link("pages/2_Session.py", label="Open the session breakdown →")


def body() -> None:
    st.title("Upload a recording")
    st.markdown("Resting EEG, ideally **60 s or more**, in **.edf** or **.fif**. Channel names are matched to the chosen preset "
                "(PhysioNet-style labels like `Fp1.` are normalised).")
    c1, c2 = st.columns(2)
    subject = c1.text_input("Subject ID", value="S060")
    preset = c2.selectbox("Channel preset", list(config.PRESETS), format_func=lambda p: ui.PRESET_LABELS.get(p, p))
    c3, c4 = st.columns(2)
    condition = c3.radio("Condition", list(config.CONDITIONS), format_func=ui.CONDITION_LABELS.get, horizontal=True)
    line_label = c4.radio("Mains (line) frequency", list(LINE_FREQS), horizontal=True)
    st.caption(f"Preset channels: {', '.join(config.PRESETS[preset]['channels'])}. "
               "The score uses the reference for the same preset and condition.")

    up = st.file_uploader("EEG file", type=["edf", "fif"])
    b1, b2 = st.columns([1, 1])
    run_upload = b1.button("Process uploaded file", type="primary", disabled=up is None)
    run_sample = b2.button("Load sample (S060 eyes-open)")

    if run_sample:
        if not SAMPLE.exists():
            st.error("The sample file data/sample/sample_frontal8_raw.fif is missing from this checkout.")
            return
        st.info("Sample: held-out subject S060, eyes-open rest, 61 s, frontal8, recorded in the US (60 Hz).")
        _process(SAMPLE, SAMPLE.name, subject or "S060", preset, condition, LINE_FREQS[line_label])
    elif run_upload and up is not None:
        with tempfile.TemporaryDirectory(dir=config.ROOT / "data") as tmp:      # deleted right after processing
            path = Path(tmp) / Path(up.name).name
            path.write_bytes(up.getbuffer())
            _process(path, up.name, subject, preset, condition, LINE_FREQS[line_label])


ui.setup_page("Upload")
ui.guard(body)
