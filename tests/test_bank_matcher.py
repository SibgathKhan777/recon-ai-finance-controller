from recon.bank_matcher import reconcile


def _settlement(sid, utr, amount, date="2026-01-01"):
    return {"settlement_id": sid, "utr": utr, "amount": amount, "date": date}


def _bank(bid, utr, amount, date="2026-01-01"):
    return {"bank_txn_id": bid, "utr": utr, "amount": amount, "date": date}


def test_simple_one_to_one_reconciliation():
    settlement = [_settlement("S1", "UTR1", 1000.0)]
    bank = [_bank("B1", "UTR1", 1000.0)]
    reconciled, exceptions = reconcile(settlement, bank)
    assert len(reconciled) == 1
    assert reconciled[0]["batch_size"] == 1
    assert not exceptions


def test_batch_of_settlements_reconciles_against_one_bank_credit():
    # the real-world case naive 1:1 matching misses: three separate
    # settlement rows, one aggregated bank transfer
    settlement = [
        _settlement("S1", "BATCH_UTR", 500.0),
        _settlement("S2", "BATCH_UTR", 300.0),
        _settlement("S3", "BATCH_UTR", 200.0),
    ]
    bank = [_bank("B1", "BATCH_UTR", 1000.0)]
    reconciled, exceptions = reconcile(settlement, bank)
    assert len(reconciled) == 1
    assert reconciled[0]["batch_size"] == 3
    assert reconciled[0]["settlement_amount"] == 1000.0
    assert not exceptions


def test_settlement_with_no_bank_credit_is_pending():
    settlement = [_settlement("S1", "UTR1", 1000.0)]
    bank = []
    reconciled, exceptions = reconcile(settlement, bank)
    assert not reconciled
    assert len(exceptions) == 1
    assert exceptions[0]["category"] == "bank_credit_pending"


def test_bank_credit_with_no_settlement_is_unrecognized():
    settlement = []
    bank = [_bank("B1", "UTR1", 1000.0)]
    reconciled, exceptions = reconcile(settlement, bank)
    assert not reconciled
    assert len(exceptions) == 1
    assert exceptions[0]["category"] == "unrecognized_bank_credit"


def test_amount_mismatch_is_flagged_not_silently_reconciled():
    settlement = [_settlement("S1", "UTR1", 1000.0)]
    bank = [_bank("B1", "UTR1", 950.0)]
    reconciled, exceptions = reconcile(settlement, bank)
    assert not reconciled
    assert len(exceptions) == 1
    assert exceptions[0]["category"] == "bank_amount_mismatch"
    assert exceptions[0]["settlement_amount"] == 1000.0
    assert exceptions[0]["bank_amount"] == 950.0


def test_partial_batch_mismatch_is_still_caught():
    # the batch sums to less than the bank credit -- a real gap, not a
    # rounding artifact, must not be silently accepted
    settlement = [
        _settlement("S1", "UTR1", 500.0),
        _settlement("S2", "UTR1", 300.0),
    ]
    bank = [_bank("B1", "UTR1", 1000.0)]  # expected 800, got 1000
    reconciled, exceptions = reconcile(settlement, bank)
    assert not reconciled
    assert exceptions[0]["category"] == "bank_amount_mismatch"


def test_blank_utr_rows_are_ignored_not_crossed():
    settlement = [_settlement("S1", "", 1000.0), _settlement("S2", "UTR1", 500.0)]
    bank = [_bank("B1", "UTR1", 500.0)]
    reconciled, exceptions = reconcile(settlement, bank)
    assert len(reconciled) == 1
    assert reconciled[0]["utr"] == "UTR1"
    assert not exceptions  # the blank-UTR settlement row is neither reconciled nor an exception -- it's simply not in scope for bank-side matching
