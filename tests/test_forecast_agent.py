from agents import forecast_agent


def test_forecast_structure():
    result = forecast_agent.forecast(horizon_days=5)
    assert "projection" in result
    assert len(result["projection"]) == 5
    assert "historical_daily_average" in result
    assert "at_risk_amount_pending_settlement" in result


def test_forecast_dates_are_sequential_and_unique():
    result = forecast_agent.forecast(horizon_days=3)
    dates = [p["date"] for p in result["projection"]]
    assert dates == sorted(dates)
    assert len(set(dates)) == 3


def test_at_risk_matches_missing_in_settlement_total():
    import csv
    from pathlib import Path

    exceptions = list(csv.DictReader(open(Path(__file__).resolve().parent.parent / "reports" / "exceptions.csv")))
    expected = sum(float(e["amount"]) for e in exceptions if e["category"] == "missing_in_settlement")
    result = forecast_agent.forecast()
    assert abs(result["at_risk_amount_pending_settlement"] - expected) < 0.01
