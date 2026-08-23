"""Reconciles internally-recorded tax (GST charged on gateway fees, per
transaction) against the vendor's periodic tax filing -- the same 2-way
check a real finance team runs before claiming Input Tax Credit. Modeled
on GSTR-2B (India's GST return): a frozen per-period snapshot, not a
continuously-updated feed like GSTR-2A, so this is deliberately a
period-level comparison, not a per-invoice one.

Honest about what a period-level comparison can and can't tell you: a
discrepancy is real and worth flagging, but two aggregate numbers alone
can't definitively distinguish a cross-period timing shift from a
genuinely missing credit -- that needs invoice-level detail a GSTR-2B-
style summary doesn't carry. Real GST reconciliation tools resolve this
ambiguity by matching at the invoice level for exactly this reason; this
flags the discrepancy honestly rather than guessing at a root cause it
can't actually verify from the data it has.
"""
from collections import defaultdict

MISMATCH_TOLERANCE = 1.0  # rupees -- below this is rounding noise, not a real gap


def reconcile(settlement_rows, tax_filing_rows):
    """Returns one dict per period: period, book_tax, filed_tax,
    difference, status ('reconciled' or 'mismatch'), invoice_count, note."""
    book_tax_by_period = defaultdict(float)
    invoice_count_by_period = defaultdict(int)
    for row in settlement_rows:
        tax = float(row.get("tax") or 0.0)
        if tax > 0:
            period = row["date"][:7]
            book_tax_by_period[period] += tax
            invoice_count_by_period[period] += 1

    filed_by_period = {row["period"]: float(row["filed_tax_amount"]) for row in tax_filing_rows}

    all_periods = sorted(set(book_tax_by_period) | set(filed_by_period))
    results = []
    for period in all_periods:
        book = round(book_tax_by_period.get(period, 0.0), 2)
        filed = round(filed_by_period.get(period, 0.0), 2)
        diff = round(filed - book, 2)
        entry = {
            "period": period,
            "book_tax": book,
            "filed_tax": filed,
            "difference": diff,
            "invoice_count": invoice_count_by_period.get(period, 0),
        }
        if abs(diff) < MISMATCH_TOLERANCE:
            entry["status"] = "reconciled"
            entry["note"] = ""
        else:
            entry["status"] = "mismatch"
            if diff < 0:
                entry["note"] = (
                    f"Vendor filed Rs.{abs(diff):,.2f} less GST than your books show for "
                    f"{period} -- that credit may be genuinely missing from their return, "
                    "or shifted to next period's filing (a common cross-period cutoff "
                    "issue). Either way, Input Tax Credit for this gap can't be safely "
                    "claimed until it shows up in a filing -- check invoice-level detail."
                )
            else:
                entry["note"] = (
                    f"Vendor filed Rs.{abs(diff):,.2f} more GST than your books show for "
                    f"{period} -- possibly a transaction shifted in from the prior "
                    "period's filing. Less urgent than an under-filed gap, but still "
                    "worth confirming it isn't a duplicate or miscategorized entry."
                )
        results.append(entry)
    return results
