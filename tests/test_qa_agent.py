import csv
import json
from pathlib import Path

from agents import qa_agent

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def _write_isolated_report(reports_dir, matches):
    fieldnames = sorted({k for r in matches for k in r})
    with open(reports_dir / "matches.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(matches)
    (reports_dir / "exceptions.csv").write_text("")
    (reports_dir / "summary.json").write_text(json.dumps({
        "ledger_rows": len(matches), "matched_pairs": len(matches), "exceptions": 0,
        "match_rate": 1.0, "overall_accuracy": None, "per_category": {},
    }))


def test_match_rate_question():
    answer = qa_agent.answer("what's our match rate")
    assert "Match rate" in answer
    assert "%" in answer


def test_fees_question():
    answer = qa_agent.answer("how much did we pay in fees")
    assert "fee" in answer.lower()
    assert "Rs." in answer


def test_duplicate_question():
    answer = qa_agent.answer("show duplicate settlements")
    assert "duplicate" in answer.lower()


def test_unknown_ref_is_honest_not_hallucinated():
    answer = qa_agent.answer("why didn't RZP000000000 settle")
    assert "no record" in answer.lower()


def test_compute_formula_for_a_matched_reference(tmp_path):
    _write_isolated_report(tmp_path, [{
        "ledger_id": "L1", "settlement_id": "S1", "txn_ref": "RZP111111111",
        "ledger_amount": "1000.0", "settlement_amount": "990.0",
        "fee": "8.0", "tax": "2.0", "utr": "", "category": "fee_adjustment", "confidence": "1.0",
    }])
    answer = qa_agent.answer("compute ledger_amount - fee - tax for RZP111111111", reports_dir=tmp_path)
    assert "990.00" in answer


def test_compute_rejects_unknown_field(tmp_path):
    _write_isolated_report(tmp_path, [{
        "ledger_id": "L1", "settlement_id": "S1", "txn_ref": "RZP111111111",
        "ledger_amount": "1000.0", "settlement_amount": "990.0",
        "fee": "8.0", "tax": "2.0", "utr": "", "category": "exact", "confidence": "1.0",
    }])
    answer = qa_agent.answer("compute ledger_amount - bogus for RZP111111111", reports_dir=tmp_path)
    assert "couldn't compute" in answer.lower()


def test_compute_for_unmatched_reference_is_honest(tmp_path):
    _write_isolated_report(tmp_path, [])
    answer = qa_agent.answer("compute ledger_amount - fee for RZP999999999", reports_dir=tmp_path)
    assert "no matched record" in answer.lower()


def test_compute_pattern_does_not_swallow_a_plain_reference_question(tmp_path):
    # "compute" without "for <ref>" should fall through to the plain
    # ref-lookup path instead of erroring as a malformed formula.
    _write_isolated_report(tmp_path, [{
        "ledger_id": "L1", "settlement_id": "S1", "txn_ref": "RZP111111111",
        "ledger_amount": "1000.0", "settlement_amount": "1000.0",
        "fee": "0.0", "tax": "0.0", "utr": "", "category": "exact", "confidence": "1.0",
    }])
    answer = qa_agent.answer("why didn't RZP111111111 settle", reports_dir=tmp_path)
    assert "matched as 'exact'" in answer


def test_known_ref_is_grounded_in_real_data():
    matches = list(csv.DictReader(open(REPORTS_DIR / "matches.csv")))
    ref = matches[0]["txn_ref"]
    answer = qa_agent.answer(f"why didn't {ref} settle")
    assert ref in answer


def test_exceptions_breakdown_question():
    answer = qa_agent.answer("how many exceptions are there")
    assert "exceptions" in answer.lower()
