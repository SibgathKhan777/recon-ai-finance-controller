"""Tests for the Streamlit dashboard (app.py) using streamlit's own
AppTest harness -- runs the real script headlessly and inspects the
resulting element tree. No browser involved.

Note on flakiness: the very first AppTest.run() in a process occasionally
took far longer than every subsequent one during testing -- reproducible
often enough in a cold/fresh venv to matter, but a traced, instrumented
single run showed zero network calls during the slow case, so it isn't
confirmed to be the usage-stats telemetry call specifically. Disabled that
telemetry anyway (env var here, plus .streamlit/config.toml so `streamlit
run app.py` doesn't hang for real users either) since there's no reason a
demo app should phone home, but that alone did not reliably eliminate the
flakiness in a from-scratch venv. _first_run() below retries with a fresh
AppTest instance -- an instance can't be reused after a timeout, since
AppTest shuts its runner down when one occurs.
"""
import os

os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")

from pathlib import Path

from streamlit.testing.v1 import AppTest

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")
TIMEOUT = 60


def _first_run(retries=3):
    last_err = None
    for _ in range(retries):
        at = AppTest.from_file(APP_PATH)
        try:
            at.run(timeout=TIMEOUT)
            return at
        except RuntimeError as e:
            last_err = e
    raise last_err


def test_app_runs_without_exception():
    at = _first_run()
    assert not at.exception


def test_app_title():
    at = _first_run()
    assert at.title[0].value == "AI Finance Controller — multi-agent system"


def test_app_shows_reconciliation_metrics():
    at = _first_run()
    values = [m.value for m in at.metric]
    assert "100.0%" in values  # accuracy vs ground truth
    assert any("%" in v for v in values)  # match rate is present in some form


def test_app_shows_cash_forecast_slider_and_chart():
    at = _first_run()
    assert at.slider[0].label == "Forecast horizon (days)"
    labels = [m.label for m in at.metric]
    assert "Historical daily avg settlement" in labels
    assert "At risk (pending settlement)" in labels


def test_app_warns_when_no_report_exists():
    summary_path = REPORTS_DIR / "summary.json"
    backup = summary_path.read_text()
    summary_path.unlink()
    try:
        at = _first_run()
        assert not at.exception
        assert any("No report found" in w.value for w in at.warning)
    finally:
        summary_path.write_text(backup)


def test_chat_box_routes_through_the_real_orchestrator():
    at = _first_run()
    at.text_input[0].input("what's our match rate").run(timeout=TIMEOUT)
    assert not at.exception
    assert any("Match rate" in c.value for c in at.code)


def test_chat_box_grounded_ref_lookup_does_not_hallucinate():
    at = _first_run()
    at.text_input[0].input("why didn't RZP999999998 settle").run(timeout=TIMEOUT)
    assert any("no record" in c.value.lower() for c in at.code)
