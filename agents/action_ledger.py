"""Shared audit trail every specialist agent writes to.

This is what makes the system "explainable, bounded and gated" rather than
a black box: every consequential action any agent takes is logged here,
gated two ways -- a dollar-amount threshold, and (for reconciliation
matches specifically) a confidence threshold. A large amount always needs
a human in the loop regardless of how sure the match was; a low-confidence
guess needs one regardless of how small the amount is.

Approving or rejecting a flagged entry (see approve()/reject() below) never
edits that entry in place -- it appends a new one that references it. Real
audit logs are append-only; a correction is a new record, not a silent
rewrite of history, otherwise "what did the ledger say at the time" stops
being answerable.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

LEDGER_PATH = Path(__file__).resolve().parent.parent / "reports" / "action_ledger.jsonl"
APPROVAL_THRESHOLD = 5000.0  # amounts at or above this need a human in the loop
CONFIDENCE_THRESHOLD = 0.8  # matches below this confidence need a human in the loop


def record(agent, action, detail, amount=None, confidence=None, ledger_path=None):
    ledger_path = ledger_path or LEDGER_PATH
    amount = float(amount) if amount is not None else None
    confidence = float(confidence) if confidence is not None else None
    amount_flag = amount is not None and abs(amount) >= APPROVAL_THRESHOLD
    confidence_flag = confidence is not None and confidence < CONFIDENCE_THRESHOLD
    entry = {
        "id": _next_id(ledger_path),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "action": action,
        "detail": detail,
        "amount": amount,
        "confidence": confidence,
        "needs_human_approval": amount_flag or confidence_flag,
    }
    _append(ledger_path, entry)
    return entry


def approve(entry_id, reviewer, note="", ledger_path=None):
    return _resolve(entry_id, reviewer, "approved", note, ledger_path)


def reject(entry_id, reviewer, note="", ledger_path=None):
    return _resolve(entry_id, reviewer, "rejected", note, ledger_path)


def pending_approvals(ledger_path=None):
    """Entries flagged needs_human_approval that no later approve()/reject()
    has resolved yet -- resolution is looked up by reference, not by
    mutating the original entry, so this always reflects the current state
    without ever rewriting history."""
    entries = read_all(ledger_path)
    resolved_ids = {e["resolves_entry_id"] for e in entries if e.get("resolves_entry_id") is not None}
    return [e for e in entries if e.get("needs_human_approval") and e["id"] not in resolved_ids]


def read_all(ledger_path=None):
    ledger_path = ledger_path or LEDGER_PATH
    if not ledger_path.exists():
        return []
    with ledger_path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def _resolve(entry_id, reviewer, verdict, note, ledger_path):
    entry = {
        "id": _next_id(ledger_path),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": "human_reviewer",
        "action": verdict,
        "detail": note or f"{verdict} by {reviewer}",
        "amount": None,
        "confidence": None,
        "needs_human_approval": False,
        "resolves_entry_id": entry_id,
        "reviewer": reviewer,
    }
    _append(ledger_path, entry)
    return entry


def _next_id(ledger_path):
    return len(read_all(ledger_path)) + 1


def _append(ledger_path, entry):
    ledger_path = ledger_path or LEDGER_PATH
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a") as f:
        f.write(json.dumps(entry) + "\n")
