from agents import action_ledger


def test_large_amount_flagged_for_approval():
    entry = action_ledger.record("test_agent", "test_action", "detail", amount=10000)
    assert entry["needs_human_approval"] is True


def test_small_amount_not_flagged():
    entry = action_ledger.record("test_agent", "test_action", "detail", amount=100)
    assert entry["needs_human_approval"] is False


def test_no_amount_not_flagged():
    entry = action_ledger.record("test_agent", "test_action", "detail")
    assert entry["needs_human_approval"] is False


def test_low_confidence_flagged_for_approval_even_with_small_amount():
    entry = action_ledger.record("test_agent", "test_action", "detail", amount=10, confidence=0.72)
    assert entry["needs_human_approval"] is True


def test_high_confidence_and_small_amount_not_flagged():
    entry = action_ledger.record("test_agent", "test_action", "detail", amount=10, confidence=1.0)
    assert entry["needs_human_approval"] is False


def test_high_confidence_but_large_amount_still_flagged():
    entry = action_ledger.record("test_agent", "test_action", "detail", amount=10000, confidence=1.0)
    assert entry["needs_human_approval"] is True


def test_confidence_exactly_at_threshold_is_not_flagged():
    entry = action_ledger.record("test_agent", "test_action", "detail", confidence=0.8)
    assert entry["needs_human_approval"] is False
