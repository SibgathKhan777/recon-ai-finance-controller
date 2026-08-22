"""Builds a labeled pairwise training dataset from many synthetic batches.

Reuses recon/generate_data.py -- the exact same generator that produces
the demo dataset and its ground truth -- across many seeds, so every
positive example has a real known-correct label, not a heuristic guess.

Positive examples: a ledger/settlement pair the generator actually created
as a genuine relationship (exact, fee_adjustment, timing, corrupted_ref,
matched_no_reference). Categories with no true 1:1 counterpart --
missing_in_*, ambiguous_no_reference, duplicate_settlement, systematic
drift -- are excluded from the pairwise task entirely rather than forced
into a match/no-match label that doesn't actually apply to them.

Negative examples: each positive's ledger row paired with the settlement
rows *closest in amount* to it (excluding the true match) -- genuinely
hard negatives, not trivially-easy random noise. A random cross-pair is
almost always wildly different in amount, date, and reference, which
makes the task trivially separable and inflates every model's accuracy to
look identical (verified directly: an early version of this dataset used
random negatives and every model, including a plain logistic regression,
scored a suspicious 100% -- not a real result, a sign the task was too
easy). Amount-closeness negatives force the model to actually use the
reference/date signal instead of amount alone.
"""
import csv
from pathlib import Path

from ml.features import extract
from recon.generate_data import generate

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "generated"

NEGATIVES_PER_POSITIVE = 3
PAIRED_CATEGORIES = {"exact", "fee_adjustment", "timing", "corrupted_ref", "matched_no_reference"}


def _read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def build_seed_examples(seed):
    generate(seed=seed)
    ledger = _read_csv(DATA_DIR / "ledger.csv")
    settlement = _read_csv(DATA_DIR / "settlement.csv")
    ground_truth = _read_csv(DATA_DIR / "ground_truth.csv")

    ledger_by_id = {r["ledger_id"]: r for r in ledger}
    settlement_by_id = {r["settlement_id"]: r for r in settlement}
    settlement_ids = list(settlement_by_id.keys())

    examples = []
    for gt in ground_truth:
        if gt["true_category"] not in PAIRED_CATEGORIES:
            continue
        lid, sid = gt["ledger_id"], gt["settlement_id"]
        if not lid or not sid or lid not in ledger_by_id or sid not in settlement_by_id:
            continue

        lrow, srow = ledger_by_id[lid], settlement_by_id[sid]
        ledger_amount = float(lrow["amount"])
        examples.append((extract(lrow, srow), 1))

        # Excludes candidates feature-identical to the true match (same ref,
        # same amount) -- these exist on purpose (duplicate_settlement rows
        # are exact clones by design) and no feature set can tell them apart
        # from the real match. Labeling one "not a match" would be a direct
        # label contradiction: the same feature vector as a positive,
        # tagged negative. That's genuine ambiguity the matcher itself
        # handles with an ID tie-break, not a hard-but-learnable negative.
        candidates = [
            s for s in settlement_ids
            if s != sid and not (
                settlement_by_id[s]["txn_ref"] == srow["txn_ref"]
                and abs(float(settlement_by_id[s]["amount"]) - ledger_amount) < 0.01
            )
        ]
        candidates.sort(key=lambda cid: abs(float(settlement_by_id[cid]["amount"]) - ledger_amount))
        for neg_sid in candidates[:NEGATIVES_PER_POSITIVE]:
            examples.append((extract(lrow, settlement_by_id[neg_sid]), 0))

    return examples


def build_dataset(seeds):
    all_examples = []
    for seed in seeds:
        all_examples.extend(build_seed_examples(seed))
    return all_examples
