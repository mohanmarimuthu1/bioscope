"""Methodology: the judge-facing science document plus the validation numbers read live from the model artefacts."""
import pandas as pd
import streamlit as st

from src import config, ui

FIGURE = config.ROOT / "docs" / "figures" / "confusion_matrix.png"


def _validation_tables() -> None:
    m, h = ui.metrics_json(), ui.holdout_json()
    s = m["summary"]
    st.subheader("Validation of the feature pipeline (eyes open vs eyes closed)")
    st.caption(ui.validation_sentence() + " The model never feeds the score.")
    og = m["original_gate"]
    st.warning(f"**Original gate, set before any evidence:** {og['rule']} → **FAIL** ({og['value']:.3f} ± {og['std']:.3f}, "
               f"ROC-AUC {og['auc']:.2f}). It was replaced *after* seeing this result (ADR-013) by: permutation p < "
               f"{config.GATE_PERM_P}, AUC > {config.GATE_AUC}, paired accuracy ≥ {config.GATE_PAIRED_ACC:.2f} → "
               f"{'PASS' if m['gate']['passed'] else 'FAIL'}.")

    rows = []
    for name, label in (("lgbm", "LightGBM"), ("lr", "Logistic regression")):
        rows.append({"Set": "CV, S001–S050 (GroupKFold 5 by subject)", "Model": label,
                     "Accuracy": f"{s[name + '_acc']['mean']:.3f} ± {s[name + '_acc']['std']:.3f}",
                     "ROC-AUC": f"{s[name + '_auc']['mean']:.3f} ± {s[name + '_auc']['std']:.3f}",
                     "Recording acc.": f"{s[name + '_rec_acc']['mean']:.3f}",
                     "Paired (subjects)": f"{s[name + '_paired_acc']['value']:.3f} (n={s[name + '_paired_acc']['n_subjects']})",
                     "Permutation p": f"{m['permutation'][name]['p_value']:.3f}",
                     "Balanced acc.": f"{m['cv_extra'][name]['per_epoch']['balanced_accuracy']:.3f}" if "cv_extra" in m else "—"})
        if h:
            hm = h["ml"][name]
            rows.append({"Set": "Holdout, S061–S109 (untouched, no refit)", "Model": label, "Accuracy": f"{hm['acc']:.3f}",
                         "ROC-AUC": f"{hm['auc']:.3f} [{hm['auc_ci95'][0]:.3f}, {hm['auc_ci95'][1]:.3f}]",
                         "Recording acc.": f"{hm['rec_acc']:.3f}", "Paired (subjects)": f"{hm['paired_acc']:.3f} (n={hm['paired_n']})",
                         "Permutation p": f"{hm['permutation']['p_value']:.3f}",
                         "Balanced acc.": f"{h['extra'][name]['per_epoch']['balanced_accuracy']:.3f}" if "extra" in h else "—"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("Chance: accuracy 0.5, AUC 0.5. Paired = share of subjects whose eyes-closed run gets a higher mean model output "
               "than their eyes-open run. Model outputs rank well but are not calibrated probabilities.")
    if FIGURE.exists():
        st.image(str(FIGURE), caption="Per-epoch confusion matrices at threshold 0.5 (eyes-closed = positive)", width=640)
    top = ", ".join(t["feature"] for t in m["shap"]["top"][:5])
    r = m["shap"]["best_alpha_rank"]
    rank = f"{r}{'th' if 10 <= r % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(r % 10, 'th')}"
    st.markdown(f"**Most influential features (SHAP):** {top}. The best alpha feature ranks {rank}: "
                "with eyes closed there is also less eye-movement and muscle activity at frontal sites.")


def _reference_table() -> None:
    ref = ui.reference_json()
    st.subheader("Reference used for scoring")
    rows = [{"Preset": p, "Condition": ui.CONDITION_LABELS[c], "Recordings (n)": len(cell["subjects_used"]),
             "Skipped (< 6 clean epochs)": len(cell["subjects_skipped"])}
            for p, cells in ref["presets"].items() for c, cell in cells.items()]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption(f"Built {ref['build_date'][:10]} from {ref['dataset']}, subjects S001–S050, runs R01 (eyes open) / R02 (eyes closed).")


def body() -> None:
    st.title("Methodology & validation")
    md = config.ROOT / "methodology.md"
    tab1, tab2 = st.tabs(["Validation & reference (live numbers)", "Methodology document"])
    with tab1:
        _validation_tables()
        _reference_table()
    with tab2:
        st.markdown(md.read_text(encoding="utf-8") if md.exists() else "methodology.md is missing.")


ui.setup_page("Methodology")
ui.guard(body)
