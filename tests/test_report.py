from recon.report import build_report


def _match(ledger_id, settlement_id, ledger_amount, settlement_amount, category, confidence=1.0):
    return {
        "ledger_id": ledger_id, "settlement_id": settlement_id, "txn_ref": f"REF-{ledger_id}",
        "ledger_amount": ledger_amount, "settlement_amount": settlement_amount,
        "category": category, "confidence": confidence,
    }


def _exception(row_id, amount, side, category, date="2026-01-01"):
    return {
        "ledger_id": row_id if side == "ledger" else "",
        "settlement_id": row_id if side == "settlement" else "",
        "txn_ref": f"REF-{row_id}", "amount": amount, "date": date, "side": side, "category": category,
    }


def test_exact_matches_go_to_fully_matched():
    matches = [_match("L1", "S1", 100.0, 100.0, "exact")]
    report = build_report(matches, [])
    assert report["fully_matched"]["ledger_count"] == 1
    assert report["fully_matched"]["ledger_amount"] == 100.0
    assert report["partially_matched"]["ledger_count"] == 0


def test_non_exact_matches_go_to_partially_matched():
    matches = [_match("L1", "S1", 1000.0, 990.0, "fee_adjustment")]
    report = build_report(matches, [])
    assert report["partially_matched"]["ledger_count"] == 1
    assert report["partially_matched"]["settlement_amount"] == 990.0
    assert report["fully_matched"]["ledger_count"] == 0


def test_net_settlement_legs_dedupe_ledger_side_but_not_settlement_side():
    matches = [
        _match("L1", "S1", 1000.0, 400.0, "net_settlement"),
        _match("L1", "S2", 1000.0, 600.0, "net_settlement"),
    ]
    report = build_report(matches, [])
    bucket = report["partially_matched"]
    assert bucket["ledger_count"] == 1  # one invoice, not two
    assert bucket["ledger_amount"] == 1000.0
    assert bucket["settlement_count"] == 2  # two real settlement legs
    assert bucket["settlement_amount"] == 1000.0
    assert bucket["difference"] == 0.0


def test_unmatched_splits_by_side():
    exceptions = [
        _exception("L9", 500.0, "ledger", "missing_in_settlement"),
        _exception("S9", 300.0, "settlement", "missing_in_ledger"),
    ]
    report = build_report([], exceptions)
    assert report["unmatched"]["ledger_count"] == 1
    assert report["unmatched"]["ledger_amount"] == 500.0
    assert report["unmatched"]["settlement_count"] == 1
    assert report["unmatched"]["settlement_amount"] == 300.0
    assert report["unmatched"]["difference"] == -200.0
    assert len(report["unmatched"]["ledger_rows"]) == 1
    assert len(report["unmatched"]["settlement_rows"]) == 1


def test_total_sums_all_three_buckets():
    matches = [
        _match("L1", "S1", 100.0, 100.0, "exact"),
        _match("L2", "S2", 1000.0, 990.0, "fee_adjustment"),
    ]
    exceptions = [_exception("L9", 50.0, "ledger", "missing_in_settlement")]
    report = build_report(matches, exceptions)
    total = report["total"]
    assert total["ledger_count"] == 3
    assert total["ledger_amount"] == 1150.0
    assert total["settlement_count"] == 2
    assert total["settlement_amount"] == 1090.0
    assert total["difference"] == round(1090.0 - 1150.0, 2)


def test_empty_input_produces_zeroed_report():
    report = build_report([], [])
    assert report["total"] == {
        "ledger_amount": 0.0, "ledger_count": 0,
        "settlement_amount": 0.0, "settlement_count": 0, "difference": 0.0,
    }
    assert report["fully_matched"]["rows"] == []
    assert report["unmatched"]["ledger_rows"] == []
    assert report["unmatched"]["settlement_rows"] == []
