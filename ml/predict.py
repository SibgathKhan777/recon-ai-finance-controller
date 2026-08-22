"""Inference helper for the trained pairwise match classifier.

Not wired into the live reconciliation app -- recon/matcher.py remains the
system of record for actual matching decisions, deterministic and
auditable by design. This module exists so the trained model is usable
standalone (locally, or after downloading it back from Hugging Face),
independent of the rest of this project.
"""
from pathlib import Path

import skops.io as sio

from ml.features import extract, to_vector

MODEL_PATH = Path(__file__).resolve().parent / "model.skops"

_model = None


def _get_model():
    global _model
    if _model is None:
        trusted = sio.get_untrusted_types(file=MODEL_PATH)
        _model = sio.load(MODEL_PATH, trusted=trusted)
    return _model


def predict(ledger_row, settlement_row):
    """Returns {"is_match": bool, "confidence": float} for one candidate
    pair. confidence is the model's predicted probability of a match."""
    model = _get_model()
    features = extract(ledger_row, settlement_row)
    vector = [to_vector(features)]
    is_match = bool(model.predict(vector)[0])
    proba = model.predict_proba(vector)[0]
    match_class_index = list(model.classes_).index(1)
    return {"is_match": is_match, "confidence": float(proba[match_class_index])}
