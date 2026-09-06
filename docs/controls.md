# Controls — C1 through C10

`closeops check` runs ten accounting controls against the ledger and the close artifacts. They run
locally, and in CI on every pull request, where the results are posted as a PR comment. If any
control fails, `check` exits non-zero and the CI check goes red — nothing merges red. This document
gives each control and why it exists; it corresponds to plan.md §8.

The controls encode what a controller (and an auditor) actually check at close: the books balance,
nothing was booked before the period was locked, every entry is evidenced, material items are signed
off, nothing is duplicated, cash ties to the bank statement, no plug is left in suspense, no
exception is left open, and the payment processor's clearing account nets to zero.

## The table

| # | Control | Fails when |
|---|---|---|
| C1 | Ledger parses and balances (`bean-check`, `errors == []`) | an unbalanced posting or a parse error |
| C2 | Trial balance nets to zero at Sep 30 | debits and credits do not net to zero |
| C3 | Period lock: no `ledger/2026-09/*` entry dated before `period_lock_before` | an entry dated e.g. 2026-08-31 |
| C4 | Every September entry has a non-empty `source` | an entry with no `source` metadata |
| C5 | Any posting ≥ materiality has `approved-by` | a 14,500 posting booked without approval |
| C6 | No duplicate `(date, postings set, source)` | the same entry appears twice |
| C7 | Ledger bank balance Sep 30 == statement closing + outstanding cheques − deposits in transit | cash is off by any amount |
| C8 | `Equity:Suspense` == 0 at Sep 30 | an unknown payee was plugged to suspense |
| C9 | No `status: open` in `exceptions/*.yaml` | one exception is still open |
| C10 | `Assets:Dodo:Balance` == Σ payments − Σ refunds − Σ paid-out gross | a payout was dropped or mis-booked |

Materiality, the bank account, the suspense account, the processor clearing account, and
`period_lock_before` all come from `data/company.json` (Northwind: materiality 10,000.00, lock
before 2026-09-01).

## Rationale, one by one

**C1 — Ledger parses and balances.** The foundation. The ledger is loaded with Beancount and must
return zero errors; `bean-check` is run as `python -m beancount.scripts.check` (Windows-safe). If a
posting does not balance, or a file does not parse, nothing else can be trusted. Every `apply` runs
`bean-check` before committing, so this should already be green by the time CI runs — C1 is the
backstop.

**C2 — Trial balance nets to zero.** Double-entry means the sum of all postings across all accounts
is zero at the period end. Computed by summing posting amounts for transactions dated on or before
Sep 30. Catches a whole class of rendering or arithmetic mistakes that C1 alone would miss.

**C3 — Period lock.** August is closed. No entry filed under the September close
(`ledger/2026-09/*`) may be dated before `period_lock_before` (2026-09-01). This stops a close task
from silently reaching back into a locked prior period — the accounting equivalent of editing signed
books.

**C4 — Every entry is evidenced.** Each September entry must carry a non-empty `source` metadata
field pointing at where it came from (e.g. `data/bank/sep-2026.csv#L41`). No source, no entry. This
is what makes the ledger auditable: every posting traces back to a document.

**C5 — Materiality sign-off.** Any single posting at or above the materiality threshold (10,000)
must carry an `approved-by` field. The 14,500 legal retainer accrual is the planted case: it cannot
be auto-posted; it must go through human approval, which stamps `approved-by`. This enforces the
human gate on the entries that matter most.

**C6 — No duplicates.** No two entries may share the same `(date, set of postings, source)`. The
dataset plants a duplicate charge (two identical ZOOM −499 on the same day, trap T8); the first is a
real transaction, the second must be caught. C6 guarantees a mis-applied decision cannot book the
same thing twice.

**C7 — Bank reconciliation.** The classic tie-out. The ledger's bank balance at Sep 30 must equal
the statement closing balance, adjusted for timing: **+ outstanding cheques − deposits in transit**.
Those reconciling items are not journal entries; they live in `exceptions/bank-rec-reconciling.json`
(written by bank-rec) so C7 can add them back. Before bank-rec has run, C7 is expected to fail —
September's bank lines are not yet posted and the reconciling file does not exist.

**C8 — Suspense is zero.** `Equity:Suspense` must be exactly zero at Sep 30. Suspense is the plug
account for "we don't know yet"; a non-zero balance means an unknown payee (trap T9, `POS 4471
SHENZHEN`) was auto-posted instead of raised for a human. The decision contract forbids auto-posting
to suspense, and C8 verifies it held.

**C9 — No open exceptions.** No exception in `exceptions/*.yaml` may have `status: open`. This is the
**human gate**: while any exception is open the PR stays red and lands in AO's "Needs You" column.
The controller approves or rejects each one (setting `status: approved` / `rejected` with a note);
only then does C9 — and the PR — go green. A C9-only failure is the normal, expected state of a
freshly opened bank-rec PR, not a bug.

**C10 — Dodo processor clearing.** `Assets:Dodo:Balance` (the payment-processor clearing account)
must net to zero: **Σ payments − Σ refunds − Σ paid-out gross**, where a payout's gross =
`payout.amount + payout.fee`. Money flows in as payments, out as refunds, and out again as payouts
to the bank; if every payout is booked, the clearing account returns to zero. A dropped or
mis-booked payout leaves a residual. This is the SaaS-specific control that ties the processor to
the ledger. Before bank-rec posts the `DODO PAYOUT` lines (traps T14), C10 is expected to fail.

> **Open item (flagged in CONTEXT.md):** trap T14's second payout (`po_002`) has its fee omitted
> from the payout record on purpose. Whether Dodo nets to exactly zero or to a small residual
> depends on how bank-rec books that missing fee (proposed to `Expenses:PaymentProcessing`). C10
> currently uses the plan's literal formula; the exact expectation is confirmed once bank-rec lands.

## Behavior when data is missing

The controls are defensive: `run_all(repo_root)` wires each control to the repo's files, and when
required data is absent a control returns a **failing** result rather than crashing. This means
C2–C10 fail cleanly on an incomplete checkout instead of raising. Consequently, before the Wave 2
task workers have posted their entries, `closeops check` on the real ledger shows **8/10** — C7 and
C10 fail by design and reconcile once bank-rec posts September's bank lines and the Dodo payouts.

## Where they run

- **Locally:** `closeops check` (table) or `closeops check --json` (machine-readable);
  `closeops status` for a one-screen summary.
- **CI:** `.github/workflows/controls.yml` runs `pytest -q`, then `closeops check --json`
  (capturing the exit code with `continue-on-error`), writes `close-report.md`, posts it as a PR
  comment with `gh pr comment`, and fails the job if any control failed. No secrets are needed —
  the `decide` tests use a fixture, not a live model.
