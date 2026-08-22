"""Regression guard: reconciliation accuracy must not silently degrade.

Two real bugs (a date-blind exact-match pass, and a duplicate-detection
rule that only worked for one specific duplicate shape) were found earlier
only by sweeping many random seeds -- a single clean run at seed=42 wasn't
proof of anything. This test locks that check into the suite (and CI) so a
future change can't reintroduce a seed-dependent failure unnoticed.
"""
from recon.generate_data import generate
from recon.pipeline import run

SEEDS = list(range(1, 21))  # matches the sweep done during manual debugging
MIN_ACCURACY = 0.98


def teardown_module(module):
    # leave the repo in the clean default demo state other tests/dev use expect
    generate(seed=42)
    run()


def test_accuracy_does_not_regress_across_many_seeds():
    failures = []
    for seed in SEEDS:
        generate(seed=seed)
        summary = run()
        accuracy = summary["overall_accuracy"] or 0
        if accuracy < MIN_ACCURACY:
            failures.append((seed, accuracy, summary.get("misclassified")))

    assert not failures, "accuracy regression on seed(s): " + ", ".join(
        f"seed={s} accuracy={a:.4f} misclassified={m}" for s, a, m in failures
    )
