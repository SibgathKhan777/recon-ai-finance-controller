"""Orchestrator: routes a natural-language message to the right specialist.

Rule-based intent matching by default -- always works, no API key needed,
and the routing decision is always inspectable rather than a black box
(you can see exactly which regex matched and why). If ANTHROPIC_API_KEY is
set, the Q&A agent's open-ended answers get phrased by Claude instead of a
template, but which specialist ran is decided by this deterministic router
either way.
"""
import csv
import os
import re
from pathlib import Path

from recon import pipeline
from agents import (
    action_ledger, bank_reconciliation_agent, claim_verifier, exception_agent,
    forecast_agent, qa_agent, tax_agent,
)

RECONCILE_PATTERN = re.compile(r"\b(reconcil\w*|match ledger|run the pipeline)\b", re.I)
FORECAST_PATTERN = re.compile(r"\b(forecast|cash position|projected cash)\b", re.I)
TRIAGE_PATTERN = re.compile(r"\b(triage|prioriti[sz]e|what should i look at|summary of exceptions)\b", re.I)
BANK_PATTERN = re.compile(r"\b(bank\w*|utr)\b", re.I)
TAX_PATTERN = re.compile(r"\b(tax filing|tax reconcil\w*|\bgst\b|\bitc\b|input tax credit)\b", re.I)
# Requires an explicit trigger phrase rather than folding into general Q&A --
# a customer/merchant claim is a different persona than an internal analyst
# question, and blending them risks a claim being misread as routine Q&A.
VERIFY_CLAIM_PATTERN = re.compile(r"^\s*verify claim[:\-]?\s*(.+)", re.I)
HORIZON_PATTERN = re.compile(r"(\d+)\s*day", re.I)
UTR_PATTERN = re.compile(r"\b([A-Z]{4}CN\d{9,10})\b", re.I)
PENDING_APPROVALS_PATTERN = re.compile(r"\b(pending approvals?|needs? approval|what needs approval)\b", re.I)
APPROVE_PATTERN = re.compile(r"^\s*approve\s+#?(\d+)\s*[:\-]?\s*(.*)$", re.I)
REJECT_PATTERN = re.compile(r"^\s*reject\s+#?(\d+)\s*[:\-]?\s*(.*)$", re.I)

MATCHES_PATH = Path(__file__).resolve().parent.parent / "reports" / "matches.csv"


