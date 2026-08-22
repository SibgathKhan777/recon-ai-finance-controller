# Ledger — a multi-agent AI Finance Controller

![tests](https://github.com/SibgathKhan777/recon-ai-finance-controller/actions/workflows/tests.yml/badge.svg)

An orchestrator agent that routes finance-ops questions to specialist
agents — Reconciliation, Settlement Q&A, Cash Forecaster, Exception &
Anomaly, and Claim Verification — each grounded in real, scored data. No
agent invents a number; every figure in every answer traces back to an
actual row.

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
under uncertainty, someone has to answer "why didn't this settle" on
demand, and a customer or merchant's claim about a payment needs checking
against reality rather than taken on faith. Five agents split that work:

- **Reconciliation Agent** — matches ledger against settlement across
  three passes (exact → gross arithmetic → fuzzy), and catches *systemic*
  drift (a currency/fee-schedule change) as one root cause instead of
  dozens of one-off exceptions.
- **Settlement Q&A Agent** — answers "why didn't RZP... settle", fee
  totals, duplicate lists, drift status, and match-rate questions in plain
  English, grounded only in the actual reconciliation output.
- **Cash Forecaster Agent** — projects a short-term cash position from
  realized settlements, and separately calls out money still at risk in
  pending exceptions rather than pretending it already landed.
- **Exception & Anomaly Agent** — proactively triages the exception list:
  which rows are one-offs to clear, and which are one systemic issue
  wearing thirty different transaction IDs.
- **Claim Verification Agent** — checks a customer or merchant's claim
  about a payment ("I never received my payout for RZP...") against the
  actual reconciliation record. Never declares anyone dishonest — a
  mismatch is flagged for human review via the same action ledger, not
  auto-resolved.

## Architecture

```
              "why didn't RZP... settle?"  /  "cash forecast for 14 days"  /
              "I never received my payout for RZP..."
                                   │
                                   ▼
                    ┌──────────────────────────┐
                    │       Orchestrator        │   agents/orchestrator.py
                    │  rule-based intent router │   no API key needed to route —
                    │  (agent_cli.py / app.py)  │   always inspectable, never
                    └────────────┬─────────────┘   a black box
                                  │
     ┌───────────────┬───────────┼───────────┬───────────────┬────────────────┐
     ▼               ▼           ▼           ▼               ▼
Reconciliation   Settlement   Cash        Exception &     Claim
Agent            Q&A Agent   Forecaster   Anomaly Agent   Verification Agent
(recon/*)        (agents/    (agents/     (agents/        (agents/
                 qa_agent)   forecast_    exception_       claim_verifier)
                             agent)       agent)
     │               │           │           │               │
     └───────────────┴───────────┴───────────┴───────────────┘
                                  ▼
                    Shared Action Ledger (agents/action_ledger.py)
                    every action logged; amount ≥ Rs.5,000, confidence
                    < 0.8, or a contradicted claim always gets flagged
                    needs_human_approval — explainable, bounded, gated
```

The Reconciliation Agent's own output (`reports/exceptions.csv`,
`summary.json`, `matches.csv`) is the shared substrate the other four
agents read from — the Cash Forecaster's "at risk" figure and drift
warning, and the Claim Verification Agent's factual check, all come
directly from the Reconciliation Agent's own records, not a separate
estimate.

The matching core stays deliberately **not** LLM-based — exact/fuzzy/
tolerance matching is cheap, fast, and auditable. The LLM (optional,
`ANTHROPIC_API_KEY`) is used only where judgment is genuinely needed:
phrasing an exception explanation, or answering an open-ended question the
Q&A agent's keyword rules don't cover.

### Optional: LangGraph tool-calling router

`agents/orchestrator.py::smart_handle` (used by both `agent_cli.py` and
`app.py`) is the real entry point, not `handle` directly. Without an API
key it's just `handle` under a different name — same deterministic
regex router, same behavior, no change. With `ANTHROPIC_API_KEY` set (and
the optional `langgraph` + `langchain` + `langchain-anthropic` packages,
already in `requirements.txt`), it upgrades to
`agents/langgraph_orchestrator.py`: the same five agents wrapped as
LangChain tools, with an LLM (Claude Haiku, via `langchain.agents.
create_agent`) deciding which one to call from the raw message instead of
matching against a fixed regex list.

This is what actually solves the deterministic router's real limitation —
the "verify claim:" trigger phrase exists only because the rule-based
router can't tell a claim from a question by phrasing alone. The
LangGraph path can: it reads the `verify_claim` tool's description and
routes a bare "I never received my payout for RZP..." there directly, no
special syntax required. The trade-off is real and stated plainly: this
path costs an API call per message and its tool choice isn't
deterministic, which is exactly why it's opt-in rather than the default.

Tested without ever calling the real Anthropic API: each tool is a plain
function tested directly, and the full graph is tested against
`langchain_core`'s `FakeMessagesListChatModel`, which scripts a tool call
deterministically so the actual `create_agent`/tool-dispatch machinery
gets exercised without a network call or a key.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate    # optional
pip install -r requirements.txt

