from agents import exception_agent


def test_triage_mentions_total_and_categories():
    output = exception_agent.triage()
    assert "total exceptions" in output.lower()
    assert "duplicate_settlement" in output or "missing_in_settlement" in output
