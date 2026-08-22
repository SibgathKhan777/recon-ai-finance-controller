"""Turns a raw exception row into a plain-English explanation.

Uses Claude if ANTHROPIC_API_KEY is set; otherwise falls back to templated
explanations so the pipeline always runs end to end with zero setup.
"""
import os

TEMPLATES = {
    "missing_in_settlement": (
        "Ledger shows {ref} for Rs.{amount:,.2f} on {date} with no matching settlement "
        "within the {window}-day window - likely still pending payout, or the payment "
        "failed after authorization and was never actually settled."
    ),
    "missing_in_ledger": (
        "Settlement includes a payout {ref} for Rs.{amount:,.2f} on {date} (UTR {utr}) with "
        "no ledger entry - check your bank statement for that UTR to confirm receipt, or "
        "look for a booking that was missed, or a refund/adjustment credited directly by "
        "the gateway without a corresponding ledger write."
    ),
    "duplicate_settlement": (
        "{ref} appears more than once in unmatched settlement rows (UTR {utr}) - likely a "
        "duplicate payout or a retried settlement batch. Only one instance should reconcile "
        "against the ledger; the rest need a payout-side correction, not a ledger entry."
    ),
    "systematic_drift_suspected": (
        "{ref} and other unmatched transactions share amount mismatches clustered around "
        "a {drift_pct:+.2f}% ratio - this looks like a systematic issue (currency "
        "conversion, fee-schedule change) rather than unrelated one-off exceptions. "
        "Investigate the batch, not each row."
    ),
}

DEFAULT_TEMPLATE = "{ref} for Rs.{amount:,.2f} on {date} could not be reconciled automatically ({category})."


def explain(exception_row, window=3):
    if os.environ.get("ANTHROPIC_API_KEY"):
        text = _explain_with_llm(exception_row)
        if text:
            return text
    return _explain_with_template(exception_row, window)


def _explain_with_template(row, window):
    template = TEMPLATES.get(row["category"], DEFAULT_TEMPLATE)
    try:
        return template.format(
            ref=row.get("txn_ref", "?"),
            amount=row.get("amount", 0.0),
            date=row.get("date", "?"),
            window=window,
            drift_pct=(row.get("drift_ratio", 1.0) - 1) * 100,
            category=row.get("category", "unknown"),
            utr=row.get("utr") or "unknown",
        )
    except Exception:
        return DEFAULT_TEMPLATE.format(
            ref=row.get("txn_ref", "?"),
            amount=row.get("amount", 0.0),
            date=row.get("date", "?"),
            category=row.get("category", "unknown"),
        )


def _explain_with_llm(row):
    try:
        import anthropic
    except ImportError:
        return None
    try:
        client = anthropic.Anthropic()
        prompt = (
            "You are a finance-ops assistant. In one plain-English sentence, "
            "explain this unmatched reconciliation row to a finance analyst and "
            "suggest the likely cause. Be specific and concrete, not generic.\n\n"
            f"Row: {row}"
        )
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception:
        return None
