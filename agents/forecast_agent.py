"""Cash Forecaster agent.

Projects a short-term cash position from realized settlements, plus the
Reconciliation Agent's own exception list -- an honest forecast that
separately calls out what's still unresolved, rather than a naive
trendline that pretends every pending payment already landed.

No LLM, no API key: this is arithmetic over real settlement data, which is
exactly the kind of number a Finance Controller agent should never let a
model "estimate" when it can just be computed.
"""
import csv
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "generated"


def _read_csv(path):
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def forecast(horizon_days=7):
    settlement = _read_csv(DATA_DIR / "settlement.csv")
    exceptions = _read_csv(REPORTS_DIR / "exceptions.csv")

    if not settlement:
        return {"error": "No settlement data found -- ask me to 'run reconciliation' first."}

    daily = defaultdict(float)
    for row in settlement:
        daily[row["date"]] += float(row["amount"])

    days_sorted = sorted(daily)
    values = [daily[d] for d in days_sorted]
    avg_daily = statistics.mean(values)

    trend = 0.0
    if len(values) >= 2:
        mid = max(1, len(values) // 2)
        first_half_avg = statistics.mean(values[:mid])
        second_half_avg = statistics.mean(values[mid:]) if values[mid:] else first_half_avg
        trend = (second_half_avg - first_half_avg) / mid

    last_date = datetime.fromisoformat(days_sorted[-1])
    projection = []
    running = avg_daily
    for i in range(1, horizon_days + 1):
        running += trend
        projection.append({
            "date": (last_date + timedelta(days=i)).date().isoformat(),
            "projected_amount": round(running, 2),
        })

    at_risk = [e for e in exceptions if e["category"] == "missing_in_settlement"]
    at_risk_total = sum(float(e["amount"]) for e in at_risk)

    drift_rows = [e for e in exceptions if e["category"] == "systematic_drift_suspected"]
    drift_note = None
    if drift_rows:
        ratio = float(drift_rows[0].get("drift_ratio", 1.0))
        drift_note = (
            f"{len(drift_rows)} unresolved rows show a {((ratio - 1) * 100):+.2f}% systematic "
            "drift -- if unresolved, future settlements will keep landing off by roughly that "
            "ratio until the root cause is fixed, not just these rows."
        )

    return {
        "horizon_days": horizon_days,
        "historical_daily_average": round(avg_daily, 2),
        "trend_per_day": round(trend, 2),
        "projection": projection,
        "at_risk_amount_pending_settlement": round(at_risk_total, 2),
        "at_risk_count": len(at_risk),
        "drift_note": drift_note,
    }
