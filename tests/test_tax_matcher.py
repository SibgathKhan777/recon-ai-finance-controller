from recon.tax_matcher import reconcile


def _settlement(date, tax):
    return {"date": date, "tax": tax}


def _filing(period, filed_tax_amount):
    return {"period": period, "vendor_gstin": "TEST", "filed_tax_amount": filed_tax_amount, "invoice_count": 1}


def test_matching_period_is_reconciled():
    settlement = [_settlement("2026-07-15", 100.0)]
    filing = [_filing("2026-07", 100.0)]
    results = reconcile(settlement, filing)
    assert len(results) == 1
    assert results[0]["status"] == "reconciled"
    assert results[0]["note"] == ""


def test_under_filed_period_is_flagged_as_mismatch():
    settlement = [_settlement("2026-07-15", 200.0)]
    filing = [_filing("2026-07", 100.0)]
    results = reconcile(settlement, filing)
    assert results[0]["status"] == "mismatch"
    assert results[0]["difference"] == -100.0
    assert "less GST" in results[0]["note"]


def test_over_filed_period_is_flagged_with_a_different_note():
    settlement = [_settlement("2026-07-15", 100.0)]
    filing = [_filing("2026-07", 150.0)]
    results = reconcile(settlement, filing)
    assert results[0]["status"] == "mismatch"
    assert results[0]["difference"] == 50.0
    assert "more GST" in results[0]["note"]


def test_rows_with_zero_tax_are_excluded_from_book_total():
    settlement = [_settlement("2026-07-15", 0.0), _settlement("2026-07-16", 50.0)]
    filing = [_filing("2026-07", 50.0)]
    results = reconcile(settlement, filing)
    assert results[0]["book_tax"] == 50.0
    assert results[0]["invoice_count"] == 1


def test_small_rounding_difference_is_not_flagged():
    settlement = [_settlement("2026-07-15", 100.001)]
    filing = [_filing("2026-07", 100.0)]
    results = reconcile(settlement, filing)
    assert results[0]["status"] == "reconciled"


def test_multiple_periods_each_scored_independently():
    settlement = [_settlement("2026-07-15", 100.0), _settlement("2026-08-15", 200.0)]
    filing = [_filing("2026-07", 100.0), _filing("2026-08", 150.0)]
    results = reconcile(settlement, filing)
    assert len(results) == 2
    by_period = {r["period"]: r for r in results}
    assert by_period["2026-07"]["status"] == "reconciled"
    assert by_period["2026-08"]["status"] == "mismatch"


def test_period_with_no_filing_at_all_is_fully_under_filed():
    settlement = [_settlement("2026-07-15", 100.0)]
    filing = []
    results = reconcile(settlement, filing)
    assert results[0]["filed_tax"] == 0.0
    assert results[0]["status"] == "mismatch"


def test_filed_period_with_no_book_transactions_is_flagged_too():
    settlement = []
    filing = [_filing("2026-07", 100.0)]
    results = reconcile(settlement, filing)
    assert results[0]["book_tax"] == 0.0
    assert results[0]["status"] == "mismatch"
