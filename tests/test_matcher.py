from recon import matcher


def _ledger(id_, ref, date, amount):
    return {"ledger_id": id_, "txn_ref": ref, "date": date, "amount": amount, "merchant": "X", "description": "d"}


def _settlement(id_, ref, date, amount):
    return {"settlement_id": id_, "txn_ref": ref, "date": date, "amount": amount, "merchant": "X", "description": "d"}


def test_exact_match():
    ledger = [_ledger("L1", "RZP1", "2026-01-01", 100.0)]
    settlement = [_settlement("S1", "RZP1", "2026-01-01", 100.0)]
    matches, exceptions = matcher.match(ledger, settlement)
    assert len(matches) == 1
    assert matches[0]["category"] == "exact"
    assert not exceptions


def test_fee_adjustment_within_tolerance():
    ledger = [_ledger("L1", "RZP1", "2026-01-01", 1000.0)]
    settlement = [_settlement("S1", "RZP1", "2026-01-01", 995.0)]
    matches, exceptions = matcher.match(ledger, settlement)
    assert len(matches) == 1
    assert matches[0]["category"] == "fee_adjustment"


def test_timing_mismatch_within_window():
    ledger = [_ledger("L1", "RZP1", "2026-01-05", 1000.0)]
    settlement = [_settlement("S1", "RZP1", "2026-01-03", 1000.0)]
    matches, exceptions = matcher.match(ledger, settlement)
    assert len(matches) == 1
    assert matches[0]["category"] == "timing"


def test_corrupted_ref_within_amount_and_date_window():
    ledger = [_ledger("L1", "RZP123456789", "2026-01-01", 1000.0)]
    settlement = [_settlement("S1", "RZP123456780", "2026-01-01", 1000.0)]
    matches, exceptions = matcher.match(ledger, settlement)
    assert len(matches) == 1
    assert matches[0]["category"] == "corrupted_ref"


def test_missing_in_settlement():
    ledger = [_ledger("L1", "RZP1", "2026-01-01", 1000.0)]
    settlement = []
    matches, exceptions = matcher.match(ledger, settlement)
    assert not matches
    assert len(exceptions) == 1
    assert exceptions[0]["category"] == "missing_in_settlement"


def test_missing_in_ledger():
    ledger = []
    settlement = [_settlement("S1", "RZP1", "2026-01-01", 1000.0)]
    matches, exceptions = matcher.match(ledger, settlement)
    assert not matches
    assert len(exceptions) == 1
    assert exceptions[0]["category"] == "missing_in_ledger"


def test_duplicate_settlement_detected():
    ledger = [_ledger("L1", "RZP1", "2026-01-01", 1000.0)]
    settlement = [
        _settlement("S1", "RZP1", "2026-01-01", 1000.0),
        _settlement("S2", "RZP1", "2026-01-01", 1000.0),
        _settlement("S3", "RZP1", "2026-01-01", 1000.0),
    ]
    matches, exceptions = matcher.match(ledger, settlement)
    assert len(matches) == 1
    assert len(exceptions) == 2
    assert all(e["category"] == "duplicate_settlement" for e in exceptions)


def test_batch_drift_detected_across_clustered_ratios():
    ledger = [_ledger(f"L{i}", f"RZPREF{i}", "2026-01-01", 1000.0) for i in range(4)]
    # settlement amounts are ~3.5% higher than ledger — outside the 2% tolerance,
    # but consistent across all 4 rows, so the drift detector should catch it.
    settlement = [_settlement(f"S{i}", f"RZPREF{i}", "2026-01-01", 1035.0) for i in range(4)]
    matches, exceptions = matcher.match(ledger, settlement)
    assert not matches
    assert all(e["category"] == "systematic_drift_suspected" for e in exceptions)
