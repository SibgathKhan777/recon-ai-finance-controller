"""Tax Reconciliation agent.

Checks GST recorded internally (settlement.tax, the gateway-fee tax the
merchant would claim as Input Tax Credit) against the vendor's periodic
tax filing. See recon/tax_matcher.py for the honest scope: a period-level
check, matching how a real GST return (GSTR-2B) actually works -- a
frozen monthly snapshot, not per-invoice detail -- so a flagged mismatch
is reported honestly as "investigate this," not over-diagnosed as a
specific root cause the data can't actually prove.
"""
import json
from pathlib import Path

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def _load(reports_dir=None):
    report_path = (reports_dir or REPORTS_DIR) / "tax_reconciliation.json"
    if not report_path.exists():
        return None
    return json.loads(report_path.read_text())


def triage(reports_dir=None):
    report = _load(reports_dir)
    if report is None:
        return "No tax reconciliation report found yet -- ask me to 'run reconciliation' first."
    if not report.get("available"):
        return "No tax filing data available for the current dataset -- tax reconciliation runs on the synthetic demo, not on uploaded data."

    lines = []
    for p in report["periods"]:
        status_word = "reconciled" if p["status"] == "reconciled" else "MISMATCH"
        lines.append(
            f"{p['period']}: book Rs.{p['book_tax']:,.2f} vs filed Rs.{p['filed_tax']:,.2f} "
            f"({status_word}, {p['invoice_count']} invoice(s))"
        )
        if p["note"]:
            lines.append(f"  {p['note']}")

    if not lines:
        return "No tax-bearing transactions in the current report."
    return "\n".join(lines)
