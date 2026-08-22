"""End-to-end pipeline: load -> match -> explain -> score -> save reports."""
import csv
import json
from pathlib import Path

from recon import explainer, matcher, scorer

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "generated"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def _read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def run():
    """The demo path: synthetic data with known ground truth, so accuracy
    is a real, checkable number."""
    ledger = _read_csv(DATA_DIR / "ledger.csv")
    settlement = _read_csv(DATA_DIR / "settlement.csv")
    ground_truth = _read_csv(DATA_DIR / "ground_truth.csv")
    return run_from_records(ledger, settlement, ground_truth)


def run_uploaded(ledger, settlement):
    """The real-data path: a user's own ledger/settlement records, with no
    ground truth to score against. overall_accuracy and per-category
    accuracy come back None -- that's honest, not a bug, since there's no
    known-correct label to check against for someone's real data.

    Also persists ledger/settlement to data/generated/ (clearing any old
    ground_truth.csv) -- agents/forecast_agent.py reads settlement.csv from
    there directly, not from reports/, so without this it would silently
    keep showing whatever synthetic data was last generated instead of the
    just-uploaded numbers."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _write_csv(DATA_DIR / "ledger.csv", ledger)
    _write_csv(DATA_DIR / "settlement.csv", settlement)
    (DATA_DIR / "ground_truth.csv").write_text("")
    return run_from_records(ledger, settlement, ground_truth=[])


def run_from_records(ledger, settlement, ground_truth):
    matches, exceptions = matcher.match(ledger, settlement)

    for e in exceptions:
        e["explanation"] = explainer.explain(e)

    result = scorer.score(matches, exceptions, ground_truth)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    _write_csv(REPORTS_DIR / "matches.csv", matches)
    _write_csv(REPORTS_DIR / "exceptions.csv", exceptions)
    (REPORTS_DIR / "scorecard.json").write_text(json.dumps(result, indent=2))

    summary = {
        "ledger_rows": len(ledger),
        "settlement_rows": len(settlement),
        "matched_pairs": len(matches),
        "exceptions": len(exceptions),
        "match_rate": round(len(matches) / max(1, len(ledger)), 4),
        "has_ground_truth": bool(ground_truth),
        **result,
    }
    (REPORTS_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
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
