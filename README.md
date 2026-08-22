# Ledger — a multi-agent AI Finance Controller

An orchestrator agent that routes finance-ops questions to specialist
agents — Reconciliation, Settlement Q&A, Cash Forecaster, and Exception &
Anomaly — each grounded in real, scored data. No agent invents a number;
every figure in every answer traces back to an actual row.

Built for the **Razorpay AI Buildathon — Track 04: AI Finance Controller**.

## Why this shape

Razorpay's own **Agent Studio** (launched March 2026, built on Anthropic's
Claude Agent SDK) already ships a natural-language interface where a
merchant can upload a bank statement and ask the system to match it
against Razorpay settlements — work that used to take hours of manual
reconciliation. This project is built in that same architectural language
on purpose: an orchestrator fielding plain-English requests, routing to
specialist agents, with every consequential action logged to a shared,
bounded audit trail — not a single script that does one thing.

## What it solves

Every payments business runs a version of the same loop: the ledger says
one thing, the settlement file says another, cash needs to be forecast
under uncertainty, and someone has to answer "why didn't this settle" on
demand. Four agents split that work:

- **Reconciliation Agent** — matches ledger against settlement across
  three passes (exact → tolerance → fuzzy), and catches *systemic* drift
  (a currency/fee-schedule change) as one root cause instead of dozens of
  one-off exceptions.
- **Settlement Q&A Agent** — answers "why didn't RZP... settle", fee
  totals, duplicate lists, drift status, and match-rate questions in plain
  English, grounded only in the actual reconciliation output.
- **Cash Forecaster Agent** — projects a short-term cash position from
  realized settlements, and separately calls out money still at risk in
  pending exceptions rather than pretending it already landed.
- **Exception & Anomaly Agent** — proactively triages the exception list:
  which rows are one-offs to clear, and which are one systemic issue
  wearing thirty different transaction IDs.

## Architecture

```
                    ┌──────────────────────────┐
   "why didn't      │     Orchestrator          │  agents/orchestrator.py
   RZP... settle?"   │  rule-based intent router │  no API key needed to route —
   "cash forecast    │  (agent_cli.py / app.py)  │  always inspectable, never a
   for 14 days"      └────────────┬─────────────┘  black box
                                   │
        ┌──────────────┬──────────┼──────────────┬───────────────┐
        ▼              ▼          ▼              ▼               │
  Reconciliation   Settlement  Cash          Exception &          │
  Agent            Q&A Agent  Forecaster     Anomaly Agent        │
  (recon/*)        (agents/   (agents/       (agents/             │
                    qa_agent)  forecast_     exception_agent)     │
                               agent)                             │
        │              │          │              │                │
        └──────────────┴──────────┴──────────────┴────────────────┘
                                   ▼
                    Shared Action Ledger (agents/action_ledger.py)
                    every action logged, amounts >= Rs.5,000 flagged
                    needs_human_approval — explainable, bounded, gated
```

The Reconciliation Agent's own output (`reports/exceptions.csv`,
`summary.json`) is the shared substrate the other three agents read from —
the Cash Forecaster's "at risk" figure and drift warning come directly
from the Reconciliation Agent's exception list, not a separate estimate.

The matching core stays deliberately **not** LLM-based — exact/fuzzy/
tolerance matching is cheap, fast, and auditable. The LLM (optional,
`ANTHROPIC_API_KEY`) is used only where judgment is genuinely needed:
phrasing an exception explanation, or answering an open-ended question the
Q&A agent's keyword rules don't cover. Which specialist handles a message
is always decided by the deterministic router, with or without a key.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate    # optional
pip install -r requirements.txt

python cli.py demo          # generate synthetic data, run the reconciliation pipeline
python agent_cli.py         # talk to the multi-agent system in your terminal
streamlit run app.py        # or: dashboard with a chat box for the same agents
```

No API key required for any of the above. Set `ANTHROPIC_API_KEY` (see
`.env.example`) to let the Reconciliation Agent's exception explanations
and the Q&A agent's open-ended answers be phrased by Claude instead of
templates.

Try in `agent_cli.py`:

```
> run reconciliation
> what's our match rate
> why didn't RZP123456789 settle        (use a real ref from reports/matches.csv)
> cash forecast for 14 days
> show duplicate exceptions
> triage exceptions
```

## Commands

| Command | What it does |
|---|---|
| `python cli.py demo` | generate data + run the reconciliation pipeline + print summary |
| `python cli.py generate --corrupt currency` | regenerate data with an injected batch-level anomaly |
| `python cli.py run` | re-run the pipeline against already-generated data |
| `python agent_cli.py` | interactive terminal chat across all four agents |
| `streamlit run app.py` | dashboard: metrics, exception explorer, cash forecast chart, agent chat box |
| `python -m pytest` | 30 unit tests across the matcher, scorer, and all four agents |

## Honest numbers, not a demo trick

`python cli.py demo` prints something like:

```
Ledger rows:      141
Settlement rows:  141
Matched pairs:    134
Exceptions:       14
Match rate:       95.0%
Overall accuracy vs ground truth: 100.0%

