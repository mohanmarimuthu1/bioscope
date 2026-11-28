"""BioScope EEG — Streamlit home page. Run: streamlit run app.py"""
import streamlit as st

from src import ui


def body() -> None:
    st.title("BioScope EEG")
    st.caption("Zenix Bio Hackathon 01 · Round 2 · Problem Statement 3 · Team We2 — Mohankumar M")
    st.markdown(
        "BioScope turns a short resting recording from **4 or 8 frontal EEG channels** into one **0–100 score** of how "
        "*typical* the brain activity is compared with a condition-matched reference of 50 healthy adults (PhysioNet EEGMMI). "
        "Every score breaks down into four dimensions, seven features and their distance from the reference, and is shown with "
        "a confidence value and plain-language explanations. The three named metrics — **theta/beta ratio, peak alpha frequency "
        "and high beta** — are measured as rhythm power above the 1/f background, with classic values alongside. Repeated "
        "sessions are tracked against a personal baseline.")
    st.warning("**Typicality, not health — research prototype.** The score says how close a recording is to the reference "
               "group, not whether a brain is healthy. It is not a diagnostic device.")
    ui.ensure_seeded()

    st.subheader("How to use it")
    c1, c2, c3 = st.columns(3)
    c1.markdown("**1 · Upload**  \nChoose an .edf/.fif file (or the built-in sample), the channel preset, eyes open/closed "
                "and the mains frequency.")
    c2.markdown("**2 · Read the session**  \nComposite ± confidence, the named metrics, four dimension gauges, feature "
                "z-scores, the spectrum and the validation check.")
    c3.markdown("**3 · Track over time**  \nScore, moving average, Bayesian estimate and flagged changes versus the "
                "personal baseline (demo subject S051 is preloaded).")

    st.subheader("Pages")
    l1, l2, l3, l4 = st.columns(4)
    l1.page_link("pages/1_Upload.py", label="Upload a recording")
    l2.page_link("pages/2_Session.py", label="Session breakdown")
    l3.page_link("pages/3_Longitudinal.py", label="Longitudinal tracking")
    l4.page_link("pages/4_Methodology.py", label="Methodology & validation")


ui.setup_page("Home")
ui.guard(body)
