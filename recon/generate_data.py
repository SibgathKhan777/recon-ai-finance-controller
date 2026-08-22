"""Synthetic ledger + settlement data generator with known ground truth.

Produces two CSVs designed to look like a real reconciliation problem:
messy dates, small fee deductions, typo'd references, duplicate payouts,
and rows that only exist on one side. Every row's true label is recorded
in ground_truth.csv so the matcher's output can be scored honestly.
"""
import argparse
import csv
import random
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


def generate(seed: int = 42, n_base: int = 150, corrupt: str = "none"):
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

    if corrupt == "currency":
        drift = 1.035  # 3.5% drift — deliberately just past the matcher's 2% tolerance band
        affected = rng.sample(settlement_rows, k=max(1, len(settlement_rows) // 7))
        for row in affected:
            row.amount = round(row.amount * drift, 2)

    rng.shuffle(ledger_rows)
    rng.shuffle(settlement_rows)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _write_csv(OUT_DIR / "ledger.csv", ledger_rows)
    _write_csv(OUT_DIR / "settlement.csv", settlement_rows)
    _write_csv(OUT_DIR / "ground_truth.csv", ground_truth)

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
