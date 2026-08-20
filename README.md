# Recon — an AI Finance Controller agent

Reconciles a ledger against a settlement file, explains every exception in
plain English, and — unlike most reconciliation demos — scores its own
output against known ground truth, so the accuracy numbers are real, not
vibes.

Built for the **Razorpay AI Buildathon — Track 04: AI Finance Controller**.

## What it solves

Every payments business runs a version of this loop: the ledger says one
thing, the settlement file from the bank/gateway says another, and someone
has to figure out why — fees, timing, typos, duplicates, or a genuinely
missing transaction — before the books close. This agent automates the
first pass: match what can be matched with confidence, explain what can't,
and flag when a pile of "exceptions" is actually one systemic problem.

## Architecture

```
generate_data.py  ->  ledger.csv + settlement.csv + ground_truth.csv
                              |
                              v
matcher.py   - deterministic core, 3 passes (exact -> tolerance -> fuzzy),
               plus a post-pass that looks for a *systematic* amount drift
               across otherwise-unmatched pairs (see "What broke" below)
                              |
                              v
explainer.py - turns each exception into a plain-English explanation.
               Uses Claude if ANTHROPIC_API_KEY is set, otherwise a
               template fallback - the pipeline always runs end to end.
                              |
                              v
scorer.py    - compares predictions to ground_truth.csv: overall accuracy,
               per-category accuracy, and every misclassified row, so the
               "measured accuracy" claim is checkable, not asserted.
                              |
                              v
              reports/summary.json, scorecard.json, matches.csv, exceptions.csv
                              |
                              v
              app.py - Streamlit dashboard over the above
```

The matching core is deliberately **not** LLM-based — exact/fuzzy/tolerance
matching is cheap, fast, and auditable. The LLM is used only where judgment
is genuinely needed: writing a human-readable explanation for a row a human
still has to review.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate    # optional
pip install -r requirements.txt

python cli.py demo          # generates ~285 synthetic rows and runs the full pipeline
streamlit run app.py        # open the dashboard
```

No API key required to run it end to end. Set `ANTHROPIC_API_KEY` (see
`.env.example`) to switch exception explanations from templates to live
Claude output.

## Commands

| Command | What it does |
|---|---|
| `python cli.py demo` | generate data + run pipeline + print summary (one shot) |
| `python cli.py generate --corrupt currency` | regenerate data with an injected batch-level anomaly |
| `python cli.py run` | re-run the pipeline against already-generated data |
| `streamlit run app.py` | dashboard: match rate, per-category accuracy, exception explorer |
| `python -m pytest` | unit tests for the matcher and scorer |

## Honest numbers, not a demo trick

`python cli.py demo` prints something like:

```
Ledger rows:      143
Settlement rows:  142
Matched pairs:    127
Exceptions:       16
Match rate:       88.8%
Overall accuracy vs ground truth: 96.5%

Per-category accuracy:
  exact                         100/100  (100.0%)
  fee_adjustment                  15/15  (100.0%)
  timing                          12/12  (100.0%)
  corrupted_ref                     7/8  ( 87.5%)
  missing_in_settlement             8/8  (100.0%)
  missing_in_ledger                 4/4  (100.0%)
  duplicate_settlement              3/3  (100.0%)
```

Every row in `ground_truth.csv` has a known correct label that the matcher
never sees — the scorecard is a real evaluation, including where it's
wrong (`reports/scorecard.json -> misclassified`).

## What broke, and how I caught it

Run:

```bash
python cli.py demo --corrupt currency
```

This injects a **3.5% systematic amount drift** into ~15% of settlement
rows — simulating a currency-conversion or fee-schedule change upstream.
3.5% is deliberately just past the matcher's 2% fee-tolerance band, so
pass 2 (tolerance matching) silently misses every affected row, and each
one falls through to exceptions individually — a pile of unrelated-looking
"missing" rows instead of one root cause.

**The fix**: a post-pass (`matcher._flag_batch_drift`) looks at unmatched
pairs that still share an exact reference and checks whether their amount
ratios cluster tightly around a common value. If three or more do, it
re-labels them `systematic_drift_suspected` with the detected ratio
instead of leaving them as N generic exceptions — so the exception list
says "investigate a 3.5% batch-wide drift" instead of burying the signal
in a pile of one-off rows.

This is the honest version of "what broke": a tolerance-band matcher is
correct for per-transaction noise (fees, rounding) but blind to
batch-level shifts by construction, and needed an explicit second check.

## Known limitations

- Fuzzy ref matching (`difflib.SequenceMatcher`) is fine for single-character
  typos but won't catch a fully re-issued reference ID — that would need a
  learned matcher or a merchant-side reference map.
- The drift detector needs 3+ affected rows sharing an exact reference to
  trigger; a single anomalous transaction still shows up as a plain
  exception, correctly.
- Synthetic data only — no real Razorpay API calls are made (matches the
  track's test-mode / synthetic-data framing).

## Project layout

```
cli.py                 entry point
app.py                 Streamlit dashboard
recon/
  generate_data.py     synthetic ledger + settlement + ground truth
  matcher.py            3-pass matching engine + batch-drift detector
  explainer.py          LLM / template exception explanations
  scorer.py              accuracy scoring against ground truth
  pipeline.py            orchestrates the above, writes reports/
tests/                  pytest unit tests for matcher + scorer
```

## Filling out the application form

- **Project name**: Recon — AI Finance Controller
- **What it solves**: see "What it solves" above
- **Track**: AI Finance Controller
- **What broke, and how you got out**: see "What broke" above — adapt it
  to your own words, and ideally add your own debugging story once you've
  run it, poked at it, and (better yet) broken something yourself.
