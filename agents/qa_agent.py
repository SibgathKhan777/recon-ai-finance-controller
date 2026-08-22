"""Settlement Q&A agent.

Answers finance-ops questions in plain English, grounded only in the
actual reconciliation output -- reports/matches.csv, reports/exceptions.csv,
reports/summary.json. Every number in an answer traces back to a real row.
If ANTHROPIC_API_KEY is set, open-ended questions that don't match a known
pattern get phrased by Claude instead of the fallback message -- but the
model is only ever shown the real data, and is instructed to say "the data
doesn't show that" rather than guess.
"""
import csv
import json
import os
import re
from pathlib import Path

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"

REF_PATTERN = re.compile(r"\b(RZP[0-9A-Z]+)\b", re.I)


def _read_csv(path):
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _load():
    matches = _read_csv(REPORTS_DIR / "matches.csv")
    exceptions = _read_csv(REPORTS_DIR / "exceptions.csv")
    summary_path = REPORTS_DIR / "summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    return matches, exceptions, summary


def answer(message):
    matches, exceptions, summary = _load()
    if not summary:
        return "No reconciliation report found yet -- ask me to 'run reconciliation' first."

    ref_match = REF_PATTERN.search(message)
    if ref_match:
        return _answer_about_ref(ref_match.group(1).upper(), matches, exceptions)

    lower = message.lower()
    if "fee" in lower:
        return _answer_fees(matches)
    if "duplicate" in lower:
        return _list_category(exceptions, "duplicate_settlement", "duplicate settlement")
    if "drift" in lower or "systematic" in lower:
        return _list_category(exceptions, "systematic_drift_suspected", "systematic drift")
    if "ambiguous" in lower or "no reference" in lower or "unreferenced" in lower:
        return _list_category(exceptions, "ambiguous_no_reference", "ambiguous no-reference")
    if "match rate" in lower or "accuracy" in lower:
        return (
            f"Match rate: {summary['match_rate'] * 100:.1f}% "
            f"({summary['matched_pairs']}/{summary['ledger_rows']} rows). "
            f"Accuracy vs ground truth: {(summary['overall_accuracy'] or 0) * 100:.1f}%."
        )
    if "exception" in lower or "unmatched" in lower:
        per_cat = summary.get("per_category", {})
        breakdown = ", ".join(f"{cat}: {v['total']}" for cat, v in per_cat.items())
        return f"{summary['exceptions']} exceptions out of {summary['ledger_rows']} ledger rows. Breakdown: {breakdown}"

    if os.environ.get("ANTHROPIC_API_KEY"):
        llm_answer = _answer_with_llm(message, exceptions, summary)
        if llm_answer:
            return llm_answer

    return (
        "I can answer questions about a specific reference (e.g. \"why didn't RZP123456789 "
        "settle\"), fees, duplicates, drift, match rate, or exceptions -- try one of those, "
        "or ask me to 'run reconciliation' first if no report exists yet."
    )


def _answer_about_ref(ref, matches, exceptions):
    for m in matches:
        if m["txn_ref"] == ref:
            utr_note = f", UTR {m['utr']}" if m.get("utr") else ""
            fee_note = ""
            if m["category"] == "fee_adjustment":
                fee_note = f" (fee Rs.{float(m['fee']):,.2f} + tax Rs.{float(m['tax']):,.2f})"
            return (
                f"{ref} matched as '{m['category']}' -- ledger Rs.{float(m['ledger_amount']):,.2f} "
                f"vs settlement Rs.{float(m['settlement_amount']):,.2f}{fee_note}{utr_note} "
                f"(confidence {m['confidence']})."
            )
    for e in exceptions:
        if e["txn_ref"] == ref:
            return e.get("explanation") or f"{ref} is an unresolved exception ({e['category']})."
    return f"No record of {ref} in the current reconciliation report."


def _answer_fees(matches):
    fee_rows = [m for m in matches if m["category"] == "fee_adjustment"]
    if not fee_rows:
        return "No fee-adjustment matches in the current report."
    total_fees = sum(float(m["fee"]) for m in fee_rows)
    total_tax = sum(float(m["tax"]) for m in fee_rows)
    return (
        f"Total gateway fees across {len(fee_rows)} settlements: Rs.{total_fees:,.2f} "
        f"(plus Rs.{total_tax:,.2f} tax on those fees)."
    )


def _list_category(exceptions, category, label):
    rows = [e for e in exceptions if e["category"] == category]
    if not rows:
        return f"No {label} exceptions in the current report."
    lines = [f"{len(rows)} {label} exception(s):"]
    for r in rows[:10]:
        row_id = r.get("ledger_id") or r.get("settlement_id") or "?"
        ref_display = r["txn_ref"] or "(no reference)"
        lines.append(f"  [{row_id}] {ref_display} -- Rs.{float(r['amount']):,.2f} on {r['date']}")
    return "\n".join(lines)


def _answer_with_llm(message, exceptions, summary):
    try:
        import anthropic
    except ImportError:
        return None
    try:
        client = anthropic.Anthropic()
        context = {"summary": summary, "sample_exceptions": exceptions[:20]}
        prompt = (
            "Answer the finance analyst's question using ONLY the JSON data below. "
            "If the data doesn't contain the answer, say so plainly -- do not guess.\n\n"
            f"DATA: {json.dumps(context)}\n\nQUESTION: {message}"
        )
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception:
        return None
