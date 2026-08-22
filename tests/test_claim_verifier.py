import csv
from pathlib import Path

from agents import action_ledger, claim_verifier

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def _real_matched_ref():
    matches = list(csv.DictReader(open(REPORTS_DIR / "matches.csv")))
    return matches[0]["txn_ref"]


def _real_exception_ref():
    exceptions = list(csv.DictReader(open(REPORTS_DIR / "exceptions.csv")))
    for e in exceptions:
        if e["txn_ref"]:
            return e["txn_ref"]
    raise AssertionError("no referenced exception found in the default demo dataset")


def test_claim_without_a_reference_asks_for_one():
    result = claim_verifier.verify("I never got my money")
    assert result["verdict"] == "no_reference"


def test_unknown_reference_returns_no_record():
    result = claim_verifier.verify("why didn't RZP999999998 settle")
    assert result["verdict"] == "no_record"
    assert result["ref"] == "RZP999999998"


def test_negative_claim_confirmed_when_record_is_a_real_exception():
    ref = _real_exception_ref()
    result = claim_verifier.verify(f"I never received my payout for {ref}")
    assert result["verdict"] == "confirmed"
    assert ref in result["message"]


def test_positive_claim_contradicted_when_record_is_a_real_exception():
    ref = _real_exception_ref()
    result = claim_verifier.verify(f"my payment for {ref} went through fine")
    assert result["verdict"] == "contradicted"


def test_negative_claim_contradicted_when_record_shows_a_clean_match():
    ref = _real_matched_ref()
    result = claim_verifier.verify(f"I never received my payout for {ref}")
    assert result["verdict"] == "contradicted"
    assert "flagged for human review" in result["message"].lower()


def test_positive_claim_confirmed_when_record_shows_a_clean_match():
    ref = _real_matched_ref()
    result = claim_verifier.verify(f"my payment {ref} went through fine")
    assert result["verdict"] == "confirmed"


def test_every_verified_claim_is_logged_to_the_action_ledger():
    ref = _real_matched_ref()
    before = len(action_ledger.read_all())
    claim_verifier.verify(f"my payment {ref} went through fine")
    after = action_ledger.read_all()
    assert len(after) == before + 1
    assert after[-1]["agent"] == "claim_verifier"


def test_contradicted_verdict_always_needs_human_approval():
    ref = _real_matched_ref()
    claim_verifier.verify(f"I never received my payout for {ref}")
    entries = action_ledger.read_all()
    assert entries[-1]["needs_human_approval"] is True


def test_confirmed_verdict_does_not_need_human_approval():
    ref = _real_matched_ref()
    claim_verifier.verify(f"my payment {ref} went through fine")
    entries = action_ledger.read_all()
    assert entries[-1]["needs_human_approval"] is False


def test_claim_with_no_reference_is_not_logged():
    before = len(action_ledger.read_all())
    claim_verifier.verify("I never got my money")
    after = action_ledger.read_all()
    assert len(after) == before
