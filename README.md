# Close-as-Code

**Month-end close that runs as reviewed pull requests, orchestrated by Agent Orchestrator (AO).**

Syndicate by Maximor hackathon, Track 2. Company: *Close-as-Code*.

Northwind Labs Inc. (a synthetic 25-person B2B SaaS) closes its books every month. Traditionally
a controller matches ~120 bank lines to bills by hand, books accruals and depreciation, reconciles
the payment processor, and signs off. Close-as-Code turns that into a pull-request workflow: the
general ledger is a plain-text [Beancount](https://beancount.github.io/) file in git, AO spawns one
agent worker per close task, deterministic code prepares and validates every entry, the model only
makes the judgment calls, and ten accounting controls run in CI on every PR. The controller reviews
diffs, approves or rejects the exceptions the agents could not resolve, and merges. The AO board is
the close dashboard.

> Status: MVP build. Final close metrics and screenshots are filled in after the recorded runtime
> close (see [Results](#results) — placeholders are marked).

---

## Why git, why a plain-text ledger

- **The ledger is a git repo.** Every journal entry is a line of text in a Beancount file. A change
  to the books is a diff you can read, comment on, and revert. `git blame` on a posting tells you
  who booked it, when, and — via entry metadata — why.
- **The close is a set of pull requests.** Each task (bank reconciliation, accruals, depreciation)
  is one branch and one PR. Review is `git diff`. Approval is a merge. The audit trail is the commit
  history — no separate audit log to trust, no ERP export to reconcile against.
- **Controls are CI.** Ten accounting controls run on every PR as a GitHub Actions check and post a
  results table as a PR comment. A book that does not balance, an entry dated before the period lock,
  or a posting over the materiality threshold without sign-off turns the check red. Nothing merges
  red.
- **Plain text is auditable and diffable.** No opaque binary database. A reviewer, a regulator, or a
  new controller reads the same file the tool writes. Balances are recomputed from the text, so the
  report can never drift from the ledger.

The result: ledger writes are always safe (code validates and runs `bean-check` before anything is
committed), and every model judgment is auditable (a Neatlogs trace id is recorded on every
exception).

---

## Architecture — the deterministic sandwich

```
controller ── "Run September close" ──▶ AO orchestrator (Claude Code, kind=orchestrator)
                                             │ spawns one worker per task, branch + worktree each
              ┌──────────────────────────────┼──────────────────────────────┐
              ▼                              ▼                              ▼
     worker close/bank-rec          worker close/accruals          worker close/depreciation
     closeops prepare  (code)       prepare                        prepare
     closeops decide   (packet → worker judges → validate)   ...     ...
     closeops apply    (code: validate, render, bean-check)
     commit → gh pr create
              │
              ▼
     GitHub PR ──▶ Actions: pytest + closeops check ──▶ PR comment (control table)
              │ green → controller reviews diff, merges (via AO)
              │ red   → AO routes comment to worker; C9-only failure → "Needs You"
              ▼        controller edits exceptions/*.yaml status → worker re-applies → green
     approved exceptions → data/rules/learned.yaml → closeops rerun bank-rec → run 2 metrics
```

**The sandwich:** code prepares candidates and evidence → the model makes judgment calls under a
contract that code enforces → code validates and renders. The model never writes to the ledger
directly and never invents amounts; it only *chooses* among candidates that code produced, and it
may *demote* a candidate to a human-reviewed exception. See [docs/architecture.md](docs/architecture.md).

---

## The four close steps

Each task follows one contract of four commands:

| Step | Command | What it does | Who |
|---|---|---|---|
| **prepare** | `closeops prepare <task>` | Reads the ledger and source data, emits ranked candidates with evidence ids to `work/<task>/candidates.json`. | code |
| **decide** | `closeops decide <task> --packet` → worker writes `decisions.json` → `closeops decide <task> --validate` | Renders a decision packet; the AO worker makes the calls; code validates them against the contract. | model, gated by code |
| **apply** | `closeops apply <task>` | Validates decisions, renders `ledger/2026-09/<task>.beancount` + `exceptions/<task>.yaml`, learns rules from approved exceptions, runs `bean-check`. | code |
| **check** | `closeops check` | Runs the ten controls; exit non-zero if any fail. | code |

**Decision contract** (enforced in `apply`, whatever `decide` said): per line
`{choice: <candidate_id>|"exception", rationale, confidence}`. Auto-post only if the chosen
candidate scored ≥ 0.9; anything else becomes an exception with the chosen candidate as its
`proposed_entry`. The model may demote a ≥ 0.9 candidate to an exception (duplicate, conflicting
description). It may never invent amounts and never auto-post to `Equity:Suspense`.

> `prepare` / `decide` / `apply` / `baseline` / `rerun` are delivered by the Wave 2 task workers
> (`bank-rec`, `decide-llm`, `period-entries`). Wave 1 ships `check`, `report`, and `status`.

---

## The ten controls

Every PR runs these in CI (`closeops check`). Full rationale in [docs/controls.md](docs/controls.md).

| # | Control | Fails when |
|---|---|---|
| C1 | Ledger parses and balances (`bean-check`, `errors == []`) | an unbalanced posting |
| C2 | Trial balance nets to zero at Sep 30 | it does not net |
| C3 | Period lock: no `ledger/2026-09/*` entry before `period_lock_before` | an entry dated 2026-08-31 |
| C4 | Every September entry has a non-empty `source` | a missing source |
| C5 | Any posting ≥ materiality has `approved-by` | 14,500 booked without approval |
| C6 | No duplicate (date, postings set, source) | a duplicated entry |
| C7 | Ledger bank balance Sep 30 == statement closing + outstanding cheques − deposits in transit | off by any amount |
| C8 | `Equity:Suspense` == 0 at Sep 30 | an unresolved unknown payee |
| C9 | No `status: open` in `exceptions/*.yaml` | one open exception |
| C10 | `Assets:Dodo:Balance` == Σ payments − Σ refunds − Σ paid-out gross | a payout dropped |

C9 is the human gate: while exceptions are open the PR stays red and lands in AO's "Needs You"
column. The controller approves/rejects each one; only then does the PR go green.

---

## Metrics and the funnel

`closeops report` writes `close-report.md` (the PR comment) and `metrics.json`. The headline is a
**four-tier funnel** that makes the model's contribution visible and honest:

1. **exact** — deterministic exact matches only (baseline).
2. **rules-only** — exact + recurring-payee matching rules.
3. **agent** — after the model's judgment: auto-posted lines, plus every remaining line raised as an
   exception *with a proposal*.
4. **after review** — once the controller approves/rejects, 100% of lines are resolved.

Plus `proposal_acceptance_rate` (how many agent proposals the controller accepted) and a **run 1 →
run 2** comparison: approved exceptions become matching rules in `data/rules/learned.yaml`, so
`closeops rerun bank-rec` auto-posts more the second time. This is the hackathon's stated goal —
reliability that improves over time.

Plan targets (not yet measured): exact ≈ 62% · rules-only ≈ 74% · agent ≈ 80% auto · after review
100% · run 2 ≈ 87%. Actual numbers are filled into [Results](#results) after the recorded close.

---

## Sponsor tools

- **Agent Orchestrator (AO) — the runtime.** AO is not just the build harness; at close time AO
  *is the product*. The controller types "Run September close" to an AO orchestrator, which spawns
  one worker per task on its own branch and worktree. CI comments route back to the owning worker;
  unresolved exceptions surface in AO's "Needs You" column. The AO Kanban board is the close
  dashboard. Build orchestration used the same mechanism (see [docs/prompts/](docs/prompts/)).
- **Neatlogs — tracing every judgment.** With `NEATLOGS_API_KEY` set, each close run appears at
  [app.neatlogs.com](https://app.neatlogs.com) as one session with per-step spans
  (`prepare → decide → apply → check`) and one span per control. Every exception's `trace:` field
  links to the trace for the judgment that raised it. No LLM call is needed — tracing is via
  `@neatlogs.span` decorators, and it is skipped entirely when the key is unset (free tier).
- **Dodo Payments — payout reconciliation source.** Northwind is a SaaS, so reconciling processor
  payouts is a real close task (trap T14, control C10). `scripts/fetch_dodo.py` pulls payouts,
  payments, and refunds. **This build uses `--fixture` (seeded local data) by default**; `--live`
  hits the Dodo test-mode API via the `dodopayments` SDK (`environment="test_mode"`, which moves no
  money) when `DODO_PAYMENTS_API_KEY` is set. The README states which mode produced the demo data:
  **fixture** unless the results section below says otherwise.

**No paid model API anywhere in the product.** Model reasoning happens only inside AO worker
sessions (Claude Code on the team subscription). The Python package never calls a paid model API;
`anthropic` is not a dependency.

---

## The close dashboard

`docs/dashboard.html` is a single self-contained page rendering the close package: the ten-control
register, the four-tier funnel, the exception register with the controller's decisions, and the
run 1 → run 2 improvement. It is **generated from the real artifacts**, never hand-written:

```bash
python scripts/build_dashboard.py          # reads metrics.json, exceptions/*.yaml, ledger/2026-09/
```

Open `docs/dashboard.html` in a browser, or see the hosted copy linked from the Devpost entry. The
AO board remains the operational surface during a close — this is the read-only close package a
controller or auditor receives afterwards.

## Setup

Requires Python 3.10+.

```bash
git clone https://github.com/PARIDHIPAWAIYA/closeops.git
cd closeops
python -m pip install -e ".[test,trace,dodo]"   # extras optional: test, trace (Neatlogs), dodo
```

Optional environment (local `.env`, never committed — see `.env.example`):

- `NEATLOGS_API_KEY` — enables tracing. Unset = tracing skipped, everything else works.
- `DODO_PAYMENTS_API_KEY` — enables `fetch_dodo.py --live` (test mode). Unset = fixtures.
- `AO_SESSION_ID` — recorded into `decisions.json` for attribution when run inside AO.

Regenerate the synthetic dataset (deterministic, seed 42):

```bash
python scripts/gen_data.py --seed 42
python scripts/verify_data.py     # prints trap counts
```

## Run the close

```bash
# Verify the books (the ten controls)
closeops check              # human-readable table; exit 1 if any control fails
closeops check --json       # machine-readable
closeops status             # one-screen controls summary

# One task, end to end (Wave 2 commands)
closeops prepare bank-rec
closeops decide bank-rec --packet      # writes work/bank-rec/packet.md
#   ... an AO worker reads the packet and writes work/bank-rec/decisions.json ...
closeops decide bank-rec --validate    # gates decisions against the contract
closeops apply bank-rec                # renders entries + exceptions, runs bean-check

# Reporting and reliability-over-time
closeops report            # writes close-report.md + metrics.json
closeops baseline bank-rec # exact + rules-only tiers
closeops rerun bank-rec    # run 2 after learned rules
```

Workers can also invoke `python -m closeops.cli <cmd>` when the entry point is not on PATH.

Validate the ledger directly (Windows-safe):

```bash
python -m beancount.scripts.check ledger/main.beancount
```

## Running the close through AO

1. Add the repo as an AO project; worker agent = Claude Code, base branch = `main`, setup command
   `pip install -e .[test,trace,dodo]`.
2. Spawn an orchestrator and paste [docs/prompts/orchestrator-close.md](docs/prompts/orchestrator-close.md).
3. It spawns three workers, each following its `docs/prompts/worker-<task>.md`, each opening a PR
   `close(2026-09): <task>`.
4. Review diffs, approve/reject exceptions in `exceptions/<task>.yaml`, merge from AO. See the
   human review loop in [docs/demo-script.md](docs/demo-script.md).

---

## Repository layout

```
closeops/          package: cli, ledger, models, controls, report, rules, tasks/{accruals,depreciation}
                   (Wave 2, planned: tasks/bank_rec, decide, trace, baseline)
data/              company.json, bank CSV + statement balance, AP invoices, fixed assets, Dodo fixtures, rules
ledger/            main.beancount (opening + August + booked September) and ledger/2026-09/<task>.beancount
exceptions/        <task>.yaml (human review queue) + bank-rec-reconciling.json (for C7)
scripts/           gen_data.py, fetch_dodo.py, verify_data.py
tests/             pytest suite + fixtures
docs/              architecture.md, controls.md, demo-script.md, prompts/
.github/workflows/ controls.yml (pytest + closeops check + PR comment)
```

See `plan.md` for the full build plan and `CONTEXT.md` for the running work log.

---

## Results

The September 2026 close was run end to end through AO on 6 Sep 2026. All numbers below come from
`metrics.json` and `close-report.md` on `main`, regenerated by `closeops report`.

### The close

| | |
|---|---|
| Bank statement lines | 116 |
| Auto-posted by the agent | 94 |
| Exceptions raised for the controller | 22 (bank-rec) + 1 (accruals) = 23 |
| Reconciling items (not entries) | 4 — 3 outstanding cheques, 1 deposit in transit |
| Accruals booked | 5 (17,850.00); 1 October-service bill correctly refused |
| Depreciation booked | 3 entries, 1,087.78; FA-004 flagged fully depreciated |
| **Controls after review** | **10 / 10 green** |
| Exceptions at close | 0 open, 23 approved, 0 rejected |

### The funnel — what the agent actually adds

| Tier | Auto-rate | What it is |
|---|---|---|
| Exact baseline | 60.3% (70/116) | amount match within ±5 days, nothing else |
| Rules only | 79.3% (92/116) | + deterministic payee rules, splits, payouts |
| Agent | 81.0% (94/116) | + the worker's judgment under the decision contract |
| After review | 100% (116/116) | + the controller's 23 approvals |

The agent's own contribution is the 79.3% → 81.0% step **plus** the fact that the other 19% arrive
as proposed entries with evidence and a confidence, not as a list of unmatched lines. Two of those
were demotions the agent made against its own deterministic top candidate: a duplicate ZOOM charge
and a same-amount two-vendor collision.

### Improvement over time

| | Auto-rate |
|---|---|
| Run 1 | 81.0% (94/116) |
| Run 2, after learning from approved exceptions | 83.6% (97/116) |

Two rules were learned from the controller's decisions: `SHENZHEN → Expenses:Office` (from BR-015)
and `LAGOS → Expenses:Travel` (from BR-017) — the two unknown payees the human identified. Rule
learning is deliberately conservative: it learns only from approved unknown-payee exceptions with a
simple two-posting entry, never from splits, partials, FX, payouts or duplicates, and material items
stay exceptions forever.

### The human-in-the-loop moment

The bank-rec PR (#9) went **red on C9 with 22 open exceptions** and stopped. The controller approved
all 22 and reclassified four of them off the agent's proposal (three distinct decisions):

- **BR-014** duplicate ZOOM charge → `Assets:AR` (refund receivable), not a second software expense
- **BR-015 / BR-016** Shenzhen POS → `Expenses:Office`
- **BR-017** Lagos ATM → `Expenses:Travel`

Re-applying turned the same PR **green at 10/10**. Blind-approving every exception as proposed would
have left `Equity:Suspense` at 2,850 and failed C8 — the human decision was load-bearing, not a
rubber stamp.

### Sponsor tools

- **AO** built the project (7 PRs, one worker each, AO's own reviewer on every PR) and ran the close
  (3 close PRs). See `docs/AO-LOG.md`.
- **Neatlogs** traced every close step. All 94 booked bank-rec entries and all 22 bank-rec
  exceptions carry a real Neatlogs trace id (e.g. `neatlogs:7853ef917eac793eb6376cc1283d467f`),
  so any journal entry can be traced back to the decide run that produced it. The single
  accruals exception has an empty `trace` field: accruals renders a zero-line packet, so
  provenance had nothing to copy from — a known gap, not a claim we make.
- **Dodo Payments** — payout reconciliation ran on **fixture** data in the shape of Dodo's
  test-mode API (`scripts/fetch_dodo.py --fixture`); `--live` uses the `dodopayments` SDK against
  `test_mode`. Both payouts reconciled, C10 green.
