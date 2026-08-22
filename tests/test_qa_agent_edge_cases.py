"""Edge-case tests for the Q&A agent's reference extraction and precedence
rules -- these document actual behavior at ambiguous boundaries (multiple
refs, mixed case, keyword collisions) rather than assuming an untested
default is correct.
"""
import csv
from pathlib import Path

from agents import qa_agent

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def _real_ref():
    matches = list(csv.DictReader(open(REPORTS_DIR / "matches.csv")))
    return matches[0]["txn_ref"]


def test_ref_extraction_ignores_trailing_punctuation():
    ref = _real_ref()
    answer = qa_agent.answer(f"why didn't {ref}? settle")
    assert ref in answer


def test_ref_extraction_is_case_insensitive_but_normalizes_to_upper():
    ref = _real_ref()
    answer = qa_agent.answer(f"why didn't {ref.lower()} settle")
    assert ref in answer


def test_two_refs_in_one_message_uses_only_the_first():
    ref = _real_ref()
    fake_second_ref = "RZP000000001"
    answer = qa_agent.answer(f"compare {ref} against {fake_second_ref}")
    assert ref in answer
    assert fake_second_ref not in answer


def test_ref_lookup_takes_precedence_over_keyword_match():
    # message contains both a real ref AND the word "fee" -- ref-specific
    # lookup should win over the generic fee-total answer
    ref = _real_ref()
    answer = qa_agent.answer(f"was there a fee on {ref}")
    assert ref in answer


def test_empty_message_does_not_crash():
    answer = qa_agent.answer("")
    assert isinstance(answer, str) and answer


def test_whitespace_only_message_does_not_crash():
    answer = qa_agent.answer("   ")
    assert isinstance(answer, str) and answer


def test_syntactically_valid_but_unknown_ref_reports_no_record():
    answer = qa_agent.answer("why didn't RZP999999998 settle")
    assert "no record" in answer.lower()


def test_ref_pattern_does_not_match_bare_rzp_with_no_digits():
    # "RZP" alone with nothing after it shouldn't be treated as a reference
    answer = qa_agent.answer("what does RZP stand for")
    assert "no record" not in answer.lower()
