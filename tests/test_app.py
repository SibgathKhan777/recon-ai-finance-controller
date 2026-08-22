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


def test_app_stays_usable_with_no_report_yet():
    # the app used to hard-stop with no report -- now the Upload tab must
    # stay reachable even for a brand-new user with nothing generated yet
    summary_path = REPORTS_DIR / "summary.json"
    backup = summary_path.read_text()
    summary_path.unlink()
    try:
        at = _first_run()
        assert not at.exception
        assert any("No report yet" in i.value for i in at.info)
        assert "Upload data" in [t.label for t in at.tabs]
        assert len(at.file_uploader) == 2
    finally:
        summary_path.write_text(backup)


def _chat_message_text(at):
    return [m.value for cm in at.chat_message for m in cm.markdown]


def test_chat_box_routes_through_the_real_orchestrator():
    at = _first_run()
    at.chat_input[0].set_value("what's our match rate").run(timeout=TIMEOUT)
    assert not at.exception
    assert any("Match rate" in text for text in _chat_message_text(at))


def test_chat_box_grounded_ref_lookup_does_not_hallucinate():
    at = _first_run()
    at.chat_input[0].set_value("why didn't RZP999999998 settle").run(timeout=TIMEOUT)
    assert any("no record" in text.lower() for text in _chat_message_text(at))


def _restore_demo_state():
    from recon.generate_data import generate
    from recon.pipeline import run as run_demo
    generate(seed=42)
    run_demo()


def test_upload_tab_reconciles_uploaded_csvs_end_to_end():
    import json

    ledger_csv = (
        "ledger_id,txn_ref,date,amount\n"
        "L1,ABC123,2026-08-01,1000.00\n"
        "L2,ABC124,2026-08-02,500.00\n"
        "L3,ABC125,2026-08-03,750.00\n"
    )
    settlement_csv = (
        "settlement_id,txn_ref,date,amount\n"
        "S1,ABC123,2026-08-01,1000.00\n"
        "S2,ABC124,2026-08-02,500.00\n"
    )
    try:
        at = _first_run()
        at.file_uploader[0].set_value(("ledger.csv", ledger_csv.encode(), "text/csv"))
        at.file_uploader[1].set_value(("settlement.csv", settlement_csv.encode(), "text/csv"))
        at.run(timeout=TIMEOUT)
        at.button[0].click().run(timeout=TIMEOUT)
        assert not at.exception

        summary = json.loads((REPORTS_DIR / "summary.json").read_text())
        assert summary["ledger_rows"] == 3
        assert summary["settlement_rows"] == 2
        assert summary["matched_pairs"] == 2
        assert summary["exceptions"] == 1
        assert summary["has_ground_truth"] is False
        assert summary["overall_accuracy"] is None
    finally:
        _restore_demo_state()


def test_upload_tab_rejects_a_csv_missing_required_columns():
    bad_ledger_csv = "id,ref,when,total\n1,ABC123,2026-08-01,1000.00\n"
    settlement_csv = "settlement_id,txn_ref,date,amount\nS1,ABC123,2026-08-01,1000.00\n"
    try:
        at = _first_run()
        at.file_uploader[0].set_value(("ledger.csv", bad_ledger_csv.encode(), "text/csv"))
        at.file_uploader[1].set_value(("settlement.csv", settlement_csv.encode(), "text/csv"))
        at.run(timeout=TIMEOUT)
        at.button[0].click().run(timeout=TIMEOUT)
        assert not at.exception
        assert any("missing required column" in e.value.lower() for e in at.error)
    finally:
        _restore_demo_state()


def test_uploaded_data_flows_into_the_cash_forecaster_not_stale_demo_data():
    # regression test for a real bug: the forecaster reads data/generated/
    # settlement.csv directly, not reports/ -- uploading without persisting
    # there left it silently showing the previous (demo) dataset's forecast
    ledger_csv = "ledger_id,txn_ref,date,amount\nL1,ABC123,2026-08-01,1000.00\nL2,ABC124,2026-08-02,500.00\n"
    settlement_csv = "settlement_id,txn_ref,date,amount\nS1,ABC123,2026-08-01,1000.00\nS2,ABC124,2026-08-02,500.00\n"
    try:
        at = _first_run()
        at.file_uploader[0].set_value(("ledger.csv", ledger_csv.encode(), "text/csv"))
        at.file_uploader[1].set_value(("settlement.csv", settlement_csv.encode(), "text/csv"))
        at.run(timeout=TIMEOUT)
        at.button[0].click().run(timeout=TIMEOUT)
        assert not at.exception

        labels = {m.label: m.value for m in at.metric}
        # 1000 + 500 = 1500 across 2 days = 750/day -- not whatever the
        # previous (much larger, many-row) demo dataset would show
        assert labels["Historical daily avg settlement"] == "Rs.750.00"
    finally:
        _restore_demo_state()
