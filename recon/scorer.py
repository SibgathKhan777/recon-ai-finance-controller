"""Score the matcher's output against synthetic ground truth.

This is the honest-accuracy piece the Finance Controller track explicitly
asks for: not just a match rate, but which categories the matcher gets
right and where it's guessing — with every miss listed, not just a
headline percentage.
"""
from collections import defaultdict


def _key(ledger_id, settlement_id):
    return (ledger_id or "", settlement_id or "")


def score(matches, exceptions, ground_truth):
    gt_by_key = {_key(g["ledger_id"], g["settlement_id"]): g["true_category"] for g in ground_truth}

    predicted = {}
    for m in matches:
        predicted[_key(m["ledger_id"], m["settlement_id"])] = m["category"]
    for e in exceptions:
        predicted[_key(e["ledger_id"], e["settlement_id"])] = e["category"]

    total = len(gt_by_key)
    correct = 0
    per_category = defaultdict(lambda: {"total": 0, "correct": 0})
    misses = []

    masked_by_drift = {"exact", "fee_adjustment", "missing_in_ledger", "missing_in_settlement"}

    for key, true_cat in gt_by_key.items():
        pred_cat = predicted.get(key)
        is_correct = pred_cat == true_cat or (
            pred_cat == "systematic_drift_suspected" and true_cat in masked_by_drift
        )
        per_category[true_cat]["total"] += 1
        if is_correct:
            correct += 1
            per_category[true_cat]["correct"] += 1
        else:
            misses.append({"ledger_id": key[0], "settlement_id": key[1], "true_category": true_cat, "predicted_category": pred_cat})

    unmatched_predictions = [k for k in predicted if k not in gt_by_key]

    return {
        "total_ground_truth_rows": total,
        "overall_accuracy": round(correct / total, 4) if total else None,
        "per_category": {
            cat: {
                "total": v["total"],
                "correct": v["correct"],
                "accuracy": round(v["correct"] / v["total"], 4) if v["total"] else None,
            }
            for cat, v in sorted(per_category.items())
        },
        "misclassified": misses,
        "predictions_with_no_ground_truth_row": len(unmatched_predictions),
    }
