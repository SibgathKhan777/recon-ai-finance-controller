"""Trains and evaluates a pairwise ledger/settlement match classifier.

Run: python -m ml.train

Splits by SEED, not by row -- an entire synthetic batch goes to either
train or test, never split across both, so no row from a test batch's
negative-sampling pool leaks into training. Also compares the trained
model against the deterministic matcher's own decisions on the same
held-out seeds -- an honest side-by-side, not just an isolated accuracy
number, since the whole point of this repo's design has been that the
rule-based matcher is the trustworthy path; this is the real test of
whether a learned model actually recovers the same decisions or not.
"""
import json
from pathlib import Path

import skops.io as sio
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

from ml.dataset import DATA_DIR, PAIRED_CATEGORIES, _read_csv, build_dataset
from ml.features import FEATURE_NAMES, to_vector
from recon import matcher
from recon.generate_data import generate

MODEL_PATH = Path(__file__).resolve().parent / "model.skops"
REPORT_PATH = Path(__file__).resolve().parent / "training_report.json"

TRAIN_SEEDS = list(range(1, 71))       # 70 seeds for training
TEST_SEEDS = list(range(1000, 1015))   # disjoint range -- no seed overlap with training


def _to_xy(examples):
    X = [to_vector(f) for f, _ in examples]
    y = [label for _, label in examples]
    return X, y


def _rule_based_accuracy_on_seeds(seeds):
    """For each held-out seed, run the actual deterministic matcher (the
    one the live app uses) and check how many of the ground truth's true
    pairs it reproduces exactly -- the fairest apples-to-apples comparison
    available, since the rule-based matcher doesn't score arbitrary pairs
    the way the classifier does, it picks its own single best candidate."""
    correct, total = 0, 0
    for seed in seeds:
        generate(seed=seed)
        ledger = _read_csv(DATA_DIR / "ledger.csv")
        settlement = _read_csv(DATA_DIR / "settlement.csv")
        ground_truth = _read_csv(DATA_DIR / "ground_truth.csv")

        matches, _ = matcher.match(ledger, settlement)
        matched_pairs = {(m["ledger_id"], m["settlement_id"]) for m in matches}

        for gt in ground_truth:
            if gt["true_category"] not in PAIRED_CATEGORIES:
                continue
            total += 1
            if (gt["ledger_id"], gt["settlement_id"]) in matched_pairs:
                correct += 1
    return {"correct": correct, "total": total, "accuracy": correct / total if total else None}


def train():
    print(f"Building training set from {len(TRAIN_SEEDS)} seeds...")
    train_examples = build_dataset(TRAIN_SEEDS)
    print(f"Building test set from {len(TEST_SEEDS)} seeds (disjoint seed range)...")
    test_examples = build_dataset(TEST_SEEDS)

    X_train, y_train = _to_xy(train_examples)
    X_test, y_test = _to_xy(test_examples)
    print(f"{len(X_train)} training examples, {len(X_test)} test examples")

    model = RandomForestClassifier(n_estimators=200, max_depth=10, random_state=42, class_weight="balanced")
    model.fit(X_train, y_train)

    baseline = LogisticRegression(max_iter=1000, class_weight="balanced")
    baseline.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    y_pred_baseline = baseline.predict(X_test)

    print("Scoring the deterministic matcher on the same held-out seeds for comparison...")
    rule_based = _rule_based_accuracy_on_seeds(TEST_SEEDS)

    report = {
        "task": "binary pairwise match classification (is this ledger/settlement pair a real match?)",
        "train_examples": len(X_train),
        "test_examples": len(X_test),
        "train_seed_range": [TRAIN_SEEDS[0], TRAIN_SEEDS[-1]],
        "test_seed_range": [TEST_SEEDS[0], TEST_SEEDS[-1]],
        "feature_names": FEATURE_NAMES,
        "random_forest": {
            "accuracy": accuracy_score(y_test, y_pred),
            "classification_report": classification_report(y_test, y_pred, output_dict=True),
            "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
            "feature_importances": dict(zip(FEATURE_NAMES, model.feature_importances_.tolist())),
        },
        "logistic_regression_baseline": {
            "accuracy": accuracy_score(y_test, y_pred_baseline),
        },
        "deterministic_matcher_on_same_seeds": rule_based,
    }

    sio.dump(model, MODEL_PATH)
    REPORT_PATH.write_text(json.dumps(report, indent=2))

    # restore the canonical demo state -- this script overwrites
    # data/generated/* many times while building train/test batches
    generate(seed=42)

    print(f"\nRandom Forest pairwise accuracy:      {report['random_forest']['accuracy']:.4f}")
    print(f"Logistic Regression baseline accuracy: {report['logistic_regression_baseline']['accuracy']:.4f}")
    print(f"Deterministic matcher accuracy:        {rule_based['accuracy']:.4f} ({rule_based['correct']}/{rule_based['total']} true pairs reproduced exactly)")
    print(f"\nModel saved to {MODEL_PATH}")
    print(f"Report saved to {REPORT_PATH}")
    return report


if __name__ == "__main__":
    train()
