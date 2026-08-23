from recon import matcher


def _ledger(id_, ref, date, amount):
    return {"ledger_id": id_, "txn_ref": ref, "date": date, "amount": amount, "merchant": "X", "description": "d"}


def _settlement(id_, ref, date, amount, fee=0.0, tax=0.0, utr=""):
    return {
        "settlement_id": id_, "txn_ref": ref, "date": date, "amount": amount,
        "fee": fee, "tax": tax, "utr": utr, "merchant": "X", "description": "d",
    }


def test_exact_match():
    ledger = [_ledger("L1", "RZP1", "2026-01-01", 100.0)]
    settlement = [_settlement("S1", "RZP1", "2026-01-01", 100.0)]
    matches, exceptions = matcher.match(ledger, settlement)
    assert len(matches) == 1
    assert matches[0]["category"] == "exact"
    assert not exceptions


def test_fee_adjustment_matches_via_exact_gross_arithmetic():
    # 1000 = 990 (net) + 8 (fee) + 2 (tax) -- an exact bookkeeping identity,
    # not a percentage guess, so this earns full confidence
    ledger = [_ledger("L1", "RZP1", "2026-01-01", 1000.0)]
    settlement = [_settlement("S1", "RZP1", "2026-01-01", 990.0, fee=8.0, tax=2.0, utr="AXISCN1234567890")]
    matches, exceptions = matcher.match(ledger, settlement)
    assert len(matches) == 1
    assert matches[0]["category"] == "fee_adjustment"
    assert matches[0]["confidence"] == 1.0
    assert matches[0]["fee"] == 8.0
    assert matches[0]["tax"] == 2.0
    assert matches[0]["utr"] == "AXISCN1234567890"


def test_amount_difference_without_a_stated_fee_does_not_match_as_fee_adjustment():
    # documents an intentional boundary: pass 2 now requires an EXPLICIT
    # fee/tax breakdown that reconciles exactly -- an unexplained amount gap
    # (no fee/tax recorded) is not assumed to be a fee. With the same ref,
    # this still gets picked up by the fuzzy pass (ref similarity 1.0), just
    # not labeled "fee_adjustment" -- there's nothing to verify it against.
    ledger = [_ledger("L1", "RZP1", "2026-01-01", 1000.0)]
    settlement = [_settlement("S1", "RZP1", "2026-01-01", 995.0)]  # no fee/tax stated
    matches, exceptions = matcher.match(ledger, settlement)
    assert len(matches) == 1
    assert matches[0]["category"] != "fee_adjustment"


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


def test_split_settlement_nets_against_one_ledger_row():
    # A legitimate partial-payout split: two settlement legs summing exactly
    # to the ledger invoice. Neither leg alone matches (400 != 1000, 600 !=
    # 1000), so passes 1-2 can't catch this -- pass 3 has to sum the group.
    ledger = [_ledger("L1", "RZP1", "2026-01-01", 1000.0)]
    settlement = [
        _settlement("S1", "RZP1", "2026-01-01", 400.0),
        _settlement("S2", "RZP1", "2026-01-01", 600.0),
    ]
    matches, exceptions = matcher.match(ledger, settlement)
    assert len(matches) == 2
    assert {m["settlement_id"] for m in matches} == {"S1", "S2"}
    assert all(m["category"] == "net_settlement" for m in matches)
    assert all(m["confidence"] == 1.0 for m in matches)
    assert not exceptions


def test_refund_leg_nets_against_original_payout():
    # A refund/reversal: the original payout plus a negative refund leg,
    # summing to the net amount actually booked in the ledger.
    ledger = [_ledger("L1", "RZP1", "2026-01-01", 700.0)]
    settlement = [
        _settlement("S1", "RZP1", "2026-01-01", 1000.0),
        _settlement("S2", "RZP1", "2026-01-01", -300.0),
    ]
    matches, exceptions = matcher.match(ledger, settlement)
    assert len(matches) == 2
    assert {m["settlement_id"] for m in matches} == {"S1", "S2"}
    assert all(m["category"] == "net_settlement" for m in matches)
    assert not exceptions


