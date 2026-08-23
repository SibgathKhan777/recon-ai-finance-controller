"""Buckets matches/exceptions into a Cointab-style reconciliation report:
Total / Fully matched / Partially matched / Unmatched, each with a ledger
total, a settlement total, and the difference between them -- the same
shape a finance analyst sees in any reconciliation tool's summary cards.

"Fully matched" is deliberately narrow: only the `exact` category (same
reference, same amount, same day -- nothing was adjusted or guessed to
get there). Everything else that still matched (a fee deduction verified
against an explicit fee/tax identity, a timing shift, a corrected typo'd
reference, a netted refund/split settlement, an unreferenced same-amount
pair) required *some* variance to reconcile, so it's "partially matched"
-- consistent with how a real reconciliation tool draws that line, not an
arbitrary split invented for this report.
"""


def build_report(matches, exceptions):
    fully = [m for m in matches if m["category"] == "exact"]
    partial = [m for m in matches if m["category"] != "exact"]
    unmatched_ledger = [e for e in exceptions if e["side"] == "ledger"]
    unmatched_settlement = [e for e in exceptions if e["side"] == "settlement"]

    fully_bucket = _bucket_matched(fully)
    partial_bucket = _bucket_matched(partial)
    unmatched_bucket = _bucket_unmatched(unmatched_ledger, unmatched_settlement)

    total = {
        "ledger_amount": round(
            fully_bucket["ledger_amount"] + partial_bucket["ledger_amount"] + unmatched_bucket["ledger_amount"], 2
        ),
        "ledger_count": fully_bucket["ledger_count"] + partial_bucket["ledger_count"] + unmatched_bucket["ledger_count"],
        "settlement_amount": round(
            fully_bucket["settlement_amount"] + partial_bucket["settlement_amount"] + unmatched_bucket["settlement_amount"], 2
        ),
        "settlement_count": (
            fully_bucket["settlement_count"] + partial_bucket["settlement_count"] + unmatched_bucket["settlement_count"]
        ),
    }
    total["difference"] = round(total["settlement_amount"] - total["ledger_amount"], 2)

    return {
        "total": total,
        "fully_matched": {**fully_bucket, "rows": fully},
        "partially_matched": {**partial_bucket, "rows": partial},
        "unmatched": {**unmatched_bucket, "ledger_rows": unmatched_ledger, "settlement_rows": unmatched_settlement},
    }


def _bucket_matched(matched_subset):
    # net_settlement matches repeat the same ledger_id across 2+ settlement
    # legs (one row per leg) -- dedupe by ledger_id so the ledger side isn't
    # counted once per leg. The settlement side has no such repeat (each
    # leg is its own real settlement row), so it sums every row as-is.
    ledger_amount_by_id = {m["ledger_id"]: float(m["ledger_amount"]) for m in matched_subset}
    settlement_amount = sum(float(m["settlement_amount"]) for m in matched_subset)
    ledger_amount = sum(ledger_amount_by_id.values())
    return {
        "ledger_amount": round(ledger_amount, 2),
        "ledger_count": len(ledger_amount_by_id),
        "settlement_amount": round(settlement_amount, 2),
        "settlement_count": len(matched_subset),
        "difference": round(settlement_amount - ledger_amount, 2),
    }


def _bucket_unmatched(unmatched_ledger, unmatched_settlement):
    ledger_amount = sum(float(e["amount"]) for e in unmatched_ledger)
    settlement_amount = sum(float(e["amount"]) for e in unmatched_settlement)
    return {
        "ledger_amount": round(ledger_amount, 2),
        "ledger_count": len(unmatched_ledger),
        "settlement_amount": round(settlement_amount, 2),
        "settlement_count": len(unmatched_settlement),
        "difference": round(settlement_amount - ledger_amount, 2),
    }
