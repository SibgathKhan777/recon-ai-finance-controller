"""Orchestrator: routes a natural-language message to the right specialist.

Rule-based intent matching by default -- always works, no API key needed,
and the routing decision is always inspectable rather than a black box
(you can see exactly which regex matched and why). If ANTHROPIC_API_KEY is
set, the Q&A agent's open-ended answers get phrased by Claude instead of a
template, but which specialist ran is decided by this deterministic router
either way.
"""
import re

from recon import pipeline
from agents import action_ledger, exception_agent, forecast_agent, qa_agent

RECONCILE_PATTERN = re.compile(r"\b(reconcil\w*|match ledger|run the pipeline)\b", re.I)
FORECAST_PATTERN = re.compile(r"\b(forecast|cash position|projected cash)\b", re.I)
TRIAGE_PATTERN = re.compile(r"\b(triage|prioriti[sz]e|what should i look at|summary of exceptions)\b", re.I)
HORIZON_PATTERN = re.compile(r"(\d+)\s*day", re.I)


def handle(message):
    if RECONCILE_PATTERN.search(message):
        summary = pipeline.run()
        action_ledger.record("orchestrator", "ran_reconciliation", "full pipeline re-run on request")
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

    return qa_agent.answer(message)


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
