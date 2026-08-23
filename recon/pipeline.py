"""End-to-end pipeline: load -> match -> explain -> score -> save reports."""
import csv
import json
from pathlib import Path

from recon import bank_matcher, explainer, matcher, scorer, tax_matcher

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "generated"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def _read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def run(data_dir=None, reports_dir=None):
    """The demo path: synthetic data with known ground truth, so accuracy
    is a real, checkable number."""
    data_dir = data_dir or DATA_DIR
    ledger = _read_csv(data_dir / "ledger.csv")
    settlement = _read_csv(data_dir / "settlement.csv")
    ground_truth = _read_csv(data_dir / "ground_truth.csv")
    summary = run_from_records(ledger, settlement, ground_truth, reports_dir=reports_dir)
    run_bank_and_tax_reconciliation(settlement, data_dir=data_dir, reports_dir=reports_dir)
    return summary


def run_uploaded(ledger, settlement, data_dir=None, reports_dir=None, amount_tolerance_pct=None):
    """The real-data path: a user's own ledger/settlement records, with no
    ground truth to score against. overall_accuracy and per-category
    accuracy come back None -- that's honest, not a bug, since there's no
    known-correct label to check against for someone's real data.

    Also persists ledger/settlement to data_dir (clearing any old
    ground_truth.csv) -- agents/forecast_agent.py reads settlement.csv from
    there directly, not from reports_dir, so without this it would silently
    keep showing whatever synthetic data was last generated instead of the
    just-uploaded numbers. Same reasoning for bank_statement.csv/
    tax_filing.csv: real uploads don't include those, so any stale
    synthetic-demo versions are cleared rather than left to silently match
    against data that has nothing to do with what was just uploaded.

    data_dir/reports_dir default to the shared module-level paths, but a
    caller serving multiple clients (see backend/main.py) passes a
    session-specific pair of directories so one client's upload can never
    leak into another's reports."""
    data_dir = data_dir or DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(data_dir / "ledger.csv", ledger)
    _write_csv(data_dir / "settlement.csv", settlement)
    (data_dir / "ground_truth.csv").write_text("")
    (data_dir / "bank_statement.csv").write_text("")
    (data_dir / "tax_filing.csv").write_text("")
    summary = run_from_records(
        ledger, settlement, ground_truth=[], reports_dir=reports_dir,
        amount_tolerance_pct=amount_tolerance_pct,
    )
    run_bank_and_tax_reconciliation(settlement, data_dir=data_dir, reports_dir=reports_dir)
    return summary


def run_bank_and_tax_reconciliation(settlement, data_dir=None, reports_dir=None):
    """Third and fourth legs of reconciliation, run alongside the main
    ledger-vs-settlement pass whenever the data exists. Writes
    bank_reconciliation.json and tax_reconciliation.json into reports_dir
    with {"available": False} when there's nothing to reconcile against
    (e.g. after an upload with no bank statement or tax filing), so
    consumers can show "not available" honestly instead of stale data."""
    data_dir = data_dir or DATA_DIR
    reports_dir = reports_dir or REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)

    bank_path = data_dir / "bank_statement.csv"
    if bank_path.exists() and bank_path.stat().st_size > 0:
        bank_rows = _read_csv(bank_path)
        reconciled, exceptions = bank_matcher.reconcile(settlement, bank_rows)
        bank_report = {
            "available": True,
            "reconciled_count": len(reconciled),
            "exception_count": len(exceptions),
            "reconciled": reconciled,
            "exceptions": exceptions,
        }
    else:
        bank_report = {"available": False}
    (reports_dir / "bank_reconciliation.json").write_text(json.dumps(bank_report, indent=2))

    tax_path = data_dir / "tax_filing.csv"
    if tax_path.exists() and tax_path.stat().st_size > 0:
        tax_rows = _read_csv(tax_path)
        periods = tax_matcher.reconcile(settlement, tax_rows)
        tax_report = {"available": True, "periods": periods}
    else:
        tax_report = {"available": False}
    (reports_dir / "tax_reconciliation.json").write_text(json.dumps(tax_report, indent=2))


def run_from_records(ledger, settlement, ground_truth, reports_dir=None, amount_tolerance_pct=None):
    reports_dir = reports_dir or REPORTS_DIR
    matches, exceptions = matcher.match(ledger, settlement, amount_tolerance_pct=amount_tolerance_pct)

    for e in exceptions:
        e["explanation"] = explainer.explain(e)

    result = scorer.score(matches, exceptions, ground_truth)

    reports_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(reports_dir / "matches.csv", matches)
    _write_csv(reports_dir / "exceptions.csv", exceptions)
    (reports_dir / "scorecard.json").write_text(json.dumps(result, indent=2))

    summary = {
        "ledger_rows": len(ledger),
        "settlement_rows": len(settlement),
        "matched_pairs": len(matches),
        "exceptions": len(exceptions),
        "match_rate": round(len(matches) / max(1, len(ledger)), 4),
        "has_ground_truth": bool(ground_truth),
        **result,
    }
    (reports_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def _write_csv(path, rows):
    if not rows:
        path.write_text("")
        return
    fieldnames = sorted({k for r in rows for k in r.keys()})
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
