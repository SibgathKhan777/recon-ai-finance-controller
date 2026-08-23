"""Synthetic ledger + settlement data generator with known ground truth.

Produces two CSVs designed to look like a real reconciliation problem:
messy dates, small fee deductions, typo'd references, duplicate payouts,
and rows that only exist on one side. Every row's true label is recorded
in ground_truth.csv so the matcher's output can be scored honestly.
"""
import argparse
import csv
import random
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "generated"

MERCHANTS = ["Kirana Mart", "Bluewave Retail", "Solstice Foods", "Nimbus Apparel", "Terra Electronics"]

REF_ALPHABET = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"

# Matches Razorpay's real settlement.entity fields (id, amount, fees, tax,
# utr) rather than an invented generic schema -- see settlement_id/fee/tax/
# utr on SettlementRow below. https://razorpay.com/docs/api/settlements/entity/
BANK_CODES = ["AXIS", "HDFC", "ICIC", "SBIN", "KKBK"]
BANK_NAMES = ["HDFC Bank", "ICICI Bank", "Axis Bank", "State Bank of India", "Kotak Mahindra Bank"]


def _generate_utr(rng: random.Random) -> str:
    return f"{rng.choice(BANK_CODES)}CN{rng.randrange(10**9, 10**10)}"


@dataclass
class LedgerRow:
    ledger_id: str
    txn_ref: str
    date: str
    amount: float
    merchant: str
    description: str


@dataclass
class SettlementRow:
    settlement_id: str
    txn_ref: str
    date: str
    amount: float
    merchant: str
    description: str
    fee: float = 0.0
    tax: float = 0.0
    utr: str = ""


@dataclass
class GroundTruthRow:
    ledger_id: str
    settlement_id: str
    true_category: str


@dataclass
class BankStatementRow:
    bank_txn_id: str
    utr: str
    date: str
    amount: float
    bank_name: str


@dataclass
class TaxFilingRow:
    period: str
    vendor_gstin: str
    filed_tax_amount: float
    invoice_count: int


VENDOR_GSTIN = "27AAFCR5055K1Z8"  # placeholder, not a real registered GSTIN


def _corrupt_ref(ref: str, rng: random.Random) -> str:
    chars = list(ref)
    idx = rng.randrange(len(chars))
    original = chars[idx]
    # Must actually differ, or this "corruption" is a silent no-op and the
    # resulting ref is byte-identical to the original — indistinguishable
    # from a real exact match, which breaks the ground-truth label.
    replacement = rng.choice(REF_ALPHABET)
    while replacement == original:
        replacement = rng.choice(REF_ALPHABET)
    chars[idx] = replacement
    return "".join(chars)


