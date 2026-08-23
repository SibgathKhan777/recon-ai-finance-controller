import json
from pathlib import Path

from recon.generate_data import generate
from recon.pipeline import run, run_uploaded

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def teardown_module(module):
    generate(seed=42)
    run()


def test_demo_run_produces_available_bank_and_tax_reports():
    generate(seed=42)
    run()
    bank_report = json.loads((REPORTS_DIR / "bank_reconciliation.json").read_text())
    tax_report = json.loads((REPORTS_DIR / "tax_reconciliation.json").read_text())
    assert bank_report["available"] is True
    assert bank_report["reconciled_count"] > 0
    assert tax_report["available"] is True
    assert len(tax_report["periods"]) > 0


def test_uploaded_data_reports_bank_and_tax_as_unavailable_not_stale():
    # regression guard: uploaded data has no bank statement or tax filing,
    # so these must honestly report unavailable rather than silently
    # matching against whatever synthetic demo data was generated last
    generate(seed=42)
    run()  # leaves real bank/tax reports on disk

    ledger = [{"ledger_id": "L1", "txn_ref": "ABC1", "date": "2026-01-01", "amount": 100.0}]
    settlement = [{"settlement_id": "S1", "txn_ref": "ABC1", "date": "2026-01-01", "amount": 100.0}]
    run_uploaded(ledger, settlement)

    bank_report = json.loads((REPORTS_DIR / "bank_reconciliation.json").read_text())
    tax_report = json.loads((REPORTS_DIR / "tax_reconciliation.json").read_text())
    assert bank_report == {"available": False}
    assert tax_report == {"available": False}


def test_bank_reconciliation_batch_scenario_is_present_in_demo_data():
    generate(seed=42)
    run()
    bank_report = json.loads((REPORTS_DIR / "bank_reconciliation.json").read_text())
    batches = [r for r in bank_report["reconciled"] if r["batch_size"] > 1]
    assert len(batches) >= 1, "expected the generator's injected multi-settlement batch scenario"


def test_bank_reconciliation_pending_and_unrecognized_exceptions_present():
    generate(seed=42)
    run()
    bank_report = json.loads((REPORTS_DIR / "bank_reconciliation.json").read_text())
    categories = {e["category"] for e in bank_report["exceptions"]}
    assert "bank_credit_pending" in categories
    assert "unrecognized_bank_credit" in categories


def test_tax_reconciliation_flags_the_injected_cross_period_scenario():
    generate(seed=42)
    run()
    tax_report = json.loads((REPORTS_DIR / "tax_reconciliation.json").read_text())
    mismatches = [p for p in tax_report["periods"] if p["status"] == "mismatch"]
    assert len(mismatches) >= 1, "expected the generator's injected cross-period tax mismatch"
