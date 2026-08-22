import csv
from pathlib import Path

from agents import qa_agent

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


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


def test_known_ref_is_grounded_in_real_data():
    matches = list(csv.DictReader(open(REPORTS_DIR / "matches.csv")))
    ref = matches[0]["txn_ref"]
    answer = qa_agent.answer(f"why didn't {ref} settle")
    assert ref in answer


def test_exceptions_breakdown_question():
    answer = qa_agent.answer("how many exceptions are there")
    assert "exceptions" in answer.lower()