def generate(seed: int = 42, n_base: int = 150, corrupt: str = "none", out_dir: Path = None):
    rng = random.Random(seed)
    today = date.today()

    ledger_rows, settlement_rows, ground_truth = [], [], []
    exact_settlement_rows = []

    def txn_date(offset_days):
        return (today - timedelta(days=offset_days)).isoformat()

    def new_amount():
        return round(rng.uniform(199, 48999), 2)

    counts = {
        "exact": int(n_base * 0.667),
        "fee_adjustment": int(n_base * 0.10),
        "timing": int(n_base * 0.08),
        "corrupted_ref": int(n_base * 0.053),
        "missing_in_settlement": int(n_base * 0.053),
        "missing_in_ledger": int(n_base * 0.027),
    }

    idx = 0
    for category, n in counts.items():
        for _ in range(n):
            idx += 1
            ledger_id = f"L{idx:05d}"
            settlement_id = f"S{idx:05d}"
            txn_ref = f"RZP{rng.randrange(10**8, 10**9)}"
            merchant = rng.choice(MERCHANTS)
            base_amount = new_amount()
            base_day_offset = rng.randrange(1, 30)

            if category == "exact":
                ledger_rows.append(LedgerRow(ledger_id, txn_ref, txn_date(base_day_offset), base_amount, merchant, "order settlement"))
                srow = SettlementRow(settlement_id, txn_ref, txn_date(base_day_offset), base_amount, merchant, "payout", utr=_generate_utr(rng))
                settlement_rows.append(srow)
                exact_settlement_rows.append(srow)
                ground_truth.append(GroundTruthRow(ledger_id, settlement_id, "exact"))

            elif category == "fee_adjustment":
                # fee and tax are explicit, separate fields -- matching Razorpay's
                # real settlement schema -- rather than baked silently into the
                # net amount. That's what lets the matcher verify this exactly
                # (ledger == settlement + fee + tax) instead of guessing via a
                # percentage tolerance.
                fee = round(base_amount * rng.uniform(0.003, 0.018), 2)
                tax = round(fee * 0.18, 2)  # GST on the gateway fee
                net_amount = round(base_amount - fee - tax, 2)
                ledger_rows.append(LedgerRow(ledger_id, txn_ref, txn_date(base_day_offset), base_amount, merchant, "order settlement"))
                settlement_rows.append(SettlementRow(
                    settlement_id, txn_ref, txn_date(base_day_offset), net_amount, merchant,
                    "payout net of gateway fee", fee=fee, tax=tax, utr=_generate_utr(rng),
                ))
                ground_truth.append(GroundTruthRow(ledger_id, settlement_id, "fee_adjustment"))

            elif category == "timing":
                lag = rng.randrange(1, 4)
                ledger_rows.append(LedgerRow(ledger_id, txn_ref, txn_date(base_day_offset), base_amount, merchant, "order settlement"))
                settlement_rows.append(SettlementRow(settlement_id, txn_ref, txn_date(base_day_offset - lag), base_amount, merchant, "payout", utr=_generate_utr(rng)))
                ground_truth.append(GroundTruthRow(ledger_id, settlement_id, "timing"))

            elif category == "corrupted_ref":
                bad_ref = _corrupt_ref(txn_ref, rng)
                ledger_rows.append(LedgerRow(ledger_id, txn_ref, txn_date(base_day_offset), base_amount, merchant, "order settlement"))
                settlement_rows.append(SettlementRow(settlement_id, bad_ref, txn_date(base_day_offset), base_amount, merchant, "payout", utr=_generate_utr(rng)))
                ground_truth.append(GroundTruthRow(ledger_id, settlement_id, "corrupted_ref"))

            elif category == "missing_in_settlement":
                ledger_rows.append(LedgerRow(ledger_id, txn_ref, txn_date(base_day_offset), base_amount, merchant, "order settlement, payment pending"))
                ground_truth.append(GroundTruthRow(ledger_id, "", "missing_in_settlement"))

            elif category == "missing_in_ledger":
                settlement_rows.append(SettlementRow(settlement_id, txn_ref, txn_date(base_day_offset), base_amount, merchant, "payout, unbooked", utr=_generate_utr(rng)))
                ground_truth.append(GroundTruthRow("", settlement_id, "missing_in_ledger"))

    # duplicate settlements: clone a few already-exact-matched settlement rows
    for dup in rng.sample(exact_settlement_rows, k=min(3, len(exact_settlement_rows))):
        idx += 1
        dup_id = f"S{idx:05d}"
        settlement_rows.append(SettlementRow(
            dup_id, dup.txn_ref, dup.date, dup.amount, dup.merchant,
            "payout (duplicate batch retry)", utr=_generate_utr(rng),
        ))
        ground_truth.append(GroundTruthRow("", dup_id, "duplicate_settlement"))

    # unreferenced transactions: a real data-quality scenario -- some payment
    # channels (cash-equivalent UPI, manual bank transfers) never capture a
    # structured reference number at all. Two unambiguous pairs demonstrate
    # that the matcher still matches them, just at lower confidence -- this
    # is what makes the audit trail's confidence gate demonstrable, not just
    # unit-tested against a hand-built fixture.
    for _ in range(2):
        idx += 1
        ledger_id = f"L{idx:05d}"
        settlement_id = f"S{idx:05d}"
        merchant = rng.choice(MERCHANTS)
        amount = new_amount()
        day_offset = rng.randrange(1, 30)
        ledger_rows.append(LedgerRow(ledger_id, "", txn_date(day_offset), amount, merchant, "cash-equivalent payment, no reference captured"))
        settlement_rows.append(SettlementRow(settlement_id, "", txn_date(day_offset), amount, merchant, "payout, no reference", utr=_generate_utr(rng)))
        ground_truth.append(GroundTruthRow(ledger_id, settlement_id, "matched_no_reference"))

    # ...and one ambiguous cluster: two ledger rows and two settlement rows,
    # all blank-ref, sharing the same amount and date. Amount+date alone
    # can't tell them apart, so none should be auto-matched -- they should
    # come out as ambiguous_no_reference, flagged for manual review.
    amb_amount = new_amount()
    amb_date = txn_date(rng.randrange(1, 30))
    amb_merchant = rng.choice(MERCHANTS)
    amb_ledger_ids, amb_settlement_ids = [], []
    for _ in range(2):
        idx += 1
        ledger_id = f"L{idx:05d}"
        ledger_rows.append(LedgerRow(ledger_id, "", amb_date, amb_amount, amb_merchant, "cash-equivalent payment, no reference captured"))
        amb_ledger_ids.append(ledger_id)
    for _ in range(2):
        idx += 1
        settlement_id = f"S{idx:05d}"
        settlement_rows.append(SettlementRow(settlement_id, "", amb_date, amb_amount, amb_merchant, "payout, no reference", utr=_generate_utr(rng)))
        amb_settlement_ids.append(settlement_id)
    for lid in amb_ledger_ids:
        ground_truth.append(GroundTruthRow(lid, "", "ambiguous_no_reference"))
    for sid in amb_settlement_ids:
        ground_truth.append(GroundTruthRow("", sid, "ambiguous_no_reference"))

    # Split settlement: one invoice paid out via two partial settlement legs
    # (e.g. a marketplace advancing part of a payout early). Neither leg
    # alone matches the ledger amount -- only their sum does -- so this is
    # what matcher.py's net_settlement pass (recon/matcher.py) exists for,
    # not something passes 1-2 could ever catch.
    idx += 1
    split_ledger_id = f"L{idx:05d}"
    split_ref = f"RZP{rng.randrange(10**8, 10**9)}"
    split_merchant = rng.choice(MERCHANTS)
    split_day = rng.randrange(1, 30)
    split_total = new_amount()
    split_first = round(split_total * rng.uniform(0.3, 0.7), 2)
    split_second = round(split_total - split_first, 2)
    ledger_rows.append(LedgerRow(split_ledger_id, split_ref, txn_date(split_day), split_total, split_merchant, "order settlement"))
    split_settlement_ids = []
    for amount in (split_first, split_second):
        idx += 1
        settlement_id = f"S{idx:05d}"
        settlement_rows.append(SettlementRow(settlement_id, split_ref, txn_date(split_day), amount, split_merchant, "partial payout (split settlement)", utr=_generate_utr(rng)))
        split_settlement_ids.append(settlement_id)
    for sid in split_settlement_ids:
        ground_truth.append(GroundTruthRow(split_ledger_id, sid, "net_settlement"))

    # Refund netting: a payout followed by a partial refund/reversal for the
    # same reference -- the ledger only ever records the net amount actually
    # kept, so the two settlement legs (original + negative refund) have to
    # be summed against it, not matched individually.
    idx += 1
    refund_ledger_id = f"L{idx:05d}"
    refund_ref = f"RZP{rng.randrange(10**8, 10**9)}"
    refund_merchant = rng.choice(MERCHANTS)
    refund_day = rng.randrange(1, 30)
    original_amount = new_amount()
    refund_amount = round(original_amount * rng.uniform(0.1, 0.4), 2)
    net_amount = round(original_amount - refund_amount, 2)
    ledger_rows.append(LedgerRow(refund_ledger_id, refund_ref, txn_date(refund_day), net_amount, refund_merchant, "order settlement, net of partial refund"))
    refund_settlement_ids = []
    idx += 1
    original_settlement_id = f"S{idx:05d}"
    settlement_rows.append(SettlementRow(original_settlement_id, refund_ref, txn_date(refund_day), original_amount, refund_merchant, "payout", utr=_generate_utr(rng)))
    refund_settlement_ids.append(original_settlement_id)
    idx += 1
    refund_settlement_id = f"S{idx:05d}"
    settlement_rows.append(SettlementRow(refund_settlement_id, refund_ref, txn_date(refund_day), -refund_amount, refund_merchant, "refund (reversal)", utr=_generate_utr(rng)))
    refund_settlement_ids.append(refund_settlement_id)
    for sid in refund_settlement_ids:
        ground_truth.append(GroundTruthRow(refund_ledger_id, sid, "net_settlement"))

    if corrupt == "currency":
        drift = 1.035  # 3.5% drift — deliberately just past the matcher's 2% tolerance band
        affected = rng.sample(settlement_rows, k=max(1, len(settlement_rows) // 7))
        for row in affected:
            row.amount = round(row.amount * drift, 2)

    # Bank statement: the third leg of reconciliation. UTR is the highest-
    # reliability match key in real bank reconciliation (assigned by the
    # banking rail itself, not typeable by either side) -- but a real bank
    # reconciliation that only checks "does this bank credit match ONE
    # settlement row" is incomplete: a payment aggregator routinely batches
    # several payouts into a single bank transfer. Modeled here by pointing
    # a few distinct settlement rows at one shared UTR -- naive 1:1 matching
    # would fail on these; matching has to sum the group.
    bank_rows = []
    bank_txn_idx = 0

    def _rows_by_utr():
        grouped = defaultdict(list)
        for srow in settlement_rows:
            if srow.utr:
                grouped[srow.utr].append(srow)
        return grouped

    utr_rows = _rows_by_utr()
    batchable_utrs = [u for u, rows in utr_rows.items() if len(rows) == 1]
    rng.shuffle(batchable_utrs)
    if len(batchable_utrs) >= 3:
        shared_utr = _generate_utr(rng)
        for u in batchable_utrs[:3]:
            for srow in utr_rows[u]:
                srow.utr = shared_utr
        utr_rows = _rows_by_utr()

    all_utrs = list(utr_rows.keys())
    rng.shuffle(all_utrs)
    pending_utrs = set(all_utrs[:2])  # settled per gateway, bank hasn't credited yet -- a real, open exception

    for utr, rows_for_utr in utr_rows.items():
        if utr in pending_utrs:
            continue
        bank_txn_idx += 1
        credit_lag = rng.randrange(0, 3)
        latest_date = max(r.date for r in rows_for_utr)
        bank_date = (date.fromisoformat(latest_date) + timedelta(days=credit_lag)).isoformat()
        bank_rows.append(BankStatementRow(
            f"BANK{bank_txn_idx:05d}", utr, bank_date,
            round(sum(r.amount for r in rows_for_utr), 2), rng.choice(BANK_NAMES),
        ))

    # one unrecognized bank credit: a UTR with no corresponding settlement
    # row at all -- a stray or unrelated bank-side entry that shows up in
    # the account but isn't part of this batch
    bank_txn_idx += 1
    bank_rows.append(BankStatementRow(
        f"BANK{bank_txn_idx:05d}", _generate_utr(rng), txn_date(rng.randrange(1, 30)),
        round(rng.uniform(199, 4999), 2), rng.choice(BANK_NAMES),
    ))

    # Tax filing: models the vendor's periodic GST return (a frozen,
    # GSTR-2B-style monthly snapshot, not continuously updated like
    # GSTR-2A) that a merchant's books get reconciled against before
    # claiming Input Tax Credit on the GST charged as part of gateway
    # fees. Two real, documented GST-reconciliation failure modes:
    # (1) a transaction's tax reported in the *next* period's return --
    # a cross-period cutoff mismatch that understates this period's ITC
    # and overstates next period's; (2) a transaction the vendor simply
    # never reported at all -- a genuinely missing credit, not a timing
    # issue. Most periods otherwise reconcile exactly.
    fee_rows_by_period = defaultdict(list)
    for srow in settlement_rows:
        if srow.tax > 0:
            fee_rows_by_period[srow.date[:7]].append(srow)

    periods = sorted(fee_rows_by_period.keys())
    filed_tax_by_period = {p: round(sum(r.tax for r in fee_rows_by_period[p]), 2) for p in periods}

    if len(periods) >= 2 and fee_rows_by_period[periods[0]]:
        earlier, later = periods[0], periods[1]
        shifted_row = fee_rows_by_period[earlier][0]
        filed_tax_by_period[earlier] = round(filed_tax_by_period[earlier] - shifted_row.tax, 2)
        filed_tax_by_period[later] = round(filed_tax_by_period[later] + shifted_row.tax, 2)

    if periods and fee_rows_by_period[periods[-1]]:
        missing_period = periods[-1]
        candidates = fee_rows_by_period[missing_period]
        missing_row = candidates[-1]
        filed_tax_by_period[missing_period] = round(filed_tax_by_period[missing_period] - missing_row.tax, 2)

    tax_filing_rows = [
        TaxFilingRow(p, VENDOR_GSTIN, filed_tax_by_period[p], len(fee_rows_by_period[p]))
        for p in periods
    ]

    rng.shuffle(ledger_rows)
    rng.shuffle(settlement_rows)
    rng.shuffle(bank_rows)

    out_dir = out_dir or OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(out_dir / "ledger.csv", ledger_rows)
    _write_csv(out_dir / "settlement.csv", settlement_rows)
    _write_csv(out_dir / "ground_truth.csv", ground_truth)
    _write_csv(out_dir / "bank_statement.csv", bank_rows)
    _write_csv(out_dir / "tax_filing.csv", tax_filing_rows)

    return len(ledger_rows), len(settlement_rows)


def _write_csv(path: Path, rows):
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate synthetic ledger/settlement reconciliation data.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-base", type=int, default=150)
    parser.add_argument("--corrupt", choices=["none", "currency"], default="none")
    args = parser.parse_args()
    n_l, n_s = generate(seed=args.seed, n_base=args.n_base, corrupt=args.corrupt)
    print(f"Generated {n_l} ledger rows and {n_s} settlement rows in {OUT_DIR}")
