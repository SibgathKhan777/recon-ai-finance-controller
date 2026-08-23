"""Third leg of reconciliation: settlement (what the gateway says it paid)
vs the actual bank statement (what landed in the account).

UTR is the match key -- the highest-reliability reference available in
real bank reconciliation, since it's assigned by the banking rail itself
(NEFT/RTGS/IMPS/UPI), not typed by either side the way an internal
transaction reference can be. But matching "does this bank credit match
ONE settlement row" is an incomplete check on its own: a payment
aggregator routinely batches several payouts into a single bank transfer.
This groups settlement rows by UTR and compares the *summed* amount
against the bank credit, so a genuine batch reconciles correctly instead
of looking like N unrelated mismatches.
"""
from collections import defaultdict


def reconcile(settlement_rows, bank_rows):
    """Returns (reconciled, exceptions). reconciled: one row per UTR that
    tied out exactly, quantities compared as
    sum(settlement amounts sharing that UTR) == bank credit amount.
    exceptions: bank_credit_pending (settled per gateway, no bank credit
    yet), unrecognized_bank_credit (a bank-side UTR with no settlement
    counterpart at all), or bank_amount_mismatch (the UTR matches but the
    summed settlement amount and the bank credit disagree -- a real,
    investigable discrepancy, not assumed away)."""
    settlement_by_utr = defaultdict(list)
    for row in settlement_rows:
        utr = (row.get("utr") or "").strip()
        if utr:
            settlement_by_utr[utr].append(row)

    bank_by_utr = {}
    for row in bank_rows:
        utr = (row.get("utr") or "").strip()
        if utr:
            bank_by_utr[utr] = row

    reconciled = []
    exceptions = []

    for utr, s_rows in settlement_by_utr.items():
        settlement_total = round(sum(float(r["amount"]) for r in s_rows), 2)
        bank_row = bank_by_utr.get(utr)
        if bank_row is None:
            exceptions.append({
                "utr": utr,
                "category": "bank_credit_pending",
                "settlement_amount": settlement_total,
                "bank_amount": None,
                "settlement_ids": ",".join(r["settlement_id"] for r in s_rows),
                "bank_txn_id": "",
                "explanation": (
                    f"UTR {utr} covers {len(s_rows)} settlement row(s) totaling "
                    f"Rs.{settlement_total:,.2f}, but no matching bank credit has "
                    "arrived yet -- likely still in transit."
                ),
            })
            continue

        bank_amount = float(bank_row["amount"])
        if abs(settlement_total - bank_amount) < 0.01:
            reconciled.append({
                "utr": utr,
                "settlement_amount": settlement_total,
                "bank_amount": bank_amount,
                "settlement_ids": ",".join(r["settlement_id"] for r in s_rows),
                "bank_txn_id": bank_row["bank_txn_id"],
                "batch_size": len(s_rows),
            })
        else:
            exceptions.append({
                "utr": utr,
                "category": "bank_amount_mismatch",
                "settlement_amount": settlement_total,
                "bank_amount": bank_amount,
                "settlement_ids": ",".join(r["settlement_id"] for r in s_rows),
                "bank_txn_id": bank_row["bank_txn_id"],
                "explanation": (
                    f"UTR {utr}: settlement side totals Rs.{settlement_total:,.2f} "
                    f"across {len(s_rows)} row(s), but the bank credit is "
                    f"Rs.{bank_amount:,.2f} -- a Rs.{abs(settlement_total - bank_amount):,.2f} "
                    "gap that doesn't self-explain, worth investigating directly."
                ),
            })

    for utr, bank_row in bank_by_utr.items():
        if utr not in settlement_by_utr:
            exceptions.append({
                "utr": utr,
                "category": "unrecognized_bank_credit",
                "settlement_amount": None,
                "bank_amount": float(bank_row["amount"]),
                "settlement_ids": "",
                "bank_txn_id": bank_row["bank_txn_id"],
                "explanation": (
                    f"Bank credit {bank_row['bank_txn_id']} (UTR {utr}) for "
                    f"Rs.{float(bank_row['amount']):,.2f} has no corresponding "
                    "settlement record -- either an unrelated bank transaction, "
                    "or a settlement from outside this batch."
                ),
            })

    return reconciled, exceptions