Per-category accuracy:
  corrupted_ref                  7/7    (100.0%)
  duplicate_settlement           3/3    (100.0%)
  exact                        100/100  (100.0%)
  fee_adjustment                15/15   (100.0%)
  missing_in_ledger              4/4    (100.0%)
  missing_in_settlement          7/7    (100.0%)
  timing                        12/12   (100.0%)
```

Every row in `ground_truth.csv` has a known correct label the matcher
never sees — the scorecard is a real evaluation, including where it's
wrong (`reports/scorecard.json -> misclassified`). Verified clean across
30 random seeds, not cherry-picked.

The Q&A and Cash Forecaster agents inherit this honesty by construction:
they only ever read `reports/*` — they cannot answer with a number that
didn't come from a scored pipeline run.

## What broke, and how I caught it

Two real bugs, found by testing rather than assumed away.

**1. A currency-drift batch, and the fix that catches it.** Run:

```bash
python cli.py demo --corrupt currency
```

This injects a 3.5% systematic amount drift into ~15% of settlement rows
— simulating a currency-conversion or fee-schedule change upstream. 3.5%
is deliberately just past the matcher's 2% fee-tolerance band, so the
tolerance pass silently misses every affected row, and each one falls
through to exceptions individually — dozens of unrelated-looking "missing"
rows instead of one root cause. The fix (`matcher._flag_batch_drift`)
looks at unmatched pairs that still share an exact reference and checks
whether their amount ratios cluster tightly around a common value; if
three or more do, it re-labels them `systematic_drift_suspected` with the
detected ratio instead of leaving them as N generic exceptions. The Cash
Forecaster then surfaces that same drift note automatically, because it
reads the Reconciliation Agent's own exception list rather than
maintaining a separate view of the data.

**2. The orchestrator's own router had a keyword bug.** The first working
version routed `"reconcil|run recon..."` — but `"reconcile"` is not
actually a substring of `"reconciliation"` (`reconcile` and `reconciliation`
diverge after `reconcil`: e-vs-i). So typing "run reconciliation" — the
single most obvious thing a user would type — silently fell through to
the Q&A agent's generic fallback message instead of running the pipeline.
Caught by an actual terminal smoke test, not code review; fixed by
matching the stem (`reconcil\w*`) instead of the whole word. A reminder
that a router built by pattern-matching keywords needs to be tested with
the keywords a *user* would actually type, not the ones the author
happened to write first.

## Known limitations

- The orchestrator's routing is keyword-based, not intent-classified by an
  LLM — it will misroute a phrasing that doesn't match any pattern (falls
  through to Q&A, which at least won't fabricate an answer, but won't run
  the right specialist either).
- Fuzzy ref matching (`difflib.SequenceMatcher`) handles single-character
  typos but not a fully re-issued reference ID.
- The drift detector needs 3+ affected rows sharing an exact reference to
  trigger; a single anomalous transaction still shows up as a plain
  exception, correctly.
- The cash forecast is a linear trend over historical settlement, not a
  seasonality-aware model — intentionally simple and auditable rather than
  a black-box estimate.
- Synthetic data only — no real Razorpay API calls are made (matches the
  track's test-mode / synthetic-data framing).

## Project layout

```
cli.py                    reconciliation-only entry point
agent_cli.py               multi-agent terminal chat entry point
app.py                     Streamlit dashboard + agent chat box
recon/
  generate_data.py         synthetic ledger + settlement + ground truth
  matcher.py                3-pass matching engine + batch-drift detector
  explainer.py               LLM / template exception explanations
  scorer.py                    accuracy scoring against ground truth
  pipeline.py                   orchestrates the above, writes reports/
agents/
  orchestrator.py           routes a message to the right specialist
  qa_agent.py                 grounded settlement Q&A
  forecast_agent.py            cash forecast + at-risk amount
  exception_agent.py            exception triage / prioritization
  action_ledger.py               shared, bounded, gated audit trail
tests/                     30 pytest tests across recon/ and agents/
```

## Filling out the application form

- **Project name**: Ledger — a multi-agent AI Finance Controller
- **What it solves**: see "What it solves" above
- **Track**: AI Finance Controller
- **What broke, and how you got out**: see "What broke" above — both bugs
  are real and both were caught by actually running the thing, not by
  reading the code. Adapt to your own words, and add your own story once
  you've broken something yourself.
