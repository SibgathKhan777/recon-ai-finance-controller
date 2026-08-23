from agents import action_ledger
from agents.orchestrator import handle, smart_handle


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


def test_routes_verify_claim_with_explicit_trigger_phrase():
    import csv
    from pathlib import Path

    ref = list(csv.DictReader(open(Path(__file__).resolve().parent.parent / "reports" / "matches.csv")))[0]["txn_ref"]
    result = handle(f"verify claim: I never received my payout for {ref}")
    assert result.startswith("[contradicted]")


def test_plain_claim_text_without_trigger_phrase_falls_through_to_qa():
    # confirms the persona separation is real -- a bare claim sentence
    # without the trigger phrase is NOT silently routed to claim_verifier
    result = handle("I never received my payout for RZP999999998")
    assert not result.startswith("[")


def test_smart_handle_falls_back_to_deterministic_router_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = smart_handle("what's our match rate")
    assert "Match rate" in result


def test_smart_handle_falls_back_when_langgraph_orchestrator_is_unimportable(monkeypatch):
    # even with a key present, a missing optional dependency must not break
    # the app -- this is the whole point of the opt-in design
    import builtins

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "agents.langgraph_orchestrator":
            raise ImportError("simulated missing optional dependency")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    result = smart_handle("what's our match rate")
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


def test_routes_bank_reconciliation_status():
    result = handle("bank reconciliation status")
    assert "reconciled cleanly against the bank statement" in result


def test_routes_tax_reconciliation():
    result = handle("show me the tax reconciliation")
    assert "book" in result.lower() and "filed" in result.lower()


def test_bank_and_tax_phrasing_is_not_swallowed_by_the_generic_reconcile_pattern():
    # regression guard: "reconciliation" contains "reconcil" as a
    # substring, so RECONCILE_PATTERN (reconcil\w*) would otherwise
    # intercept these before they ever reach the bank/tax-specific checks.
    bank_result = handle("bank reconciliation status")
    assert "Reconciliation run:" not in bank_result

    tax_result = handle("show me the tax reconciliation")
    assert "Reconciliation run:" not in tax_result


def test_routes_bank_utr_lookup():
    import csv
    from pathlib import Path

    matches_path = Path(__file__).resolve().parent.parent / "reports" / "matches.csv"
    utr = next(row["utr"] for row in csv.DictReader(open(matches_path)) if row.get("utr"))
    result = handle(f"look up UTR {utr}")
    assert utr in result


def test_pending_approvals_and_approve_reject_round_trip(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    entry = action_ledger.record(
        "reconciliation_agent", "matched", "a flagged match", amount=200, confidence=0.5,
        ledger_path=ledger_path,
    )

    pending = handle("what needs approval", ledger_path=ledger_path)
    assert f"#{entry['id']}" in pending

    approved = handle(f"approve #{entry['id']}: looks correct", ledger_path=ledger_path)
    assert "approved" in approved.lower()

    pending_after = handle("pending approvals", ledger_path=ledger_path)
    assert "Nothing pending approval" in pending_after


def test_reject_with_reason_resolves_the_pending_flag(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    entry = action_ledger.record(
        "reconciliation_agent", "matched", "a flagged match", amount=6000,
        ledger_path=ledger_path,
    )
    result = handle(f"reject #{entry['id']}: amount looks wrong", ledger_path=ledger_path)
    assert "rejected" in result.lower()
    assert action_ledger.pending_approvals(ledger_path=ledger_path) == []


def test_approve_note_mentioning_bank_is_not_swallowed_by_bank_pattern(tmp_path):
    # regression guard for a real bug: an approval note is free text a
    # reviewer writes, and "approve #3: verified against bank statement"
    # was getting intercepted by BANK_PATTERN (checked before APPROVE_
    # PATTERN) purely because the note happens to contain the word "bank"
    # -- the same keyword-collision bug class as the reconcile/reconciliation
    # bug above, just with approve/reject this time. Caught by actually
    # sending a realistic reviewer note through handle(), not by assuming
    # the anchored APPROVE_PATTERN would obviously win.
    ledger_path = tmp_path / "ledger.jsonl"
    entry = action_ledger.record(
        "reconciliation_agent", "matched", "a flagged match", amount=200, confidence=0.5,
        ledger_path=ledger_path,
    )
    result = handle(f"approve #{entry['id']}: verified against bank statement", ledger_path=ledger_path)
    assert result.startswith(f"Entry #{entry['id']} approved")


def test_compute_formula_routes_through_qa_agent():
    import csv
    from pathlib import Path

    matches_path = Path(__file__).resolve().parent.parent / "reports" / "matches.csv"
    row = next(r for r in csv.DictReader(open(matches_path)) if r["category"] == "fee_adjustment")
    result = handle(f"compute ledger_amount - fee - tax for {row['txn_ref']}")
    assert "=" in result and "Rs." in result
