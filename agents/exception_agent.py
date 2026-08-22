"""Exception & Anomaly agent.

Turns the Reconciliation Agent's raw exception list into a triaged,
prioritized narrative: which rows are one-off items a human can just
clear, and which are a single systemic issue masquerading as many rows.
This is a distinct specialist from Q&A -- Q&A answers a specific question
you ask; this one proactively tells you what to look at first.
"""
import csv
from pathlib import Path

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def _read_csv(path):
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def triage():
    exceptions = _read_csv(REPORTS_DIR / "exceptions.csv")
    if not exceptions:
        return "No exceptions in the current report -- ask me to 'run reconciliation' first."

    by_category = {}
    for e in exceptions:
        by_category.setdefault(e["category"], []).append(e)

    lines = [f"{len(exceptions)} total exceptions across {len(by_category)} categories:"]
    for cat, rows in sorted(by_category.items(), key=lambda kv: -len(kv[1])):
        total = sum(float(r["amount"]) for r in rows)
        lines.append(f"  {cat}: {len(rows)} rows, Rs.{total:,.2f}")

    if "systematic_drift_suspected" in by_category:
        n = len(by_category["systematic_drift_suspected"])
        lines.append(
            f"\nPriority: {n} of those rows are one systemic drift, not {n} separate "
            "problems -- investigate the shared root cause (see drift_ratio in "
            "exceptions.csv), don't clear them one by one."
        )

    return "\n".join(lines)
