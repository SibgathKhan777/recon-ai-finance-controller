"""Pairwise feature extraction for the trained match classifier.

Same task shape used by real-world record-linkage tools (Splink, dedupe.io):
given a candidate (ledger_row, settlement_row) pair, extract features
describing their *relationship*, then classify the pair as a match or not.
This is deliberately the same signal the deterministic matcher already
uses (amount closeness, date closeness, reference similarity) -- the
question this whole ml/ subsystem exists to honestly answer is whether a
learned model can recover the same decision boundary the hand-written
rules encode, not to invent new signal the rules don't already have
access to.
"""
import difflib
from datetime import datetime

FEATURE_NAMES = [
    "amount_diff",
    "amount_diff_pct",
    "date_diff_days",
    "ref_exact_match",
    "ref_similarity",
    "has_ledger_ref",
    "has_settlement_ref",
    "gross_reconciles",
    "ledger_amount",
    "settlement_amount",
]


def _date_diff_days(d1, d2):
    try:
        return abs((datetime.fromisoformat(d1) - datetime.fromisoformat(d2)).days)
    except (ValueError, TypeError):
        return 999  # unparseable date -- treat as maximally far apart, not a crash


def extract(ledger_row, settlement_row):
    """Returns a dict of FEATURE_NAMES -> float, describing the
    relationship between one ledger row and one settlement row candidate."""
    ledger_amount = float(ledger_row.get("amount", 0.0) or 0.0)
    settlement_amount = float(settlement_row.get("amount", 0.0) or 0.0)
    fee = float(settlement_row.get("fee") or 0.0)
    tax = float(settlement_row.get("tax") or 0.0)

    ledger_ref = str(ledger_row.get("txn_ref", "") or "").strip()
    settlement_ref = str(settlement_row.get("txn_ref", "") or "").strip()

    amount_diff = abs(ledger_amount - settlement_amount)
    expected_gross = settlement_amount + fee + tax

    return {
        "amount_diff": amount_diff,
        "amount_diff_pct": amount_diff / ledger_amount if ledger_amount else 1.0,
        "date_diff_days": _date_diff_days(ledger_row.get("date", ""), settlement_row.get("date", "")),
        "ref_exact_match": 1.0 if ledger_ref and ledger_ref == settlement_ref else 0.0,
        "ref_similarity": (
            difflib.SequenceMatcher(None, ledger_ref, settlement_ref).ratio()
            if ledger_ref and settlement_ref else 0.0
        ),
        "has_ledger_ref": 1.0 if ledger_ref else 0.0,
        "has_settlement_ref": 1.0 if settlement_ref else 0.0,
        "gross_reconciles": 1.0 if abs(ledger_amount - expected_gross) < 0.01 else 0.0,
        "ledger_amount": ledger_amount,
        "settlement_amount": settlement_amount,
    }


def to_vector(features):
    """Dict -> ordered list, for feeding a fitted sklearn model."""
    return [features[name] for name in FEATURE_NAMES]
