# ML: a trained match classifier (separate from the live app)

This subsystem trains an actual machine-learning model — not just the
rule-based reconciliation engine the rest of this repo uses. It answers
one honest, specific question: **can a learned model recover the same
match/no-match decisions the deterministic matcher makes?**

It is **not** wired into `recon/matcher.py` or the live Streamlit app.
That engine stays deterministic and auditable on purpose — see the main
[README](../README.md#what-broke-and-how-i-caught-it) for why. This is a
separate, clearly-scoped experiment, trainable and hostable on its own.

## Quickstart

```bash
pip install scikit-learn skops huggingface_hub   # optional, ml/ only

python -m ml.train                    # trains, evaluates, saves ml/model.skops
python -m ml.push_to_huggingface <your-username>/<repo-name>   # your own HF account
```

`python -m ml.train` takes a few minutes (builds ~46k labeled examples
across 85 synthetic batches). See `ml/training_report.json` for the full
results after running it, and `ml/MODEL_CARD.md` for the honest writeup —
training data, results table, and known limitations — that ships to
Hugging Face alongside the model.

## How it works

| File | Role |
|---|---|
| `features.py` | Extracts 10 pairwise features from a (ledger, settlement) candidate — amount/date closeness, reference similarity, exact gross-arithmetic reconciliation |
| `dataset.py` | Builds a labeled training set from `recon/generate_data.py` across many seeds — positives from real ground truth, hard negatives from amount-closest non-matches |
| `train.py` | Trains a Random Forest + Logistic Regression baseline, evaluates on a disjoint seed range, and scores the deterministic matcher on the same held-out seeds for an honest side-by-side |
| `predict.py` | Loads the saved model and scores a new candidate pair — usable standalone |
| `push_to_huggingface.py` | Uploads `model.skops` + the model card to your own HF Hub repo |

## The actual finding, stated honestly

The task is framed as **pairwise binary classification**: is this
(ledger, settlement) candidate pair a real match? Categories with no true
1:1 pairing (missing counterparts, ambiguous no-reference, duplicate
settlements) are excluded from this framing entirely, rather than forced
into a match/no-match label that doesn't fit them.

An early version of the negative-sampling strategy used random
cross-pairs, and every model — including a plain logistic regression —
scored a suspicious 100%. That wasn't a real result, it was a sign the
task was too easy (a random pair is almost always wildly different in
every dimension). Fixed by sampling **hard negatives**: settlement rows
closest in amount to the ledger row, excluding the true match — genuinely
forcing the model to use reference/date signal, not just amount.

That surfaced a second, more interesting issue: some "hard negatives"
turned out to be **feature-identical to the true positive** — Razorpay-
style duplicate-settlement clones, which are exact copies by design. No
feature set can distinguish which of two identical settlement rows is
"the real one" (the deterministic matcher itself only resolves this via
an arbitrary ID tie-break, not real signal). Labeling one a "negative"
would have been a direct label contradiction — same features, opposite
label. Fixed by excluding these from the negative pool rather than
mislabeling them.

With that fixed, the model reaches the same accuracy as the deterministic
matcher on held-out data, and its feature importances converge on the
same signal the hand-written rules already use (`gross_reconciles` and
reference similarity dominate). See `training_report.json` for exact
numbers — they'll differ slightly across retrains since scikit-learn's
`RandomForestClassifier` isn't bit-for-bit deterministic across versions,
even with a fixed `random_state`.

## Known limitations

See `MODEL_CARD.md` — trained and evaluated entirely on synthetic data
from this project's own generator, never real Razorpay transactions; the
pairwise framing excludes the genuinely ambiguous cases; no audit trail or
confidence-threshold gating like the live app's `action_ledger`.
