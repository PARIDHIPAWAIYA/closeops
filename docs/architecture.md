# Architecture — the deterministic sandwich

Close-as-Code runs a month-end close as pull requests over a plain-text ledger. This document
explains the runtime flow, the "deterministic sandwich" that keeps ledger writes safe while letting
a model make judgment calls, and how the pieces fit together. It corresponds to plan.md §2.

## The flow

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

## The deterministic sandwich

The core design principle: **code on the outside, model in the middle, under a contract code
enforces.**

```
   ┌─────────────────────────────────────────────────────────────┐
   │  prepare (code)                                               │
   │    read ledger + source data → ranked candidates + evidence  │
   └───────────────────────────┬─────────────────────────────────┘
                               ▼
   ┌─────────────────────────────────────────────────────────────┐
   │  decide (model, gated by code)                               │
   │    packet renders candidates → worker chooses per line       │
   │    validate: schema + contract, or apply refuses to run      │
   └───────────────────────────┬─────────────────────────────────┘
                               ▼
   ┌─────────────────────────────────────────────────────────────┐
   │  apply (code)                                                 │
   │    re-check contract → render Beancount → bean-check → learn  │
   └─────────────────────────────────────────────────────────────┘
```

**Bottom slice — `prepare` (deterministic).** Code reads the ledger and the source data (bank CSV,
AP invoices, fixed-asset schedule, Dodo payout records) and produces, for each item, a ranked list
of candidate entries. Every candidate carries a score and evidence ids (which bank line, which bill,
which payout record). Nothing is written to the ledger. This is pure code and fully tested.

**Filling — `decide` (the only place a model acts).** `closeops decide <task> --packet` renders the
candidates as a compact decision packet: the contract, the chart of accounts, the rules, and every
line with its ranked candidates and evidence. An AO worker (Claude Code on the team subscription —
no paid API) reads the packet and writes `work/<task>/decisions.json`: one choice per line, a
one-sentence rationale citing evidence ids, and a confidence. `closeops decide <task> --validate`
then checks that JSON against the schema and the contract. If it fails, it exits non-zero with a
readable list of violations and `apply` refuses to run.

**Top slice — `apply` (deterministic).** Code re-checks the contract (regardless of what `decide`
said), renders the chosen entries into `ledger/2026-09/<task>.beancount` with metadata, writes any
exceptions to `exceptions/<task>.yaml`, learns rules from approved exceptions, and runs `bean-check`.
If `bean-check` fails, `apply` fails.

### The decision contract

Enforced in `apply`, whatever `decide` produced:

- Per line: `{choice: <candidate_id> | "exception", rationale, confidence}`.
- **Auto-post only if the chosen candidate scored ≥ 0.9.** Anything below becomes an exception with
  the chosen candidate as its `proposed_entry`.
- The model may **demote** a ≥ 0.9 candidate to an exception (e.g. a suspected duplicate, or a
  description that contradicts the top match).
- **Never invent amounts** — a posting must equal its candidate's postings.
- **Never auto-post to `Equity:Suspense`** — unknown payees go to the human queue.

Because the contract is re-enforced by code at `apply` time, a model that misbehaves cannot corrupt
the ledger; the worst it can do is raise something to human review that could have been automated, or
be rejected by `--validate`.

## Why this shape

- **Ledger writes are always safe.** Amounts and balancing come from deterministic code and are
  verified by `bean-check` before commit. The model chooses among code-produced candidates; it does
  not author postings freehand.
- **Reasoning is auditable.** Every exception records who decided it (`closeops-decide`, `worker`, or
  `human`) and a Neatlogs `trace:` id, so any judgment can be traced back to its inputs.
- **Zero model spend.** Reasoning happens inside AO workers on the team subscription. The Python
  package never calls a paid model API.

## Components

| Module | Responsibility |
|---|---|
| `closeops/cli.py` | `prepare · decide · apply · check · report · baseline · rerun · status` |
| `closeops/ledger.py` | Load Beancount, balances by account/date, open items, render entries, `bean-check` |
| `closeops/models.py` | `StatementLine · Invoice · Asset · Payout · Candidate · Decision · Exception · ControlResult` (Decimal money) |
| `closeops/tasks/` | `bank_rec · accruals · depreciation` — the `prepare` logic per task |
| `closeops/decide.py` | Packet renderer + `decisions.json` validator |
| `closeops/trace.py` | Neatlogs init + `@span` decorators on each step and control |
| `closeops/controls.py` | C1–C10 |
| `closeops/report.py` | `close-report.md` + `metrics.json` |
| `closeops/baseline.py` | Exact-match and rules-only funnel tiers |
| `closeops/rules.py` | Load matching + learned rules; learn from approved exceptions |

## Money and dates

- **Decimal everywhere; never float for money.** All amounts are `decimal.Decimal`.
- Beancount balance assertions apply at the *start* of a date, so the September 30 close is asserted
  on `2026-10-01`. Balances are computed by summing posting amounts for transactions dated on or
  before the as-of date.
- `bean-check` is invoked as `python -m beancount.scripts.check <file>` for Windows compatibility.

## Data and the traps

The synthetic dataset (`scripts/gen_data.py --seed 42`) is built to exercise every branch of the
close. The bank statement contains fifteen categories of "trap" (T1–T15) — exact matches, recurring
payees, splits, partials, FX/rounding, duplicates, unknown payees, discounts, outstanding cheques,
deposits in transit, cross-period payments, Dodo payouts, and same-amount ambiguity — with expected
outcomes that double as the bank-rec test plan. See plan.md §4 for the full table. Targets: ~95
auto-posted, ~20 exceptions, 4 reconciling items.

## Tracing (Neatlogs)

When `NEATLOGS_API_KEY` is set, `closeops/trace.py` calls `neatlogs.init(...)` once and each step
(`prepare`, `decide`, `apply`, `check`) and each control is wrapped in a `@neatlogs.span`. A full
close then appears as a single Neatlogs session with per-step spans, candidate/decision counts, and
control outcomes. The current span's trace id is read via OpenTelemetry
(`trace.get_current_span().get_span_context()`) and recorded into `decisions.json` and each
exception's `trace:`. When the key is unset, tracing is a no-op and the close runs unchanged.
