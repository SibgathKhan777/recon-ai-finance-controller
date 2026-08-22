"""Claim Verification agent.

An end-user (customer or merchant) makes a claim about what happened to a
payment -- "I never received my payout for RZP123456789", "my payment
settled fine, why is support saying it didn't". This agent checks the
claim against the actual reconciliation record and returns a verdict:
does the claim match the data, contradict it, or is there no record to
check it against at all.

It never accuses anyone of lying -- a contradiction is flagged for human
review via the shared action ledger, not auto-resolved. Same principle as
match-confidence gating elsewhere in this system: a claim that doesn't
match the data doesn't get silently dismissed OR silently believed, it
gets a human in the loop before anything consequential happens.
"""
import csv
import re
from pathlib import Path

from agents import action_ledger

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
REF_PATTERN = re.compile(r"\b(RZP[0-9A-Z]+)\b", re.I)

# Deliberately simple keyword matching, not real NLU -- this is meant to
# route claims to the right factual check, not to be the source of truth.
# The actual verdict always comes from the reconciliation record, never
# from how confidently-worded the claim is.
NEGATIVE_PHRASES = [
    "didn't", "did not", "never received", "never got", "not received",
    "not paid", "not settled", "missing", "failed", "hasn't arrived",
    "has not arrived", "no money", "haven't received", "have not received",
    "still waiting", "where is my", "where's my",
]
POSITIVE_PHRASES = [
    "did receive", "went through", "was paid", "settled fine", "got paid",
    "received it", "came through", "was successful", "all good",
]


def _read_csv(path):
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _claim_sentiment(claim):
    lower = claim.lower()
    if any(phrase in lower for phrase in NEGATIVE_PHRASES):
        return "negative"
    if any(phrase in lower for phrase in POSITIVE_PHRASES):
        return "positive"
    return "unclear"


def verify(claim):
    """Returns {"verdict", "message", "ref"}. verdict is one of:
    "confirmed" (claim matches the record), "contradicted" (claim
    conflicts with the record -- needs human review), "no_record"
    (a valid-looking ref with nothing on file), or "no_reference"
    (couldn't find a ref to check at all)."""
    ref_match = REF_PATTERN.search(claim)
    if not ref_match:
        return {
            "verdict": "no_reference",
            "ref": None,
            "message": (
                "I couldn't find a transaction reference in that claim -- include "
                "the reference ID (e.g. RZP123456789) so it can be checked against "
                "the actual reconciliation record."
            ),
        }

    ref = ref_match.group(1).upper()
    sentiment = _claim_sentiment(claim)
    matches = _read_csv(REPORTS_DIR / "matches.csv")
    exceptions = _read_csv(REPORTS_DIR / "exceptions.csv")

    record = next((m for m in matches if m["txn_ref"] == ref), None)
    if record:
        result = _verdict_against_match(ref, claim, sentiment, record)
        _log(result, ref)
        return result

    exc = next((e for e in exceptions if e["txn_ref"] == ref), None)
    if exc:
        result = _verdict_against_exception(ref, claim, sentiment, exc)
        _log(result, ref)
        return result

    result = {
        "verdict": "no_record",
        "ref": ref,
        "message": (
            f"No record of {ref} in the current reconciliation report -- this can't "
            "be verified either way. Needs manual investigation, not an automatic answer."
        ),
    }
    _log(result, ref)
    return result


def _verdict_against_match(ref, claim, sentiment, record):
    detail = (
        f"matched as '{record['category']}', ledger Rs.{float(record['ledger_amount']):,.2f} "
        f"vs settlement Rs.{float(record['settlement_amount']):,.2f} (confidence {record['confidence']})"
    )
    if sentiment == "negative":
        return {
            "verdict": "contradicted",
            "ref": ref,
            "message": (
                f"Our records show {ref} DID settle -- {detail}. This claim doesn't "
                "match our data. Flagged for human review, not dismissed."
            ),
        }
    return {
        "verdict": "confirmed",
        "ref": ref,
        "message": f"Confirmed: {ref} {detail}. Consistent with the claim.",
    }


def _verdict_against_exception(ref, claim, sentiment, exc):
    detail = f"an open '{exc['category']}' exception for Rs.{float(exc['amount']):,.2f}"
    explanation = exc.get("explanation") or ""
    if sentiment == "negative":
        return {
            "verdict": "confirmed",
            "ref": ref,
            "message": f"Confirmed: {ref} genuinely hasn't reconciled -- it's {detail}. {explanation}".strip(),
        }
    return {
        "verdict": "contradicted",
        "ref": ref,
        "message": (
            f"Our records show {ref} is actually {detail}, not a successful "
            "settlement. This claim doesn't match our data. Flagged for human review."
        ),
    }


def _log(result, ref):
    # a contradiction always needs a human -- confidence 0.0 forces that
    # gate regardless of amount; a confirmed claim is routine, logged at
    # full confidence so it doesn't clutter anyone's review queue
    confidence = 0.0 if result["verdict"] == "contradicted" else 1.0
    action_ledger.record(
        "claim_verifier", "verified_claim",
        f"{result['verdict']} for {ref}",
        confidence=confidence,
    )
