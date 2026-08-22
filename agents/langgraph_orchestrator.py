"""Optional LangGraph tool-calling orchestrator.

This is an alternate router to agents/orchestrator.py's deterministic
keyword-based one -- not a replacement. It wraps the same five specialist
agents as LangGraph/LangChain tools and lets an LLM (Claude, via
langchain-anthropic) decide which one to call from free-form natural
language, instead of matching against a fixed set of regexes.

Trade-off, stated plainly: this path is genuinely smarter at open-ended
phrasing (no explicit "verify claim:" trigger needed, no keyword list to
maintain) but it is non-deterministic and costs an API call per message.
That's exactly why it's opt-in -- see agents.orchestrator.smart_handle,
which only reaches this module when ANTHROPIC_API_KEY is set, and falls
back to the deterministic router otherwise. The core reconciliation
matching logic is untouched either way; this only changes how a message
gets routed to it.

Requires the optional `langgraph` and `langchain-anthropic` packages.
Callers should catch ImportError -- see smart_handle.
"""
from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool

from agents import claim_verifier, exception_agent, forecast_agent, qa_agent
from agents.orchestrator import _format_forecast, _format_summary, _log_consequential_matches
from recon import pipeline

MODEL_NAME = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = (
    "You are the AI Finance Controller, an orchestrator over five specialist "
    "tools for a payments reconciliation system. Route each user message to "
    "exactly the tool(s) that can actually answer it -- never answer from your "
    "own knowledge, since every real number must come from a tool. If no tool "
    "fits, say so plainly rather than guessing."
)


@tool
def run_reconciliation() -> str:
    """Re-run the full ledger-vs-settlement reconciliation pipeline and
    return a summary (match rate, exception count, accuracy vs ground
    truth). Use this when the user asks to run, re-run, or refresh the
    reconciliation."""
    summary = pipeline.run()
    _log_consequential_matches()
    return _format_summary(summary)


@tool
def cash_forecast(horizon_days: int = 7) -> str:
    """Project the cash position for the next N days from real settlement
    data, including money still at risk in unresolved exceptions. Use this
    for any cash-flow, forecast, or "how much will we have" question."""
    result = forecast_agent.forecast(horizon_days=horizon_days)
    return _format_forecast(result)


@tool
def triage_exceptions() -> str:
    """Summarize and prioritize the current exception list -- which rows
    are one-off issues versus one systemic problem affecting many rows.
    Use this when the user asks what to look at first, or for a summary
    of exceptions."""
    return exception_agent.triage()


@tool
def answer_settlement_question(question: str) -> str:
    """Answer a specific factual question about the reconciliation report
    -- match rate, a specific transaction reference, fee totals,
    duplicates, or drift status. Use this for any question about what
    already happened in the data, grounded only in the real report."""
    return qa_agent.answer(question)


@tool
def verify_claim(claim: str) -> str:
    """Check a customer or merchant's claim about a payment (e.g. "I never
    received my payout for RZP123456789") against the actual
    reconciliation record. Use this whenever a message sounds like an
    external claim about what happened to a specific payment, not an
    internal analyst question. Never conclude someone is lying yourself --
    this tool's own verdict already handles that responsibly."""
    result = claim_verifier.verify(claim)
    return f"[{result['verdict']}] {result['message']}"


TOOLS = [run_reconciliation, cash_forecast, triage_exceptions, answer_settlement_question, verify_claim]

_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        model = ChatAnthropic(model=MODEL_NAME)
        _agent = create_agent(model, TOOLS, system_prompt=SYSTEM_PROMPT)
    return _agent


def handle(message):
    agent = _get_agent()
    result = agent.invoke({"messages": [{"role": "user", "content": message}]})
    return result["messages"][-1].content
