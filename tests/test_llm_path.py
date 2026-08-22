"""Tests for the LLM-backed code paths: recon.explainer._explain_with_llm
and agents.qa_agent._answer_with_llm.

anthropic.Anthropic is mocked throughout -- no real API key or network call
is ever made. These tests verify our own prompt construction, response
parsing, and fallback behavior, not Claude's actual output.
"""
from unittest.mock import MagicMock, patch

from agents import qa_agent
from recon import explainer


def _fake_response(text):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    return resp


def test_explainer_uses_llm_when_key_present():
    row = {"category": "missing_in_settlement", "txn_ref": "RZP123456789", "amount": 500.0, "date": "2026-01-01"}
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_anthropic.return_value.messages.create.return_value = _fake_response("LLM explanation text")
            result = explainer.explain(row)
    assert result == "LLM explanation text"
    mock_anthropic.return_value.messages.create.assert_called_once()


def test_explainer_falls_back_to_template_when_llm_errors():
    row = {"category": "missing_in_settlement", "txn_ref": "RZP123456789", "amount": 500.0, "date": "2026-01-01"}
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_anthropic.return_value.messages.create.side_effect = RuntimeError("network error")
            result = explainer.explain(row)
    assert "RZP123456789" in result
    assert "Rs.500.00" in result


def test_explainer_uses_template_when_no_key_even_if_anthropic_installed():
    row = {"category": "duplicate_settlement", "txn_ref": "RZP999999999", "amount": 10.0, "date": "2026-01-01"}
    with patch.dict("os.environ", {}, clear=False):
        import os
        os.environ.pop("ANTHROPIC_API_KEY", None)
        with patch("anthropic.Anthropic") as mock_anthropic:
            result = explainer.explain(row)
    mock_anthropic.assert_not_called()
    assert "RZP999999999" in result


def test_qa_agent_llm_path_used_for_open_ended_question():
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_anthropic.return_value.messages.create.return_value = _fake_response("Grounded LLM answer")
            result = qa_agent.answer("what's the weirdest thing in this batch")
    assert result == "Grounded LLM answer"


def test_qa_agent_falls_back_to_help_text_when_llm_errors():
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_anthropic.return_value.messages.create.side_effect = RuntimeError("boom")
            result = qa_agent.answer("what's the weirdest thing in this batch")
    assert "I can answer questions about" in result


def test_qa_agent_known_patterns_never_reach_llm_even_with_key():
    """Known-pattern questions (match rate, fees, etc.) are answered
    deterministically -- the LLM should never be invoked for them, key or
    not, since a grounded template answer already exists."""
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("anthropic.Anthropic") as mock_anthropic:
            qa_agent.answer("what's our match rate")
    mock_anthropic.assert_not_called()


def test_explainer_llm_import_error_falls_back_cleanly():
    row = {"category": "missing_in_ledger", "txn_ref": "RZP111111111", "amount": 42.0, "date": "2026-01-01"}
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        with patch.dict("sys.modules", {"anthropic": None}):
            result = explainer.explain(row)
    assert "RZP111111111" in result
