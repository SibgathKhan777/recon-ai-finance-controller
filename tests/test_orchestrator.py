from agents.orchestrator import handle


def test_routes_run_reconciliation():
    result = handle("please run reconciliation")
    assert "Reconciliation run" in result


def test_routes_reconciliation_natural_phrasing():
    result = handle("can you reconcile the ledger against settlements")
    assert "Reconciliation run" in result


def test_routes_cash_forecast():
    result = handle("give me a cash forecast for 5 days")
    assert "Projection" in result


def test_routes_triage():
    result = handle("what should i prioritize")
    assert "total exceptions" in result.lower() or "no exceptions" in result.lower()


def test_routes_qa_fallback():
    result = handle("what's our match rate")
    assert "Match rate" in result
