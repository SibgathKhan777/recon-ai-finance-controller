"""Streamlit dashboard for the reconciliation agent.

Run: streamlit run app.py
(run `python cli.py demo` at least once first to generate reports/)
"""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

REPORTS_DIR = Path(__file__).resolve().parent / "reports"

st.set_page_config(page_title="AI Finance Controller - Recon Agent", layout="wide")
st.title("AI Finance Controller — Reconciliation Agent")
st.caption("Deterministic matching + LLM exception explanations, scored against known ground truth.")

summary_path = REPORTS_DIR / "summary.json"
if not summary_path.exists():
    st.warning("No report found yet. Run `python cli.py demo` first, then reload this page.")
    st.stop()

summary = json.loads(summary_path.read_text())

col1, col2, col3, col4 = st.columns(4)
col1.metric("Ledger rows", summary["ledger_rows"])
col2.metric("Match rate", f"{summary['match_rate'] * 100:.1f}%")
col3.metric("Exceptions", summary["exceptions"])
col4.metric("Accuracy vs ground truth", f"{(summary['overall_accuracy'] or 0) * 100:.1f}%")

st.subheader("Accuracy by category")
per_cat = summary["per_category"]
cat_df = pd.DataFrame([
    {"category": cat, "correct": v["correct"], "total": v["total"], "accuracy": v["accuracy"]}
    for cat, v in per_cat.items()
])
st.bar_chart(cat_df.set_index("category")["accuracy"])
st.dataframe(cat_df, use_container_width=True)

st.subheader("Exceptions")
exceptions_path = REPORTS_DIR / "exceptions.csv"
if exceptions_path.exists() and exceptions_path.stat().st_size > 0:
    exc_df = pd.read_csv(exceptions_path)
    categories = ["All"] + sorted(exc_df["category"].unique().tolist())
    choice = st.selectbox("Filter by category", categories)
    if choice != "All":
        exc_df = exc_df[exc_df["category"] == choice]
    st.dataframe(exc_df, use_container_width=True)
else:
    st.info("No exceptions in this run.")

st.subheader("Matched pairs")
matches_path = REPORTS_DIR / "matches.csv"
if matches_path.exists() and matches_path.stat().st_size > 0:
    st.dataframe(pd.read_csv(matches_path), use_container_width=True)

with st.expander("Misclassified rows (matcher disagreed with ground truth)"):
    misses = summary.get("misclassified", [])
    if misses:
        st.dataframe(pd.DataFrame(misses))
    else:
        st.write("None — every ground-truth row was categorized correctly in this run.")