def test_split_settlement_with_fee_uses_gross_sum():
    # Two legs, net of fee/tax each, whose combined gross reconciles
    # against the ledger invoice -- same identity check as fee_adjustment,
    # just summed across legs instead of a single row.
    ledger = [_ledger("L1", "RZP1", "2026-01-01", 1000.0)]
    settlement = [
        _settlement("S1", "RZP1", "2026-01-01", 396.0, fee=3.0, tax=1.0),
        _settlement("S2", "RZP1", "2026-01-01", 594.0, fee=4.5, tax=1.5),
    ]
    matches, exceptions = matcher.match(ledger, settlement)
    assert len(matches) == 2
    assert all(m["category"] == "net_settlement" for m in matches)


def test_single_leg_is_not_treated_as_net_settlement():
    # A single settlement leg that simply doesn't match should still fall
    # through to the fuzzy pass / exceptions -- pass 3 requires 2+ legs.
    ledger = [_ledger("L1", "RZP1", "2026-01-01", 1000.0)]
    settlement = [_settlement("S1", "RZP1", "2026-01-01", 400.0)]
    matches, exceptions = matcher.match(ledger, settlement)
    assert not any(m["category"] == "net_settlement" for m in matches)


def test_custom_amount_tolerance_widens_fuzzy_pass():
    # Default 2% tolerance rejects this 5% gap; an explicit wider tolerance
    # (e.g. a client known to have messier fee handling) should accept it.
    ledger = [_ledger("L1", "RZP1", "2026-01-01", 1000.0)]
    settlement = [_settlement("S1", "RZP1", "2026-01-01", 950.0)]
    matches, _ = matcher.match(ledger, settlement)
    assert not matches

    matches, _ = matcher.match(ledger, settlement, amount_tolerance_pct=0.06)
    assert len(matches) == 1


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


def test_unambiguous_blank_reference_pair_still_matches_at_lower_confidence():
    ledger = [_ledger("L1", "", "2026-01-01", 500.0)]
    settlement = [_settlement("S1", "", "2026-01-01", 500.0)]
    matches, exceptions = matcher.match(ledger, settlement)
    assert len(matches) == 1
    assert matches[0]["category"] == "matched_no_reference"
    assert matches[0]["confidence"] < 1.0
    assert not exceptions


def test_ambiguous_blank_reference_rows_are_not_cross_matched():
    # two genuinely different transactions, both missing a reference number,
    # coincidentally the same amount and date -- must NOT be guessed at
    ledger = [
        _ledger("L1", "", "2026-01-01", 500.0),
        _ledger("L2", "", "2026-01-01", 500.0),
    ]
    settlement = [
        _settlement("S1", "", "2026-01-01", 500.0),
        _settlement("S2", "", "2026-01-01", 500.0),
    ]
    matches, exceptions = matcher.match(ledger, settlement)
    assert not matches, "ambiguous blank-ref rows must never be auto-matched"
    assert len(exceptions) == 4
    assert all(e["category"] == "ambiguous_no_reference" for e in exceptions)


def test_blank_reference_with_no_counterpart_is_a_plain_exception():
    ledger = [_ledger("L1", "", "2026-01-01", 500.0)]
    settlement = []
    matches, exceptions = matcher.match(ledger, settlement)
    assert not matches
    assert len(exceptions) == 1
    assert exceptions[0]["category"] == "missing_in_settlement"


def test_multiple_unrelated_blank_ref_settlements_are_not_flagged_as_duplicates():
    # different amounts, different days -- these are just three unrelated
    # rows that each happen to lack a reference number, not duplicates
    ledger = []
    settlement = [
        _settlement("S1", "", "2026-01-01", 100.0),
        _settlement("S2", "", "2026-01-05", 250.0),
        _settlement("S3", "", "2026-01-10", 75.0),
    ]
    matches, exceptions = matcher.match(ledger, settlement)
    assert not matches
    assert len(exceptions) == 3
    assert all(e["category"] == "missing_in_ledger" for e in exceptions)
