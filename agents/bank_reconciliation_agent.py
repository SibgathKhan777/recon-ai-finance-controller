"""Bank Reconciliation agent -- the third leg of reconciliation.

Reads reports/bank_reconciliation.json (written by recon/pipeline.py
alongside the main ledger-vs-settlement run) and turns it into a
plain-English summary: how much reconciled cleanly against the actual
bank statement, what's still pending, and what showed up in the account
with no explanation. UTR-based, and batch-aware -- see recon/bank_matcher.py
for why a naive one-settlement-per-bank-credit check isn't enough.
"""
import json
from pathlib import Path

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def _load(reports_dir=None):
    report_path = (reports_dir or REPORTS_DIR) / "bank_reconciliation.json"
    if not report_path.exists():
        return None
    return json.loads(report_path.read_text())


def triage(reports_dir=None):
    report = _load(reports_dir)
    if report is None:
        return "No bank reconciliation report found yet -- ask me to 'run reconciliation' first."
    if not report.get("available"):
        return "No bank statement data available for the current dataset -- bank reconciliation runs on the synthetic demo, not on uploaded data."

    lines = [
        f"{report['reconciled_count']} UTR(s) reconciled cleanly against the bank statement, "
        f"{report['exception_count']} exception(s)."
    ]

    batches = [r for r in report["reconciled"] if r["batch_size"] > 1]
    if batches:
        lines.append(
            f"{len(batches)} of those were batch settlements -- multiple gateway payouts "
            "landing in one bank transfer, correctly summed rather than treated as separate mismatches."
        )

    by_category = {}
    for e in report["exceptions"]:
        by_category.setdefault(e["category"], []).append(e)
    for category, rows in sorted(by_category.items()):
        lines.append(f"  {category}: {len(rows)} row(s)")
        for r in rows[:5]:
            lines.append(f"    UTR {r['utr']}: {r['explanation']}")

    return "\n".join(lines)


def lookup(utr, reports_dir=None):
    report = _load(reports_dir)
    if report is None or not report.get("available"):
        return "No bank reconciliation data available to look that up against."

    for r in report["reconciled"]:
        if r["utr"] == utr:
            batch_note = f" (a batch of {r['batch_size']} settlement rows)" if r["batch_size"] > 1 else ""
            return f"UTR {utr} reconciled cleanly{batch_note}: Rs.{r['bank_amount']:,.2f} landed in the bank, matching the settlement side exactly."
    for e in report["exceptions"]:
        if e["utr"] == utr:
            return e["explanation"]
    return f"No record of UTR {utr} in the current bank reconciliation report."
