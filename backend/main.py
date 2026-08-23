"""FastAPI backend for the chat UI (frontend/).

Wraps the same recon/pipeline.py + agents/orchestrator.py used by cli.py and
app.py -- no reconciliation logic lives here, only per-client session
plumbing: each browser session gets its own data/sessions/{id} and
reports/sessions/{id} directories, so one client's uploaded CSVs and chat
history can never leak into another's. That isolation is threaded through
via the data_dir/reports_dir/ledger_path parameters added to pipeline.py
and every agents/*.py module for exactly this purpose.

Session state (the id -> directory mapping) is an in-memory dict, not a
database -- correct for a single-process demo, but it means sessions don't
survive a server restart and this process can't be horizontally scaled
without moving that registry to shared storage. Stated plainly rather than
implied, same as every other honest-scope note in this project.
"""
import csv
import io
import random
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from agents import orchestrator
from recon import generate_data, pipeline

ROOT = Path(__file__).resolve().parent.parent
SESSIONS_DATA_ROOT = ROOT / "data" / "sessions"
SESSIONS_REPORTS_ROOT = ROOT / "reports" / "sessions"

# Whitelisted for both listing and download -- never build a path from a
# client-supplied filename directly, even though today's filenames are
# fixed and not attacker-controlled.
DOWNLOADABLE_FILES = {
    "matches.csv": "Matched pairs",
    "exceptions.csv": "Exceptions",
    "summary.json": "Summary",
    "scorecard.json": "Scorecard",
    "bank_reconciliation.json": "Bank reconciliation",
    "tax_reconciliation.json": "Tax reconciliation",
    "action_ledger.jsonl": "Audit trail",
}

app = FastAPI(title="AI Finance Controller API")

app.add_middleware(
    CORSMiddleware,
    # Regex, not a fixed port -- the Next.js dev server falls back to the
    # next free port (3001, 3002, ...) whenever 3000 is already taken.
    allow_origin_regex=r"http://localhost:\d+",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_SESSIONS = {}


class ChatRequest(BaseModel):
    message: str


def _session_dirs(session_id):
    if session_id not in _SESSIONS:
        raise HTTPException(status_code=404, detail="Unknown or expired session")
    data_dir = SESSIONS_DATA_ROOT / session_id
    reports_dir = SESSIONS_REPORTS_ROOT / session_id
    ledger_path = reports_dir / "action_ledger.jsonl"
    return data_dir, reports_dir, ledger_path


def _read_upload_csv(upload: UploadFile, raw: bytes):
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail=f"{upload.filename} is not valid UTF-8 text")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise HTTPException(status_code=400, detail=f"{upload.filename} has no data rows")
    return rows


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/sessions")
def create_session():
    session_id = uuid.uuid4().hex
    data_dir, reports_dir, _ = _session_dirs_unchecked(session_id)
    data_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    _SESSIONS[session_id] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "has_data": False,
    }
    return {"session_id": session_id}


def _session_dirs_unchecked(session_id):
    data_dir = SESSIONS_DATA_ROOT / session_id
    reports_dir = SESSIONS_REPORTS_ROOT / session_id
    return data_dir, reports_dir, reports_dir / "action_ledger.jsonl"


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    data_dir, reports_dir, _ = _session_dirs(session_id)
    shutil.rmtree(data_dir, ignore_errors=True)
    shutil.rmtree(reports_dir, ignore_errors=True)
    del _SESSIONS[session_id]
    return {"deleted": True}


@app.post("/api/sessions/{session_id}/demo")
def load_demo_data(session_id: str):
    """Generates a fresh synthetic dataset straight into this session's own
    directory (not the shared data/generated/ used by cli.py) -- lets
    someone try the product with one click instead of needing their own
    CSVs, without touching any other session's or the CLI's data."""
    data_dir, reports_dir, _ = _session_dirs(session_id)
    seed = random.SystemRandom().randint(1, 10**9)
    generate_data.generate(seed=seed, out_dir=data_dir)
    summary = pipeline.run(data_dir=data_dir, reports_dir=reports_dir)
    _SESSIONS[session_id]["has_data"] = True
    return {
        "reply": (
            f"Loaded a fresh synthetic demo batch: {summary['ledger_rows']} ledger rows, "
            f"{summary['match_rate'] * 100:.1f}% match rate, {summary['exceptions']} exceptions. "
            "Ask me anything about it, or try 'triage exceptions', 'forecast cash', "
            "'bank reconciliation status', or 'tax reconciliation'."
        ),
        "summary": summary,
    }


@app.post("/api/sessions/{session_id}/upload")
async def upload_data(
    session_id: str,
    ledger: UploadFile,
    settlement: UploadFile,
    tolerance_pct: float | None = Form(None),
):
    """tolerance_pct optionally widens/tightens the fuzzy-match amount
    tolerance (default 2%) for this client's data specifically -- some
    clients' fee handling is messier than others, and forcing everyone
    onto one hardcoded tolerance is exactly the "no-code configurability"
    gap real reconciliation tools (e.g. Cointab's rule engine) close and a
    single hardcoded constant doesn't."""
    data_dir, reports_dir, _ = _session_dirs(session_id)
    ledger_rows = _read_upload_csv(ledger, await ledger.read())
    settlement_rows = _read_upload_csv(settlement, await settlement.read())

    summary = pipeline.run_uploaded(
        ledger_rows, settlement_rows, data_dir=data_dir, reports_dir=reports_dir,
        amount_tolerance_pct=tolerance_pct,
    )
    _SESSIONS[session_id]["has_data"] = True

    accuracy_note = (
        f"{(summary['overall_accuracy'] or 0) * 100:.1f}% accuracy vs ground truth"
        if summary["has_ground_truth"] else "no ground truth to score against -- that's expected for real data"
    )
    return {
        "reply": (
            f"Processed {summary['ledger_rows']} ledger rows against {summary['settlement_rows']} "
            f"settlement rows: {summary['matched_pairs']} matched ({summary['match_rate'] * 100:.1f}%), "
            f"{summary['exceptions']} exceptions, {accuracy_note}. "
            "Ask me about a specific reference, or try 'triage exceptions' or 'forecast cash'."
        ),
        "summary": summary,
    }


@app.post("/api/sessions/{session_id}/chat")
def chat(session_id: str, body: ChatRequest):
    data_dir, reports_dir, ledger_path = _session_dirs(session_id)
    reply = orchestrator.handle(
        body.message, data_dir=data_dir, reports_dir=reports_dir, ledger_path=ledger_path,
    )
    return {"reply": reply}


@app.get("/api/sessions/{session_id}/files")
def list_files(session_id: str):
    _, reports_dir, _ = _session_dirs(session_id)
    available = []
    for filename, label in DOWNLOADABLE_FILES.items():
        path = reports_dir / filename
        if path.exists() and path.stat().st_size > 0:
            available.append({"filename": filename, "label": label})
    return {"files": available}


@app.get("/api/sessions/{session_id}/files/{filename}")
def download_file(session_id: str, filename: str):
    if filename not in DOWNLOADABLE_FILES:
        raise HTTPException(status_code=404, detail="Unknown file")
    _, reports_dir, _ = _session_dirs(session_id)
    path = reports_dir / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not generated yet")
    return FileResponse(path, filename=filename)
