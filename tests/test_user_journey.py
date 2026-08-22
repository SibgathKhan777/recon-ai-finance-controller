"""End-to-end user-journey tests.

Unlike the rest of the suite, these don't call internal functions -- they
spawn the real entry points (cli.py, agent_cli.py, app.py) as actual
subprocesses/AppTest sessions and feed them the kind of multi-turn session
a real finance analyst would type, in order, exactly as documented in the
README. This is the closest thing to a human clicking through the demo,
automated so the demo itself can't silently regress.
"""
import csv
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
REPORTS_DIR = REPO_ROOT / "reports"

os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")


def _run_cli(*args, timeout=60):
    return subprocess.run(
        [PYTHON, str(REPO_ROOT / "cli.py"), *args],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout,
    )


def _chat(inputs, timeout=60):
    """Feeds a scripted conversation to the real agent_cli.py subprocess,
    exactly as if a user typed each line and pressed enter."""
    result = subprocess.run(
        [PYTHON, str(REPO_ROOT / "agent_cli.py")],
        cwd=REPO_ROOT, capture_output=True, text=True,
        input="\n".join(inputs) + "\n", timeout=timeout,
    )
    return result.stdout


def _real_ref():
    with open(REPORTS_DIR / "matches.csv", newline="") as f:
        return next(csv.DictReader(f))["txn_ref"]


def _assert_in_order(haystack, needles):
    pos = -1
    for needle in needles:
        idx = haystack.find(needle, pos + 1)
        assert idx > pos, f"expected {needle!r} to appear after position {pos}, transcript:\n{haystack}"
        pos = idx


def setup_module(module):
    result = _run_cli("demo")
    assert result.returncode == 0, result.stderr


def teardown_module(module):
    # leave the repo in the clean default demo state for any other use
    _run_cli("demo")


def test_a_new_users_first_command_works_exactly_as_documented():
    result = _run_cli("demo")
    assert result.returncode == 0
    assert "Overall accuracy vs ground truth" in result.stdout
    assert "Full report:" in result.stdout


def test_an_analyst_explores_the_data_via_the_chat_terminal():
    ref = _real_ref()
    transcript = _chat([
        "what's our match rate",
        f"why didn't {ref} settle",
        "show duplicate exceptions",
        "cash forecast for 10 days",
        "triage exceptions",
        "exit",
    ])
    _assert_in_order(transcript, [
        "Match rate:",
        ref,
        "duplicate settlement exception",
        "Projection:",
        "total exceptions across",
    ])


def test_an_analyst_asks_a_question_before_running_reconciliation_even_once():
    backups = {}
    for name in ["summary.json", "matches.csv", "exceptions.csv"]:
        path = REPORTS_DIR / name
        if path.exists():
            backups[name] = path.read_text()
            path.unlink()
    try:
        transcript = _chat(["what's our match rate", "exit"])
        assert "run reconciliation" in transcript.lower()
    finally:
        for name, content in backups.items():
            (REPORTS_DIR / name).write_text(content)


def test_a_typo_prone_but_common_command_still_works():
    # regression test for a real bug found earlier: "reconcile" is not
    # actually a substring of "reconciliation" -- typing the single most
    # obvious command used to silently fall through to the wrong agent
    transcript = _chat(["please run reconciliation", "exit"])
    assert "Reconciliation run:" in transcript


def test_an_analyst_investigates_a_currency_drift_incident_end_to_end():
    generate = subprocess.run(
        [PYTHON, str(REPO_ROOT / "cli.py"), "generate", "--corrupt", "currency"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert generate.returncode == 0
    assert _run_cli("run").returncode == 0

    transcript = _chat(["triage exceptions", "cash forecast for 7 days", "exit"])
    lower = transcript.lower()
    assert "systemic drift" in lower or "systematic drift" in lower
    assert "%" in transcript


def test_dashboard_user_session_with_multiple_questions_in_one_visit():
    from streamlit.testing.v1 import AppTest

    at, last_err = None, None
    for _ in range(3):
        candidate = AppTest.from_file(str(REPO_ROOT / "app.py"))
        try:
            candidate.run(timeout=60)
            at = candidate
            break
        except RuntimeError as e:
            last_err = e
    if at is None:
        raise last_err

    ref = _real_ref()

    def chat_text(app_test):
        return [m.value for cm in app_test.chat_message for m in cm.markdown]

    at.chat_input[0].set_value("what's our match rate").run(timeout=60)
    assert any("Match rate" in text for text in chat_text(at))

    at.chat_input[0].set_value(f"why didn't {ref} settle").run(timeout=60)
    assert any(ref in text for text in chat_text(at))

    at.slider[0].set_value(21).run(timeout=60)
    assert not at.exception
    assert "Historical daily avg settlement" in [m.label for m in at.metric]
