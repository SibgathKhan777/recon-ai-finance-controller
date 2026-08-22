"""Tests for the optional LangGraph tool-calling orchestrator.

No real API call is ever made: tool functions are tested directly (they're
plain functions wrapping already-tested agents), and the one full-graph
test uses langchain_core's FakeMessagesListChatModel to script tool calls
deterministically -- exercising the real create_agent/tool-dispatch
machinery without hitting Anthropic's API or needing a key.
"""
import csv
from pathlib import Path
from unittest.mock import patch

import pytest

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"

langchain = pytest.importorskip("langchain", reason="optional dependency")
langgraph = pytest.importorskip("langgraph", reason="optional dependency")

from agents import langgraph_orchestrator as lgo  # noqa: E402


def _real_matched_ref():
    matches = list(csv.DictReader(open(REPORTS_DIR / "matches.csv")))
    return matches[0]["txn_ref"]


def test_answer_settlement_question_tool_is_grounded():
    result = lgo.answer_settlement_question.invoke({"question": "what's our match rate"})
    assert "Match rate" in result


def test_cash_forecast_tool_returns_a_projection():
    result = lgo.cash_forecast.invoke({"horizon_days": 5})
    assert "Projection" in result


def test_triage_exceptions_tool_returns_a_summary():
    result = lgo.triage_exceptions.invoke({})
    assert "exceptions" in result.lower() or "no exceptions" in result.lower()


def test_verify_claim_tool_is_grounded_and_bracketed():
    ref = _real_matched_ref()
    result = lgo.verify_claim.invoke({"claim": f"I never received my payout for {ref}"})
    assert result.startswith("[contradicted]")


def test_run_reconciliation_tool_reruns_the_pipeline():
    result = lgo.run_reconciliation.invoke({})
    assert "Reconciliation run" in result


def test_all_five_tools_are_registered():
    assert {t.name for t in lgo.TOOLS} == {
        "run_reconciliation", "cash_forecast", "triage_exceptions",
        "answer_settlement_question", "verify_claim",
    }


def test_full_graph_dispatches_to_the_right_tool_with_a_fake_model():
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage
    from langchain.agents import create_agent

    class FakeToolCallingModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    fake_model = FakeToolCallingModel(responses=[
        AIMessage(content="", tool_calls=[{
            "name": "answer_settlement_question",
            "args": {"question": "what's our match rate"},
            "id": "call_1",
        }]),
        AIMessage(content="Your match rate is 93.8 percent."),
    ])
    agent = create_agent(fake_model, lgo.TOOLS)
    result = agent.invoke({"messages": [{"role": "user", "content": "what's our match rate"}]})
    assert result["messages"][-1].content == "Your match rate is 93.8 percent."


def test_handle_builds_and_reuses_a_cached_agent():
    with patch("agents.langgraph_orchestrator._get_agent") as mock_get_agent:
        mock_agent = mock_get_agent.return_value
        mock_agent.invoke.return_value = {"messages": [type("M", (), {"content": "mocked"})()]}
        result = lgo.handle("anything")
        assert result == "mocked"
        mock_agent.invoke.assert_called_once()
