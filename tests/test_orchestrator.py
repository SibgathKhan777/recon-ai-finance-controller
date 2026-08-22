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


def test_default_demo_dataset_produces_a_genuine_confidence_driven_flag():
    # regression guard for a real gap: the confidence-gating mechanism was
    # originally built and unit-tested, but the default demo dataset never
    # actually exercised it -- every match happened to score >= 0.8
    # confidence, so every audit-trail flag was amount-driven, not
    # confidence-driven. Fixed by adding an unreferenced-transaction
    # scenario (matched_no_reference, confidence 0.5) to the generator.
    # This test would fail again if that scenario were ever removed.
    handle("run reconciliation")
    entries = [e for e in action_ledger.read_all() if e["agent"] == "reconciliation_agent"]
    confidence_driven = [
        e for e in entries
        if e["confidence"] is not None and e["confidence"] < 0.8
        and e["needs_human_approval"]
    ]
    assert confidence_driven, "expected the demo dataset's unreferenced-transaction scenario to produce at least one confidence-driven approval flag"


def test_low_confidence_matches_get_flagged_when_logged(tmp_path, monkeypatch):
    # unit-level check of the wiring itself, independent of dataset content
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
