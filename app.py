"""Streamlit dashboard for the AI Finance Controller multi-agent system.

Run: streamlit run app.py
(run `python cli.py demo` at least once first to generate reports/)
"""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from agents import forecast_agent
from agents.orchestrator import handle as agent_handle

REPORTS_DIR = Path(__file__).resolve().parent / "reports"

st.set_page_config(page_title="AI Finance Controller", layout="wide")
st.title("AI Finance Controller — multi-agent system")
st.caption("Reconciliation, Settlement Q&A, Cash Forecaster and Exception & Anomaly agents, all grounded in scored real data.")

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

st.subheader("Cash forecast")
st.caption("Pure arithmetic over real settlement data, plus the reconciliation agent's own exception list — no LLM, nothing estimated that could just be computed.")
horizon = st.slider("Forecast horizon (days)", 3, 30, 7)
forecast = forecast_agent.forecast(horizon_days=horizon)
if "error" in forecast:
    st.info(forecast["error"])
else:
    proj_df = pd.DataFrame(forecast["projection"])
    st.line_chart(proj_df.set_index("date")["projected_amount"])
    fcol1, fcol2 = st.columns(2)
    fcol1.metric("Historical daily avg settlement", f"Rs.{forecast['historical_daily_average']:,.2f}")
    fcol2.metric("At risk (pending settlement)", f"Rs.{forecast['at_risk_amount_pending_settlement']:,.2f}")
    if forecast["drift_note"]:
        st.warning(forecast["drift_note"])

st.subheader("Ask the Finance Controller")
st.caption("Routed by the orchestrator to whichever specialist agent can actually answer — try a reference ID, or ask about fees, duplicates, drift, or match rate.")
user_question = st.text_input("Ask a question", placeholder="why didn't RZP... settle / show duplicate exceptions / what's our match rate")
if user_question:
    st.code(agent_handle(user_question), language=None)
