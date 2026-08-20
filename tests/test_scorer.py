from recon import scorer


def test_perfect_score():
    matches = [{"ledger_id": "L1", "settlement_id": "S1", "category": "exact"}]
    ground_truth = [{"ledger_id": "L1", "settlement_id": "S1", "true_category": "exact"}]
    result = scorer.score(matches, [], ground_truth)
    assert result["overall_accuracy"] == 1.0
    assert result["misclassified"] == []


def test_misclassification_is_reported():
    matches = [{"ledger_id": "L1", "settlement_id": "S1", "category": "exact"}]
    ground_truth = [{"ledger_id": "L1", "settlement_id": "S1", "true_category": "fee_adjustment"}]
    result = scorer.score(matches, [], ground_truth)
    assert result["overall_accuracy"] == 0.0
    assert len(result["misclassified"]) == 1
    assert result["misclassified"][0]["true_category"] == "fee_adjustment"
    assert result["misclassified"][0]["predicted_category"] == "exact"


def test_drift_suspected_counts_as_a_correct_catch():
    exceptions = [{"ledger_id": "L1", "settlement_id": "", "category": "systematic_drift_suspected"}]
    ground_truth = [{"ledger_id": "L1", "settlement_id": "", "true_category": "missing_in_settlement"}]
    result = scorer.score([], exceptions, ground_truth)
    assert result["overall_accuracy"] == 1.0


def test_per_category_breakdown():
    matches = [
        {"ledger_id": "L1", "settlement_id": "S1", "category": "exact"},
        {"ledger_id": "L2", "settlement_id": "S2", "category": "exact"},
    ]
    ground_truth = [
        {"ledger_id": "L1", "settlement_id": "S1", "true_category": "exact"},
        {"ledger_id": "L2", "settlement_id": "S2", "true_category": "exact"},
    ]
    result = scorer.score(matches, [], ground_truth)
    assert result["per_category"]["exact"]["total"] == 2
    assert result["per_category"]["exact"]["correct"] == 2
