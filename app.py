"""Streamlit dashboard for the AI Finance Controller multi-agent system.

Run: streamlit run app.py
(run `python cli.py demo` at least once first to generate reports/)
"""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from agents import claim_verifier, forecast_agent
from agents.orchestrator import handle as agent_handle

REPORTS_DIR = Path(__file__).resolve().parent / "reports"

CATEGORY_BADGE_COLOR = {
    "exact": "green",
    "fee_adjustment": "green",
    "timing": "blue",
    "corrupted_ref": "blue",
    "matched_no_reference": "orange",
    "missing_in_settlement": "red",
    "missing_in_ledger": "red",
    "duplicate_settlement": "orange",
    "ambiguous_no_reference": "red",
    "systematic_drift_suspected": "violet",
}

SUGGESTIONS = {
    ":blue[:material/query_stats:] What's our match rate?": "what's our match rate",
    ":orange[:material/help:] Show ambiguous exceptions": "show ambiguous exceptions",
    ":green[:material/payments:] How much did we pay in fees?": "how much did we pay in fees",
    ":violet[:material/trending_up:] Cash forecast for 14 days": "cash forecast for 14 days",
}

st.set_page_config(page_title="AI Finance Controller", page_icon=":material/account_balance:", layout="wide")
st.title("AI Finance Controller — multi-agent system")
st.caption("Reconciliation, Settlement Q&A, Cash Forecaster and Exception & Anomaly agents, all grounded in scored real data.")

summary_path = REPORTS_DIR / "summary.json"
if not summary_path.exists():
    st.warning("No report found yet. Run `python cli.py demo` first, then reload this page.", icon=":material/warning:")
    st.stop()

summary = json.loads(summary_path.read_text())

with st.container(horizontal=True):
    st.metric("Ledger rows", summary["ledger_rows"], border=True)
    st.metric("Match rate", f"{summary['match_rate'] * 100:.1f}%", border=True)
    st.metric("Exceptions", summary["exceptions"], border=True)
    st.metric("Accuracy vs ground truth", f"{(summary['overall_accuracy'] or 0) * 100:.1f}%", border=True)

overview_tab, exceptions_tab, matches_tab, forecast_tab, ask_tab, claim_tab = st.tabs([
    "Overview", "Exceptions", "Matched pairs", "Cash forecast", "Ask the controller", "Verify a claim",
])

with overview_tab:
    with st.container(border=True):
        st.markdown("**Accuracy by category**")
        per_cat = summary["per_category"]
        cat_df = pd.DataFrame([
            {"category": cat, "correct": v["correct"], "total": v["total"], "accuracy": v["accuracy"]}
            for cat, v in per_cat.items()
        ])
        st.bar_chart(cat_df.set_index("category")["accuracy"])
        st.dataframe(cat_df, width="stretch", hide_index=True)

    with st.expander("Misclassified rows (matcher disagreed with ground truth)", icon=":material/error:"):
        misses = summary.get("misclassified", [])
        if misses:
            st.dataframe(pd.DataFrame(misses), width="stretch", hide_index=True)
        else:
            st.write("None — every ground-truth row was categorized correctly in this run.")

with exceptions_tab:
    exceptions_path = REPORTS_DIR / "exceptions.csv"
    if exceptions_path.exists() and exceptions_path.stat().st_size > 0:
        exc_df = pd.read_csv(exceptions_path).fillna("")

        with st.container(horizontal=True):
            for cat, count in exc_df["category"].value_counts().items():
                st.badge(f"{cat}: {count}", color=CATEGORY_BADGE_COLOR.get(cat, "gray"))

        categories = ["All"] + sorted(exc_df["category"].unique().tolist())
        choice = st.selectbox("Filter by category", categories)
        if choice != "All":
            exc_df = exc_df[exc_df["category"] == choice]
        st.dataframe(exc_df, width="stretch", hide_index=True)
    else:
        st.info("No exceptions in this run.")

with matches_tab:
    matches_path = REPORTS_DIR / "matches.csv"
    if matches_path.exists() and matches_path.stat().st_size > 0:
        matches_df = pd.read_csv(matches_path).fillna("")
        st.dataframe(
            matches_df,
            width="stretch",
            hide_index=True,
            column_config={
                "confidence": st.column_config.ProgressColumn(
                    "confidence", min_value=0.0, max_value=1.0, format="%.2f",
                ),
            },
        )