python cli.py demo          # generate synthetic data, run the reconciliation pipeline
python agent_cli.py         # talk to the multi-agent system in your terminal
streamlit run app.py        # or: dashboard with a chat box for the same agents
```

`app.py`'s **"Upload data"** tab also takes your own ledger/settlement CSVs
directly — no synthetic data required. It runs them through the same
`recon/matcher.py` engine; the only difference is there's no ground truth
to score accuracy against, so that shows as `N/A` rather than a
percentage, honestly, instead of a fabricated number. See `ml/README.md`
for a separate, standalone trained classifier (not used by the live app)
built on the same synthetic data.

No API key required for any of the above. Set `ANTHROPIC_API_KEY` (see
`.env.example`) to let the Reconciliation Agent's exception explanations
and the Q&A agent's open-ended answers be phrased by Claude instead of
templates, and to upgrade both `agent_cli.py` and `app.py` to the
LangGraph tool-calling router (see "Optional: LangGraph tool-calling
router" above) instead of the deterministic one.

Try in `agent_cli.py`:

```
> run reconciliation
> what's our match rate
> why didn't RZP123456789 settle        (use a real ref from reports/matches.csv)
> cash forecast for 14 days
> show duplicate exceptions
> triage exceptions
> verify claim: I never received my payout for RZP123456789
```

## Commands

| Command | What it does |
|---|---|
| `python cli.py demo` | generate data + run the reconciliation pipeline + print summary |
| `python cli.py generate --corrupt currency` | regenerate data with an injected batch-level anomaly |
| `python cli.py run` | re-run the pipeline against already-generated data |
| `python agent_cli.py` | interactive terminal chat across all five agents |
| `streamlit run app.py` | dashboard: metrics, exception explorer, cash forecast chart, agent chat box, claim verification tab |
| `python -m pytest` | 121 tests: unit tests across the matcher/scorer/agents, plus end-to-end user-journey tests that spawn the real CLI as subprocesses |

## Honest numbers, not a demo trick

`python cli.py demo` prints something like:

```
Ledger rows:      145
Settlement rows:  145
Matched pairs:    136
Exceptions:       18
Match rate:       93.8%
Overall accuracy vs ground truth: 100.0%

Per-category accuracy:
  ambiguous_no_reference         4/4    (100.0%)
  corrupted_ref                  7/7    (100.0%)
  duplicate_settlement           3/3    (100.0%)
  exact                        100/100  (100.0%)
  fee_adjustment                15/15   (100.0%)
  matched_no_reference           2/2    (100.0%)
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

Real bugs, found by testing (and research) rather than assumed away.

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

**3. Blank reference numbers could cause a false match.** Research into
real reconciliation-system postmortems flagged missing/truncated reference
fields as the single most common real-world failure mode. Tested directly:
two *different* transactions with blank references, same amount, same day,
got silently matched to each other at `confidence: 1.0` — the matcher did
plain string equality on `txn_ref`, so `"" == ""` was treated exactly like
a real matching reference. Fixed with a fourth matching pass: blank-ref
rows only auto-match when there's exactly one candidate on each side
sharing that amount+date; anything ambiguous (two candidates on either
side) is now flagged `ambiguous_no_reference` for manual review instead of
guessed. Also fixed a second-order bug this exposed: the duplicate-
detection logic counted blank refs via a plain `Counter`, so multiple
unrelated blank-ref rows were being flagged as "duplicates of each other"
purely for sharing the empty string.

**4. The audit trail never saw the matcher's own decisions.** The
Reconciliation Agent's matches never reached `action_ledger` — only
orchestrator-level actions (running the pipeline, forecasting) did. A
low-confidence fuzzy match could get auto-accepted with no
`needs_human_approval` flag, which undercuts the "every money action
explainable, bounded and gated" bar this track is judged on. Fixed:
`agents/orchestrator.py` now logs every non-trivial match (confidence < 1.0
or amount above the approval threshold) to the ledger, and
`action_ledger.record()` gates on confidence as well as amount — a large
amount always needs a human regardless of match confidence, and a
low-confidence match always needs one regardless of amount.

Verifying this end to end (not just unit-testing it) surfaced a real gap:
on the dataset as it stood, every flagged entry was amount-driven, not
confidence-driven — synthetic corrupted-ref matches score ~0.92 similarity
(a single-char typo out of 12 characters), comfortably above the 0.8 gate,
so the mechanism was correct but never actually demonstrated by
`python cli.py demo`. Fixed by adding an **unreferenced-transaction**
scenario to the generator: two transactions with a blank reference number
(a real data-quality issue — some payment channels never capture a
structured reference at all) that the matcher still matches, correctly,
but at `confidence: 0.5` — now a genuine confidence-driven approval flag
shows up in `reports/action_ledger.jsonl` on every default demo run,
alongside a small ambiguous cluster (two blank-ref ledger rows, two
blank-ref settlement rows, same amount and date) that correctly comes out
as `ambiguous_no_reference` instead of being guessed at. Ask the Q&A agent
"show ambiguous exceptions" to see it, or check the ledger directly.

