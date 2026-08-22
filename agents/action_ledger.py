"""Shared audit trail every specialist agent writes to.

This is what makes the system "explainable, bounded and gated" rather than
a black box: every consequential action any agent takes is logged here,
gated two ways -- a dollar-amount threshold, and (for reconciliation
matches specifically) a confidence threshold. A large amount always needs
a human in the loop regardless of how sure the match was; a low-confidence
guess needs one regardless of how small the amount is.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

LEDGER_PATH = Path(__file__).resolve().parent.parent / "reports" / "action_ledger.jsonl"
APPROVAL_THRESHOLD = 5000.0  # amounts at or above this need a human in the loop
CONFIDENCE_THRESHOLD = 0.8  # matches below this confidence need a human in the loop


def record(agent, action, detail, amount=None, confidence=None):
    amount = float(amount) if amount is not None else None
    confidence = float(confidence) if confidence is not None else None
    amount_flag = amount is not None and abs(amount) >= APPROVAL_THRESHOLD
    confidence_flag = confidence is not None and confidence < CONFIDENCE_THRESHOLD
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "action": action,
        "detail": detail,
        "amount": amount,
        "confidence": confidence,
        "needs_human_approval": amount_flag or confidence_flag,
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
