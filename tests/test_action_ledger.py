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
