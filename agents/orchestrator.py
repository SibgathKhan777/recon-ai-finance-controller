"""Orchestrator: routes a natural-language message to the right specialist.

Rule-based intent matching by default -- always works, no API key needed,
and the routing decision is always inspectable rather than a black box
(you can see exactly which regex matched and why). If ANTHROPIC_API_KEY is
set, the Q&A agent's open-ended answers get phrased by Claude instead of a
template, but which specialist ran is decided by this deterministic router
either way.
"""
import csv
import re
from pathlib import Path

from recon import pipeline
from agents import action_ledger, claim_verifier, exception_agent, forecast_agent, qa_agent

RECONCILE_PATTERN = re.compile(r"\b(reconcil\w*|match ledger|run the pipeline)\b", re.I)
FORECAST_PATTERN = re.compile(r"\b(forecast|cash position|projected cash)\b", re.I)
TRIAGE_PATTERN = re.compile(r"\b(triage|prioriti[sz]e|what should i look at|summary of exceptions)\b", re.I)
# Requires an explicit trigger phrase rather than folding into general Q&A --
# a customer/merchant claim is a different persona than an internal analyst
# question, and blending them risks a claim being misread as routine Q&A.
VERIFY_CLAIM_PATTERN = re.compile(r"^\s*verify claim[:\-]?\s*(.+)", re.I)
HORIZON_PATTERN = re.compile(r"(\d+)\s*day", re.I)

MATCHES_PATH = Path(__file__).resolve().parent.parent / "reports" / "matches.csv"


def handle(message):
    if RECONCILE_PATTERN.search(message):
        summary = pipeline.run()
        action_ledger.record("orchestrator", "ran_reconciliation", "full pipeline re-run on request")
        _log_consequential_matches()
        return _format_summary(summary)

    if FORECAST_PATTERN.search(message):
        horizon_match = HORIZON_PATTERN.search(message)
        horizon = int(horizon_match.group(1)) if horizon_match else 7
        result = forecast_agent.forecast(horizon_days=horizon)
        if "error" not in result:
            action_ledger.record(
                "cash_forecaster", "forecast", f"{horizon}-day projection",
                amount=result.get("at_risk_amount_pending_settlement"),
            )
        return _format_forecast(result)

    if TRIAGE_PATTERN.search(message):
        return exception_agent.triage()

    verify_match = VERIFY_CLAIM_PATTERN.match(message)
    if verify_match:
        result = claim_verifier.verify(verify_match.group(1))
        return f"[{result['verdict']}] {result['message']}"

    return qa_agent.answer(message)


def _log_consequential_matches():
    """Every match the Reconciliation Agent made is a money decision --
    log the ones actually worth a second look (not perfect, or large) to
    the shared audit trail, letting action_ledger's own confidence/amount
    gates decide whether each one needs human sign-off."""
    if not MATCHES_PATH.exists():
        return
    with open(MATCHES_PATH, newline="") as f:
        for row in csv.DictReader(f):
            confidence = float(row["confidence"])
            amount = float(row["ledger_amount"])
            if confidence < 1.0 or abs(amount) >= action_ledger.APPROVAL_THRESHOLD:
                action_ledger.record(
                    "reconciliation_agent",
                    "matched",
                    f"{row['category']}: {row['ledger_id']}<->{row['settlement_id']} "
                    f"(ref {row['txn_ref'] or '(none)'})",
                    amount=amount,
                    confidence=confidence,
                )


def _format_summary(summary):
    return (
        f"Reconciliation run: {summary['matched_pairs']}/{summary['ledger_rows']} matched "
        f"({summary['match_rate'] * 100:.1f}%), {summary['exceptions']} exceptions, "
        f"{(summary['overall_accuracy'] or 0) * 100:.1f}% accuracy vs ground truth."
    )


def _format_forecast(result):
    if "error" in result:
        return result["error"]
    lines = [f"Historical daily average settlement: Rs.{result['historical_daily_average']:,.2f}"]
    lines.append("Projection:")
    for p in result["projection"]:
        lines.append(f"  {p['date']}: Rs.{p['projected_amount']:,.2f}")
    if result["at_risk_count"]:
        lines.append(
            f"At risk (pending settlement, not yet counted above): "
            f"Rs.{result['at_risk_amount_pending_settlement']:,.2f} across {result['at_risk_count']} rows"
        )
    if result["drift_note"]:
        lines.append(f"Note: {result['drift_note']}")
    return "\n".join(lines)