with forecast_tab:
    st.caption("Pure arithmetic over real settlement data, plus the reconciliation agent's own exception list — no LLM, nothing estimated that could just be computed.")
    horizon = st.slider("Forecast horizon (days)", 3, 30, 7)
    forecast = forecast_agent.forecast(horizon_days=horizon)
    if "error" in forecast:
        st.info(forecast["error"])
    else:
        proj_df = pd.DataFrame(forecast["projection"])
        st.line_chart(proj_df.set_index("date")["projected_amount"])
        with st.container(horizontal=True):
            st.metric("Historical daily avg settlement", f"Rs.{forecast['historical_daily_average']:,.2f}", border=True)
            st.metric("At risk (pending settlement)", f"Rs.{forecast['at_risk_amount_pending_settlement']:,.2f}", border=True)
        if forecast["drift_note"]:
            st.warning(forecast["drift_note"], icon=":material/warning:")

with ask_tab:
    st.caption("Routed by the orchestrator to whichever specialist agent can actually answer — no hallucinated numbers, every answer traces back to a real row.")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    prompt = None
    if not st.session_state.chat_history:
        selected = st.pills("Try asking:", list(SUGGESTIONS.keys()), label_visibility="collapsed")
        if selected:
            prompt = SUGGESTIONS[selected]

    typed = st.chat_input("Ask a question")
    if typed:
        prompt = typed

    if prompt:
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)
        # agent responses are plain multi-line text, not markdown -- a single
        # "\n" renders as a space in markdown, collapsing exception lists and
        # forecast tables into one run-on line. Hard line breaks fix that.
        response = agent_handle(prompt).replace("\n", "  \n")
        with st.chat_message("assistant"):
            st.write(response)
        st.session_state.chat_history.append({"role": "assistant", "content": response})

with claim_tab:
    st.caption("A customer or merchant claims something happened to a payment. Check it against the actual reconciliation record instead of taking it at face value.")
    st.caption("Never declares anyone dishonest — a mismatch is flagged for human review, not resolved automatically.")

    if "claim_chat_history" not in st.session_state:
        st.session_state.claim_chat_history = []

    for message in st.session_state.claim_chat_history:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    claim_prompt = None
    if not st.session_state.claim_chat_history:
        claim_examples = {}
        matches_path = REPORTS_DIR / "matches.csv"
        exceptions_path = REPORTS_DIR / "exceptions.csv"
        if matches_path.exists() and matches_path.stat().st_size > 0:
            ref = pd.read_csv(matches_path)["txn_ref"].iloc[0]
            label = f":red[:material/report:] \"I never received my payout for {ref}\""
            claim_examples[label] = f"I never received my payout for {ref}"
        if exceptions_path.exists() and exceptions_path.stat().st_size > 0:
            exc_df = pd.read_csv(exceptions_path)
            exc_refs = exc_df[exc_df["txn_ref"] != ""]
            if len(exc_refs):
                ref = exc_refs["txn_ref"].iloc[0]
                label = f":green[:material/check_circle:] \"My payment {ref} went through fine\""
                claim_examples[label] = f"My payment {ref} went through fine"
        if claim_examples:
            selected_claim = st.pills("Try a claim:", list(claim_examples.keys()), label_visibility="collapsed")
            if selected_claim:
                claim_prompt = claim_examples[selected_claim]

    typed_claim = st.chat_input("Describe what the customer or merchant is claiming")
    if typed_claim:
        claim_prompt = typed_claim

    if claim_prompt:
        st.session_state.claim_chat_history.append({"role": "user", "content": claim_prompt})
        with st.chat_message("user"):
            st.write(claim_prompt)
        result = claim_verifier.verify(claim_prompt)
        badge_color = {
            "confirmed": "green",
            "contradicted": "red",
            "no_record": "gray",
            "no_reference": "gray",
        }[result["verdict"]]
        verdict_label = result["verdict"].replace("_", " ")
        formatted = f":{badge_color}-badge[{verdict_label}]  \n{result['message']}"
        with st.chat_message("assistant"):
            st.write(formatted)
        st.session_state.claim_chat_history.append({"role": "assistant", "content": formatted})
