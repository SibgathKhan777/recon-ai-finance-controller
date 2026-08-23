from agents import action_ledger


def test_flagged_entry_appears_in_pending_approvals(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    entry = action_ledger.record("test_agent", "matched", "detail", amount=10000, ledger_path=ledger_path)
    pending = action_ledger.pending_approvals(ledger_path=ledger_path)
    assert [p["id"] for p in pending] == [entry["id"]]


def test_approving_removes_entry_from_pending_without_rewriting_it(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    entry = action_ledger.record("test_agent", "matched", "detail", amount=10000, ledger_path=ledger_path)
    action_ledger.approve(entry["id"], reviewer="alice", ledger_path=ledger_path)

    pending = action_ledger.pending_approvals(ledger_path=ledger_path)
    assert pending == []

    all_entries = action_ledger.read_all(ledger_path=ledger_path)
    assert len(all_entries) == 2  # original entry preserved verbatim, approval appended separately
    original = next(e for e in all_entries if e["id"] == entry["id"])
    assert original["needs_human_approval"] is True  # never mutated in place
    approval = next(e for e in all_entries if e.get("resolves_entry_id") == entry["id"])
    assert approval["action"] == "approved"
    assert approval["reviewer"] == "alice"


def test_rejecting_also_resolves_the_pending_flag(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    entry = action_ledger.record("test_agent", "matched", "detail", confidence=0.5, ledger_path=ledger_path)
    action_ledger.reject(entry["id"], reviewer="bob", note="looks wrong", ledger_path=ledger_path)
    assert action_ledger.pending_approvals(ledger_path=ledger_path) == []
    approval = next(e for e in action_ledger.read_all(ledger_path=ledger_path) if e.get("action") == "rejected")
    assert approval["detail"] == "looks wrong"


def test_entries_not_needing_approval_never_show_up_as_pending(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    action_ledger.record("test_agent", "matched", "detail", amount=10, confidence=1.0, ledger_path=ledger_path)
    assert action_ledger.pending_approvals(ledger_path=ledger_path) == []


def test_ids_are_sequential_per_ledger_file(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    e1 = action_ledger.record("a", "x", "d", ledger_path=ledger_path)
    e2 = action_ledger.record("a", "x", "d", ledger_path=ledger_path)
    assert e2["id"] == e1["id"] + 1


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
