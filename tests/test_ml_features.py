from ml.features import FEATURE_NAMES, extract, to_vector


def _ledger(ref="RZP1", date="2026-01-01", amount=1000.0):
    return {"ledger_id": "L1", "txn_ref": ref, "date": date, "amount": amount}


def _settlement(ref="RZP1", date="2026-01-01", amount=1000.0, fee=0.0, tax=0.0):
    return {"settlement_id": "S1", "txn_ref": ref, "date": date, "amount": amount, "fee": fee, "tax": tax}


def test_identical_pair_has_zero_diffs_and_full_similarity():
    f = extract(_ledger(), _settlement())
    assert f["amount_diff"] == 0.0
    assert f["date_diff_days"] == 0
    assert f["ref_exact_match"] == 1.0
    assert f["ref_similarity"] == 1.0
    assert f["gross_reconciles"] == 1.0


def test_fee_and_tax_are_included_in_gross_reconciliation():
    f = extract(_ledger(amount=1000.0), _settlement(amount=990.0, fee=8.0, tax=2.0))
    assert f["gross_reconciles"] == 1.0
    assert f["amount_diff"] == 10.0  # net difference, not gross


def test_unexplained_amount_gap_does_not_gross_reconcile():
    f = extract(_ledger(amount=1000.0), _settlement(amount=995.0))
    assert f["gross_reconciles"] == 0.0


def test_blank_refs_have_zero_similarity_not_a_crash():
    f = extract(_ledger(ref=""), _settlement(ref=""))
    assert f["ref_similarity"] == 0.0
    assert f["has_ledger_ref"] == 0.0
    assert f["has_settlement_ref"] == 0.0
    assert f["ref_exact_match"] == 0.0  # blank == blank must NOT count as a real match


def test_unparseable_date_does_not_crash():
    f = extract(_ledger(date="not-a-date"), _settlement(date="2026-01-01"))
    assert f["date_diff_days"] == 999


def test_zero_ledger_amount_does_not_divide_by_zero():
    f = extract(_ledger(amount=0.0), _settlement(amount=100.0))
    assert f["amount_diff_pct"] == 1.0


def test_to_vector_matches_feature_names_order():
    f = extract(_ledger(), _settlement())
    vec = to_vector(f)
    assert len(vec) == len(FEATURE_NAMES)
    assert vec == [f[name] for name in FEATURE_NAMES]
