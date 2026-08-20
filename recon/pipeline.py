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
    ledger = _read_csv(DATA_DIR / "ledger.csv")
    settlement = _read_csv(DATA_DIR / "settlement.csv")
    ground_truth = _read_csv(DATA_DIR / "ground_truth.csv")

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
