from ml.dataset import NEGATIVES_PER_POSITIVE, build_dataset, build_seed_examples
from recon.generate_data import generate


def teardown_module(module):
    # this module regenerates data/generated/* repeatedly via build_dataset
    generate(seed=42)


def test_build_seed_examples_produces_expected_positive_negative_ratio():
    examples = build_seed_examples(1)
    positives = [e for e in examples if e[1] == 1]
    negatives = [e for e in examples if e[1] == 0]
    assert len(positives) > 0
    assert len(negatives) == len(positives) * NEGATIVES_PER_POSITIVE


def test_negatives_are_never_the_true_match_amount_and_ref_together():
    # a "negative" that's actually identical to a positive would be a
    # mislabeled example, not a hard negative
    examples = build_seed_examples(1)
    for features, label in examples:
        if label == 0:
            assert not (features["ref_exact_match"] == 1.0 and features["amount_diff"] == 0.0)


def test_negatives_are_genuinely_hard_not_random_noise():
    # the whole point of amount-closeness sampling: negatives should be
    # close in amount, not wildly different (which would make the task
    # trivially easy and inflate every model's accuracy identically --
    # this happened with an earlier random-sampling version of this dataset)
    examples = build_seed_examples(1)
    negatives = [f for f, label in examples if label == 0]
    close_amount_negatives = [n for n in negatives if n["amount_diff_pct"] < 0.05]
    assert len(close_amount_negatives) / len(negatives) > 0.5


def test_build_dataset_accumulates_across_multiple_seeds():
    single_seed = build_seed_examples(1)
    two_seeds = build_dataset([1, 2])
    assert len(two_seeds) > len(single_seed)


def test_build_dataset_is_deterministic():
    first = build_dataset([1])
    second = build_dataset([1])
    assert first == second
