from agents import action_ledger
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


def test_running_reconciliation_logs_non_trivial_matches_to_the_audit_trail():
    before = len(action_ledger.read_all())
    handle("run reconciliation")
    after = action_ledger.read_all()
    assert len(after) > before
    reconciliation_entries = [e for e in after if e["agent"] == "reconciliation_agent"]
    assert reconciliation_entries, "expected at least one match logged (fee/timing/fuzzy matches are never confidence 1.0)"


def test_low_confidence_matches_get_flagged_when_logged(tmp_path, monkeypatch):
    # the default demo dataset's fuzzy matches happen to score high
    # confidence (a single-char typo out of 12 chars is a ~0.92 ratio,
    # well above the 0.8 gate) -- so exercise the wiring directly with a
    # constructed low-confidence row instead of relying on incidental data
    import csv

    from agents import orchestrator

    fake_matches = tmp_path / "matches.csv"
    with open(fake_matches, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "ledger_id", "settlement_id", "txn_ref", "ledger_amount",
            "settlement_amount", "category", "confidence",
        ])
        writer.writeheader()
        writer.writerow({
            "ledger_id": "L1", "settlement_id": "S1", "txn_ref": "",
            "ledger_amount": "500.0", "settlement_amount": "500.0",
            "category": "matched_no_reference", "confidence": "0.5",
        })
    monkeypatch.setattr(orchestrator, "MATCHES_PATH", fake_matches)

    before = len(action_ledger.read_all())
    orchestrator._log_consequential_matches()
    new_entries = action_ledger.read_all()[before:]

    assert len(new_entries) == 1
    assert new_entries[0]["confidence"] == 0.5
    assert new_entries[0]["needs_human_approval"] is True