**5. Our schema didn't match Razorpay's real one, and fee-matching was
guessing when it didn't need to.** Research into Razorpay's actual
`settlement.processed` webhook payload showed real settlement records carry
separate `fees` and `tax` fields (plus a `utr` for bank-side reconciliation)
— our synthetic data baked the fee silently into a single net `amount`
instead. That meant "fee_adjustment" matches were only ever a **percentage
tolerance guess** (0.9 confidence), even though the actual fee amount was
knowable. Fixed: settlement rows now carry explicit `fee`, `tax`, and `utr`
fields, and the matcher verifies the exact bookkeeping identity
`ledger_amount == settlement_amount + fee + tax` instead of guessing within
a tolerance band — a genuine identity check earns `confidence: 1.0`, not a
heuristic 0.9. The UTR also now flows into exception explanations ("check
your bank statement for that UTR") and Q&A answers, which is what a real
finance analyst would actually need to act on an exception.

One deliberate deviation from a fully faithful Razorpay schema: real
settlement amounts are integers in paise (smallest currency unit); this
project keeps rupee floats throughout. Converting the unit representation
touches nine source files and every test's expected values for a purely
cosmetic match, with no behavioral upside — the actual float-precision risk
that unit choice guards against was already checked directly (see the
"Known limitations" note below) and isn't live here. The fee/tax/UTR
separation was the part with real teeth, so that's what changed.

Also caught mid-fix: normalizing a settlement row's `fee`/`tax` from a
freshly-generated Python object works fine, but a row read back from
`settlement.csv` via `csv.DictReader` has every field as a **string** —
`"8.0" + 0.0` throws `TypeError`, not a silent bug, so this one surfaced
immediately on the first full-pipeline test run rather than needing to be
hunted for.

**6. Uploaded data silently fed the Cash Forecaster stale numbers.** After
building the "Upload data" tab, the Cash Forecaster kept showing the
*previous* dataset's forecast instead of the just-uploaded one — no error,
no crash, just a quietly wrong number. Cause: `agents/forecast_agent.py`
reads settlement data straight from `data/generated/settlement.csv`, and
the upload path only wrote to `reports/`. Fixed by having the upload path
also persist to `data/generated/` (and clear the stale `ground_truth.csv`
alongside it, so it can't be mistaken for real labels on real data). Caught
by checking the actual number shown after a real upload, not by assuming
the existing forecast code would "just work" against new data.

**7. A trained ML classifier scored a suspicious 100% — because the task
was too easy, then, after fixing that, an actually-mislabeled example
surfaced.** Full story in `ml/README.md`. Short version: random negative
sampling made every model (including plain logistic regression) trivially
separate the classes; switching to amount-closest hard negatives fixed
that, but then surfaced cases that were genuinely feature-identical to a
true match (duplicate-settlement clones, which are exact copies by
design) — labeling those "not a match" would have been a direct label
contradiction, not a hard example. Fixed by excluding them from the
negative pool rather than mislabeling them. The corrected model reaches
the deterministic matcher's own accuracy on held-out data, with feature
importances converging on the same signal (`gross_reconciles`, reference
similarity) the hand-written rules already use — a genuinely informative
result, not a number chased to look good.

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
- Amounts are rupee floats, not integer paise like Razorpay's real API —
  a float's precision is nowhere near this system's actual comparison
  tolerances (checked directly, not assumed), so this is a representation
  choice, not a live correctness bug.
- No authentication or role-based access control on the dashboard — anyone
  who can reach it sees and can trigger everything. Real reconciliation
  software (SOX-relevant) requires this; out of scope for a demo.
- Single currency only — no FX handling for multi-currency merchants.
- Batch-only: reconciliation runs on a static CSV snapshot, not a live
  webhook feed. The `utr` field is modeled specifically so this could
  extend to true 3-way reconciliation (ledger ↔ settlement ↔ bank
  statement) — that third leg isn't built.

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
  claim_verifier.py              checks a user's claim against the record
  langgraph_orchestrator.py        optional LLM tool-calling router
  action_ledger.py                   shared, bounded, gated audit trail
ml/                        standalone trained classifier -- see ml/README.md
  features.py               pairwise feature extraction
  dataset.py                  builds a labeled set from generate_data.py
  train.py                      trains + evaluates + saves model.skops
  predict.py                      inference helper, not wired into the app
  push_to_huggingface.py            pushes to your own HF Hub repo
  model.skops, MODEL_CARD.md          the trained artifact + its writeup
tests/                     121 pytest tests: unit-level across recon/, agents/,
                           and ml/, plus test_user_journey.py -- real subprocess
                           sessions that act as a user typing into cli.py / agent_cli.py
```

## Filling out the application form

- **Project name**: Ledger — a multi-agent AI Finance Controller
- **What it solves**: see "What it solves" above
- **Track**: AI Finance Controller
- **What broke, and how you got out**: see "What broke" above — both bugs
  are real and both were caught by actually running the thing, not by
  reading the code. Adapt to your own words, and add your own story once
  you've broken something yourself.
