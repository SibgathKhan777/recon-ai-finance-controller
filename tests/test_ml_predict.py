import pytest

from ml.predict import MODEL_PATH, predict

pytestmark = pytest.mark.skipif(not MODEL_PATH.exists(), reason="model.skops not trained yet -- run `python -m ml.train` first")


def test_predicts_a_genuine_exact_match_with_high_confidence():
    ledger = {"ledger_id": "L1", "txn_ref": "RZP123456789", "date": "2026-01-01", "amount": 1000.0}
    settlement = {"settlement_id": "S1", "txn_ref": "RZP123456789", "date": "2026-01-01", "amount": 1000.0}
    result = predict(ledger, settlement)
    assert result["is_match"] is True
    assert result["confidence"] > 0.9


def test_predicts_an_unrelated_pair_as_not_a_match():
    ledger = {"ledger_id": "L1", "txn_ref": "RZP123456789", "date": "2026-01-01", "amount": 1000.0}
    settlement = {"settlement_id": "S2", "txn_ref": "RZP999999999", "date": "2026-01-15", "amount": 42.50}
    result = predict(ledger, settlement)
    assert result["is_match"] is False


def test_returns_the_expected_shape():
    ledger = {"ledger_id": "L1", "txn_ref": "RZP1", "date": "2026-01-01", "amount": 500.0}
    settlement = {"settlement_id": "S1", "txn_ref": "RZP1", "date": "2026-01-01", "amount": 500.0}
    result = predict(ledger, settlement)
    assert set(result.keys()) == {"is_match", "confidence"}
    assert isinstance(result["is_match"], bool)
    assert 0.0 <= result["confidence"] <= 1.0
