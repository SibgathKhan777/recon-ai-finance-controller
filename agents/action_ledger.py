"""Shared audit trail every specialist agent writes to.

This is what makes the system "explainable, bounded and gated" rather than
a black box: every consequential action any agent takes is logged here,
with a dollar-amount gate that flags anything above threshold as needing
human sign-off before it would ever be allowed to execute for real.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

LEDGER_PATH = Path(__file__).resolve().parent.parent / "reports" / "action_ledger.jsonl"
APPROVAL_THRESHOLD = 5000.0  # amounts at or above this need a human in the loop


def record(agent, action, detail, amount=None):
    amount = float(amount) if amount is not None else None
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "action": action,
        "detail": detail,
        "amount": amount,
        "needs_human_approval": amount is not None and abs(amount) >= APPROVAL_THRESHOLD,
    }
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def read_all():
    if not LEDGER_PATH.exists():
        return []
    with LEDGER_PATH.open() as f:
        return [json.loads(line) for line in f if line.strip()]
