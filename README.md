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
demand, money that should have hit the bank needs confirming, tax filed
by a vendor needs checking against what your own books show, and a
customer or merchant's claim about a payment needs checking against
reality rather than taken on faith. Seven agents split that work:

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
- **Bank Reconciliation Agent** — the third reconciliation leg: checks
  settlement records against the actual bank statement by UTR, correctly
  handling batched settlements (many payouts landing in one bank credit)
  instead of flagging every one as a false mismatch.
- **Tax Reconciliation Agent** — the fourth leg: checks GST recorded on
  gateway fees against a vendor's periodic tax filing, period by period,
  and flags a cross-period cutoff shift as plausible rather than assuming
  the worse explanation.

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
     ┌───────────────┬───────────┼───────────┬───────────────┬────────────────┬────────────────┐
     ▼               ▼           ▼           ▼               ▼                ▼                ▼
Reconciliation   Settlement   Cash        Exception &     Claim            Bank             Tax
Agent            Q&A Agent   Forecaster   Anomaly Agent   Verification     Reconciliation   Reconciliation
(recon/*)        (agents/    (agents/     (agents/        Agent            Agent            Agent
                 qa_agent)   forecast_    exception_      (agents/         (agents/         (agents/
                             agent)       agent)          claim_verifier)  bank_reconcil-   tax_agent,
                                                                            iation_agent,    recon/
                                                                            recon/           tax_matcher)
                                                                            bank_matcher)
     │               │           │           │               │                │                │
     └───────────────┴───────────┴───────────┴───────────────┴────────────────┴────────────────┘
                                  ▼
                    Shared Action Ledger (agents/action_ledger.py)
                    every action logged; amount ≥ Rs.5,000, confidence
                    < 0.8, or a contradicted claim always gets flagged
                    needs_human_approval — explainable, bounded, gated
```

The Reconciliation Agent's own output (`reports/exceptions.csv`,
`summary.json`, `matches.csv`) is the shared substrate the other agents
read from — the Cash Forecaster's "at risk" figure and drift warning, and
the Claim Verification Agent's factual check, all come directly from the
Reconciliation Agent's own records, not a separate estimate. The Bank and
Tax Reconciliation agents are the exception: they read `settlement.csv`
plus their own third/fourth data source (`bank_statement.csv`,
`tax_filing.csv`) directly, since ledger-vs-settlement matching has
nothing to say about whether money actually landed in the bank or was
filed correctly for tax.

### Multi-source reconciliation: the third and fourth legs

The original build only reconciled ledger ↔ settlement — a real gap
against the track's own "Multi-source reconciliation" example direction,
which implies more than two sources. Two more legs were added, each
shaped by a specific researched failure mode rather than a naive 1:1
diff:

**Bank reconciliation** (`recon/bank_matcher.py`) matches settlement
records against an actual bank statement by UTR — but real payment
gateways batch multiple settlement payouts into a single bank credit
(e.g. Razorpay's daily/weekly settlement cycles), so a naive
one-settlement-per-bank-row check would flag every batched settlement as
a false "amount mismatch." The matcher groups settlement rows by UTR
first and compares the *sum* against the bank credit, correctly
recognizing an N-to-1 batch as reconciled instead of N false exceptions.
It also distinguishes "not arrived yet" (`bank_credit_pending`) from "no
settlement explains this money" (`unrecognized_bank_credit`) — different
problems that need different follow-up, not one generic "mismatch."

**Tax reconciliation** (`recon/tax_matcher.py`) checks GST recorded on
gateway fees against a vendor's periodic tax filing — modeled on India's
real GSTR-2A/2B mechanism, where Input Tax Credit must be claimed against
a *frozen monthly snapshot* (2B), not a live running total (2A). That
period-level framing has a real, stated limit: a transaction that settles
near month-end can have its GST reported by the vendor in the *next*
period's filing (a cross-period cutoff shift), and from aggregate
period totals alone that looks identical to a genuinely missing credit.
The matcher doesn't pretend to resolve that ambiguity from data it
doesn't have — it flags the mismatch, states both plausible causes, and
says invoice-level detail is what's actually needed to tell them apart,
rather than overclaiming a root cause the period-level data can't prove.

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
`agents/langgraph_orchestrator.py`: the same seven agents wrapped as
LangChain tools (plus three approval-workflow tools wrapping
`action_ledger` directly -- `pending_approvals`, `approve_entry`,
`reject_entry`), with an LLM (Claude Haiku, via `langchain.agents.
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

### Closing gaps found against Cointab (a real competitor)

A competitive scan of [Cointab](https://www.cointab.net/) — a reconciliation
SaaS with a mature no-code rule engine, pre-built vertical templates, and
SFTP/API/email data automation — surfaced four features this project
didn't have, closed here:

- **Net/contra settlement matching** (`recon/matcher.py`, pass 3). Cointab
  explicitly supports "contra and net matching" for refunds, reversals, and
  split payouts; this project's matcher previously only matched a single
  settlement leg per ledger row. Now it sums 2+ settlement legs sharing a
  reference and checks whether the sum (or gross-adjusted sum) reconciles
  against the ledger row — covering both a refund netting against its
  original payout and a legitimate multi-leg partial payout, both as a
  verified identity (`confidence: 1.0`), not a guess. Demoable via
  `python cli.py demo` directly (no `--corrupt` flag needed) — look for
  `category: net_settlement` in `reports/matches.csv`.
- **Configurable match tolerance.** Cointab's pitch is a no-code rule
  engine business users configure themselves, versus this project's
  previously-hardcoded 2% fuzzy-match tolerance. `recon/matcher.py::match`
  now takes an optional `amount_tolerance_pct`, threaded through
  `pipeline.run_uploaded` and exposed as an optional `tolerance_pct` field
  on `backend/main.py`'s `/upload` endpoint (and a matching input in the
  chat UI's upload panel) — a genuine per-client override, not just
  internal plumbing nobody can reach.
- **An approval workflow** (`agents/action_ledger.py::approve`/`reject`/
  `pending_approvals`). Cointab has multi-level approvals as a stated
  governance feature; this project had confidence/amount gating
  (`needs_human_approval`) but nothing to actually resolve a flagged entry.
  Approving or rejecting never edits the original entry — it appends a new
  one referencing it by `id`, because a real audit log has to stay
  append-only or "what did it say at the time" stops being answerable.
  Reachable from chat: `pending approvals`, `approve #3`, `reject #3:
  reason`.
- **A safe derived-column formula evaluator** (`recon/formula.py`).
  Cointab's "AI formula builder" generates Excel-style formulas from a
  natural-language ask via an LLM. This evaluates a formula
  deterministically instead — `+`, `-`, `*`, `/` over a fixed field
  whitelist, built on Python's `ast` module rather than `eval()` (running
  an attacker-supplied string through `eval()` is a code-execution
  vulnerability, not a formula feature — verified directly with a
  `__import__('os').system(...)` test case that's rejected, not executed).
  Reachable from chat: `compute ledger_amount - fee - tax for
  RZP123456789`.

What's deliberately still not built, and why: a no-code rule-configuration
*UI* (the tolerance override above is a real parameter, not a business-user
-facing rule builder), SFTP/email/DB-connector data automation (needs real
external infrastructure this project can't stand up and verify), and
Cointab's 20 pre-built vertical templates (school fees, real-money gaming,
travel, etc.) — those are thin wrappers around the same matching engine
with different column names, not a capability gap worth cloning one by one.
See "Known limitations" below for the complete list.

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

### Chat UI: a multi-client product, not a single shared dashboard

`app.py` (Streamlit) is one shared dashboard for one operator. `backend/`
+ `frontend/` is a different shape entirely: a ChatGPT-style chat where
each browser session is its own isolated client — upload your own CSVs
(or click "Try synthetic demo data"), chat with the same seven agents,
and download your own result files, all without ever seeing or touching
another session's data or reports.

```bash
pip install -r requirements.txt                            # adds fastapi/uvicorn
uvicorn backend.main:app --port 8000     # terminal 1: the session API
cd frontend && npm install && npm run dev    # terminal 2: the chat UI, http://localhost:3000
```

Isolation is real, not cosmetic: every `recon/pipeline.py` function and
every `agents/*.py` entry point takes optional `data_dir`/`reports_dir`/
`ledger_path` parameters (defaulting to the shared paths `cli.py`/`app.py`
already used, so nothing else changed behavior). `backend/main.py` hands
each session its own `data/sessions/{id}` and `reports/sessions/{id}`
pair — verified directly by running two concurrent sessions (one loading
demo data, one uploading a 1-row CSV) and confirming neither's chat
answers ever reflected the other's numbers, not just assumed from the
parameter threading being correct.

Session state itself (the id → directory mapping) is an in-memory dict —
correct for a single-process demo, honestly not a persistence layer: a
server restart forgets every session, and it can't be horizontally scaled
without moving that registry to shared storage first.

**Reconciliation report view.** Loading demo data, uploading a CSV, or
sending "run reconciliation" in chat doesn't just return a text summary
-- it also renders a Cointab-style report inline: four summary cards
(Total / Fully matched / Partially matched / Unmatched, each with a
ledger total, a settlement total, and the difference between them),
tabbed match tables, and side-by-side Ledger/Settlement tables for the
unmatched rows. `recon/report.py::build_report` computes this from the
same `matches.csv`/`exceptions.csv` every other agent already reads --
"fully matched" is deliberately narrow (only the `exact` category; a fee
deduction, timing shift, corrected reference, or netted refund/split
settlement all count as "partially matched" since they required some
variance to reconcile), and it correctly dedupes a `net_settlement`
match's ledger side so a 2-leg split payout isn't counted as two ledger
rows. The frontend's theme is a light teal/white palette to match, not
the ChatGPT-style dark chat bubbles from the first version.

Try in `agent_cli.py`:

```
> run reconciliation
> what's our match rate
> why didn't RZP123456789 settle        (use a real ref from reports/matches.csv)
> cash forecast for 14 days
> show duplicate exceptions
> triage exceptions
> verify claim: I never received my payout for RZP123456789
> bank reconciliation status
> tax reconciliation
> compute ledger_amount - fee - tax for RZP123456789   (use a real fee_adjustment ref)
> pending approvals
> approve #3: confirmed against bank statement
```

## Commands

| Command | What it does |
|---|---|
| `python cli.py demo` | generate data + run the reconciliation pipeline + print summary |
| `python cli.py generate --corrupt currency` | regenerate data with an injected batch-level anomaly |
| `python cli.py run` | re-run the pipeline against already-generated data |
| `python agent_cli.py` | interactive terminal chat across all seven agents |
| `streamlit run app.py` | dashboard: metrics, exception explorer, cash forecast chart, agent chat box, claim verification tab |
| `uvicorn backend.main:app --port 8000` | session API behind the chat UI -- one isolated data/reports directory pair per client |
| `cd frontend && npm run dev` | ChatGPT-style chat UI: upload CSVs or load demo data, chat, download your own result files |
| `python -m pytest` | 180 tests: unit tests across the matcher/scorer/agents, plus end-to-end user-journey tests that spawn the real CLI as subprocesses |

## Honest numbers, not a demo trick

`python cli.py demo` prints something like:

```
Ledger rows:      147
Settlement rows:  149
Matched pairs:    140
Exceptions:       18
Match rate:       95.2%
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
  net_settlement                 4/4    (100.0%)
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

**8. The bank/tax router had the mirror-image bug of #2.** Adding
`BANK_PATTERN`/`TAX_PATTERN` for the new agents, `RECONCILE_PATTERN`
(`reconcil\w*`) — checked first in `handle()` — silently intercepted them,
because "reconciliation" *contains* "reconcil" as a substring. So typing
"bank reconciliation status" or "show me the tax reconciliation" ran the
full ledger-vs-settlement pipeline and returned its generic summary
instead of ever reaching the bank/tax agents. Bug #2 was "reconcile isn't
a substring of reconciliation, so a specific match under-fires"; this one
is the opposite — "reconcil *is* a substring, so a broad match over-fires"
— caught the same way, by actually calling `handle()` with the exact
phrases a user would type rather than trusting that non-overlapping-
looking regexes don't overlap. Fixed by checking the more specific
bank/tax patterns before the generic reconcile pattern.

**9. Multi-client isolation was verified, not assumed, before shipping.**
Threading `data_dir`/`reports_dir`/`ledger_path` through nine files (all
of `recon/pipeline.py` and every `agents/*.py` entry point) is exactly
the kind of change that looks obviously correct and silently isn't —
one missed default, one function that still reads its own module-level
constant instead of the passed-in path, and two clients silently share
data. Verified directly: two concurrent sessions against the running
FastAPI backend, one loading a 145-row synthetic demo batch, one
uploading a 1-row CSV, each asked "what is the match rate" before and
after the other's action. The demo session's answer never changed after
the 1-row upload, and the 1-row session started with an honest "no report
found yet" rather than inheriting the demo session's numbers.

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
- No authentication or role-based access control on the dashboard or chat
  UI — anyone who can reach it (or guess a session id) sees and can
  trigger everything for that session. Real reconciliation software
  (SOX-relevant) requires this; out of scope for a demo. This includes the
  approval workflow specifically: `approve #<id>`/`reject #<id>` always
  logs the reviewer as the literal string `"chat_operator"` — there's no
  real identity behind it, so the audit trail records *that* something was
  approved and *when*, but not genuinely *by whom*. A real deployment
  needs actual reviewer identity before that log means anything for
  compliance.
- Single currency only — no FX handling for multi-currency merchants.
- Batch-only: reconciliation runs on a static CSV snapshot, not a live
  webhook feed.
- The tax matcher's period-level comparison genuinely cannot distinguish
  a cross-period filing shift from a truly missing credit using only
  aggregate period totals — stated as a real limit in its own docstring
  rather than a diagnosis the data doesn't support (see "Multi-source
  reconciliation" above).
- `backend/main.py`'s session registry is an in-memory dict, not a
  database — sessions (and their uploaded data) don't survive a server
  restart, and the process can't be horizontally scaled as-is.

## Project layout

```
cli.py                    reconciliation-only entry point
agent_cli.py               multi-agent terminal chat entry point
app.py                     Streamlit dashboard + agent chat box
backend/
  main.py                  FastAPI session API behind frontend/ -- per-client
                           data_dir/reports_dir isolation, upload/chat/download
frontend/                  Next.js chat UI: upload CSVs or load demo data,
                           chat with all seven agents, download result files
  app/report-view.tsx      Cointab-style Total/Fully/Partially/Unmatched
                           report cards + tabs, rendered inline in chat
recon/
  generate_data.py         synthetic ledger + settlement + ground truth
                           (+ bank statement + tax filing, seeded scenarios)
  matcher.py                5-pass matching engine (now incl. net/contra
                           settlement) + batch-drift detector, configurable
                           amount_tolerance_pct
  bank_matcher.py             settlement vs bank statement, UTR + batch-aware
  tax_matcher.py                 settlement tax vs periodic tax filing
  formula.py                       safe derived-column formula evaluator
                                   (ast-based, no eval())
  report.py                          buckets matches/exceptions into the
                                     Total/Fully/Partially/Unmatched report
  explainer.py                         LLM / template exception explanations
  scorer.py                              accuracy scoring against ground truth
  pipeline.py                              orchestrates the above, writes reports/
agents/
  orchestrator.py           routes a message to the right specialist
  qa_agent.py                 grounded settlement Q&A + compute <formula>
  forecast_agent.py            cash forecast + at-risk amount
  exception_agent.py            exception triage / prioritization
  claim_verifier.py              checks a user's claim against the record
  bank_reconciliation_agent.py    bank_matcher.py results, in plain English
  tax_agent.py                      tax_matcher.py results, in plain English
  langgraph_orchestrator.py          optional LLM tool-calling router
  action_ledger.py                     shared, bounded, gated audit trail --
                                       approve()/reject()/pending_approvals()
ml/                        standalone trained classifier -- see ml/README.md
  features.py               pairwise feature extraction
  dataset.py                  builds a labeled set from generate_data.py
  train.py                      trains + evaluates + saves model.skops
  predict.py                      inference helper, not wired into the app
  push_to_huggingface.py            pushes to your own HF Hub repo
  model.skops, MODEL_CARD.md          the trained artifact + its writeup
tests/                     180 pytest tests: unit-level across recon/, agents/,
                           and ml/, plus test_user_journey.py -- real subprocess
                           sessions that act as a user typing into cli.py / agent_cli.py