def handle(message, data_dir=None, reports_dir=None, ledger_path=None):
    """data_dir/reports_dir/ledger_path default to the shared module-level
    paths used by the CLI, Streamlit app, and tests. A caller serving
    multiple clients (see backend/main.py) passes a session-specific set so
    one client's chat can never read or log against another client's data."""
    matches_path = reports_dir / "matches.csv" if reports_dir else MATCHES_PATH

    # Approve/reject checked FIRST, before anything keyword-based: an
    # approval note is free text a reviewer writes ("approve #3: confirmed
    # against bank statement"), and that note can legitimately contain any
    # other intent's keyword ("bank", "tax", "reconcile"...). Found the
    # same way as bugs #2 and #8 in this project's history -- by actually
    # sending a realistic note through handle(), not by inspecting the
    # regexes and assuming they don't overlap. APPROVE_PATTERN/
    # REJECT_PATTERN are anchored on "approve #<digits>"/"reject #<digits>"
    # at the very start of the message, so they can't misfire on a message
    # that merely mentions "approve" or "reject" in passing.
    approve_match = APPROVE_PATTERN.match(message)
    if approve_match:
        entry_id, note = int(approve_match.group(1)), approve_match.group(2).strip()
        entry = action_ledger.approve(entry_id, reviewer="chat_operator", note=note, ledger_path=ledger_path)
        return f"Entry #{entry_id} approved by chat_operator. ({entry['timestamp']})"

    reject_match = REJECT_PATTERN.match(message)
    if reject_match:
        entry_id, note = int(reject_match.group(1)), reject_match.group(2).strip()
        entry = action_ledger.reject(entry_id, reviewer="chat_operator", note=note, ledger_path=ledger_path)
        return f"Entry #{entry_id} rejected by chat_operator. ({entry['timestamp']})"

    if PENDING_APPROVALS_PATTERN.search(message):
        return _format_pending_approvals(action_ledger.pending_approvals(ledger_path=ledger_path))

    # Bank/tax checked next: RECONCILE_PATTERN matches "reconcil\w*", and
    # "reconciliation" is exactly that -- so "bank reconciliation" or "tax
    # reconciliation" would otherwise get swallowed by the generic
    # run-the-whole-pipeline intent before ever reaching these more
    # specific ones. Found by actually testing these phrases, not assumed
    # to route correctly because the patterns looked non-overlapping.
    if BANK_PATTERN.search(message):
        utr_match = UTR_PATTERN.search(message)
        if utr_match:
            return bank_reconciliation_agent.lookup(utr_match.group(1).upper(), reports_dir=reports_dir)
        return bank_reconciliation_agent.triage(reports_dir=reports_dir)

    if TAX_PATTERN.search(message):
        return tax_agent.triage(reports_dir=reports_dir)

    if RECONCILE_PATTERN.search(message):
        summary = pipeline.run(data_dir=data_dir, reports_dir=reports_dir)
        action_ledger.record(
            "orchestrator", "ran_reconciliation", "full pipeline re-run on request",
            ledger_path=ledger_path,
        )
        _log_consequential_matches(matches_path, ledger_path)
        return _format_summary(summary)

    if FORECAST_PATTERN.search(message):
        horizon_match = HORIZON_PATTERN.search(message)
        horizon = int(horizon_match.group(1)) if horizon_match else 7
        result = forecast_agent.forecast(horizon_days=horizon, data_dir=data_dir, reports_dir=reports_dir)
        if "error" not in result:
            action_ledger.record(
                "cash_forecaster", "forecast", f"{horizon}-day projection",
                amount=result.get("at_risk_amount_pending_settlement"),
                ledger_path=ledger_path,
            )
        return _format_forecast(result)

    if TRIAGE_PATTERN.search(message):
        return exception_agent.triage(reports_dir=reports_dir)

    verify_match = VERIFY_CLAIM_PATTERN.match(message)
    if verify_match:
        result = claim_verifier.verify(verify_match.group(1), reports_dir=reports_dir, ledger_path=ledger_path)
        return f"[{result['verdict']}] {result['message']}"

    return qa_agent.answer(message, reports_dir=reports_dir)


def smart_handle(message):
    """Same contract as handle(): takes a message, returns a response
    string. Uses the LangGraph tool-calling agent (agents.langgraph_
    orchestrator) when ANTHROPIC_API_KEY is set and the optional langgraph
    + langchain-anthropic packages are installed -- an LLM decides which
    specialist tool to call, so it handles open-ended phrasing (including
    a bare claim with no "verify claim:" trigger phrase) that the
    deterministic router's fixed regexes can't. Falls back to handle()
    whenever that path isn't available, so this never requires an API key
    to work -- it only ever upgrades the experience, never gates it."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from agents.langgraph_orchestrator import handle as langgraph_handle
            return langgraph_handle(message)
        except ImportError:
            pass
    return handle(message)


def _log_consequential_matches(matches_path=None, ledger_path=None):
    """Every match the Reconciliation Agent made is a money decision --
    log the ones actually worth a second look (not perfect, or large) to
    the shared audit trail, letting action_ledger's own confidence/amount
    gates decide whether each one needs human sign-off."""
    matches_path = matches_path or MATCHES_PATH
    if not matches_path.exists():
        return
    with open(matches_path, newline="") as f:
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
                    ledger_path=ledger_path,
                )


def _format_summary(summary):
    return (
        f"Reconciliation run: {summary['matched_pairs']}/{summary['ledger_rows']} matched "
        f"({summary['match_rate'] * 100:.1f}%), {summary['exceptions']} exceptions, "
        f"{(summary['overall_accuracy'] or 0) * 100:.1f}% accuracy vs ground truth."
    )


def _format_pending_approvals(entries):
    if not entries:
        return "Nothing pending approval right now."
    lines = [f"{len(entries)} entr{'y' if len(entries) == 1 else 'ies'} pending approval:"]
    for e in entries:
        amount_note = f", Rs.{e['amount']:,.2f}" if e.get("amount") is not None else ""
        confidence_note = f", confidence {e['confidence']}" if e.get("confidence") is not None else ""
        lines.append(f"  #{e['id']} [{e['agent']}] {e['detail']}{amount_note}{confidence_note}")
    lines.append("Reply 'approve #<id>' or 'reject #<id>: <reason>' to resolve one.")
    return "\n".join(lines)


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
