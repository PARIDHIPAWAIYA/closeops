# CONTEXT

Running log. Newest entry first. Keep it short: what is done, what is next, decisions.

## Sun 6 Sep — Wave 2: docs (branch build/docs)
- Expanded `README.md` from the 2-line stub: setup, the prepare/decide/apply/check
  flow, architecture summary (deterministic sandwich), the ten controls, the
  four-tier funnel, sponsor tools (AO as runtime, Neatlogs traces, Dodo
  fixture-by-default with live test-mode noted), a "why git / why plain-text
  ledger" section, and a Results section left as clearly-marked placeholders (the
  runtime close has not happened yet — no fabricated metrics).
- Added `docs/architecture.md` (plan §2: the sandwich, component table, money/date
  rules, tracing) and `docs/controls.md` (C1–C10 table + per-control rationale,
  including the C7/C10 pre-bank-rec 8/10 note and the T14 po_002 fee open item from
  CONTEXT).
- Added `docs/demo-script.md` (plan §11 shot list + human review loop + a
  pre-record checklist) with the Devpost outline (plan §12) appended.
- `docs/prompts/{orchestrator-build,orchestrator-close,worker-bank-rec,
  worker-accruals,worker-depreciation}.md` already existed on main and match plan
  §10.1/§10.2/§10.3 verbatim — verified, left unchanged.
- Scope: docs only; no code/tests/scripts touched. Metrics left as placeholders.
- Next: open PR `build: docs`, address CI comments.

## Sun 6 Sep — period-entries (Wave 2: accruals + depreciation)
- Branch `build/period-entries` off main. TDD: tests first, then impl.
- `closeops/tasks/accruals.py` (plan 6.2): `prepare` selects `booked:false` bills
  with `service_period == 2026-09`, Dr expense / Cr Liabilities:Accrued:Expenses
  dated 2026-09-30; Oct-service bills listed "do not accrue"; amounts >= materiality
  flagged `needs_approval`. `apply` auto-posts the 5 non-material bills (17,850.00),
  routes the 14,500 legal retainer (INV-001) to `exceptions/accruals.yaml` as one
  OPEN exception (exercises C5 + C9). Approval round-trip: set an exception
  `status: approved` and re-apply → the 14,500 books with an `approved-by` meta so
  C5 stays green. bean-check runs on every apply.
- `closeops/tasks/depreciation.py` (plan 6.3): straight-line (cost−salvage)/life,
  half-month when placed in service during the period, zero+flag once fully
  depreciated; prior accumulated read from ledger via per-asset `asset:` meta.
  Hand-computed Sep: FA-001 777.78 (full), FA-002 160.00 (full), FA-003 150.00
  (half, in service 09-20), FA-004 0.00 (fully depreciated → flagged). Total
  1,087.78. `apply` writes one entry per booked asset with `asset:` meta.
- `closeops/cli.py`: added `prepare <task>` / `apply <task>` with a `TASKS`
  registry (accruals, depreciation) — kept alphabetical/minimal so bank-rec and
  decide workers can append without conflict. check/report/status untouched.
- Tests: `tests/test_accruals.py` (8), `tests/test_depreciation.py` (9) — copy the
  repo to tmp so runs are non-destructive. 74 tests pass total.
- Decision: build PR keeps the `ledger/2026-09/*` placeholders; real entries +
  open exceptions are generated during the runtime close (Step 3), not committed
  here (an open exception would turn CI red on a build PR).
- Next: open PR `build: period-entries`, address CI comments.

## Sun 6 Sep — controls-ci rebased on merged data-ledger
- Rebased `build/controls-ci` onto main (data-ledger merged). 57 tests pass.
- `closeops check` on the real ledger: 8/10 pass. C7 and C10 FAIL — both expected
  pre-bank-rec (Wave 2), NOT controls bugs:
  - C7: bank-rec has not posted September's ~120 bank lines and
    `exceptions/bank-rec-reconciling.json` (outstanding cheques / deposits in
    transit, a bank-rec output) does not exist yet. Reconciles after bank-rec.
  - C10: `Assets:Dodo:Balance` = 15,000 = payments − refunds with zero payout
    clearings posted (the `DODO PAYOUT` lines are bank-rec traps T14). Nets after
    bank-rec posts the payout credits.
- Wave-2 follow-up (flagged to orchestrator): confirm the C10 "paid-out gross"
  definition against bank-rec's actual Dodo postings — po_002's fee (150) is
  omitted from the record (T14), so whether Dodo nets to 0 or to the 150 residual
  depends on how bank-rec books the missing fee. C10 kept as the plan's literal
  formula (gross = payout.amount + fee) for now; revisit once bank-rec lands.

## Sun 6 Sep — Wave 1: data-ledger (branch build/data-ledger)
- Done: `closeops/models.py` (StatementLine, Invoice, Asset, Payout, Candidate,
  Decision, Exception, ControlResult — Decimal money, `from_dict`/`to_dict`).
- Done: `closeops/ledger.py` (load, balance/balances_by_account/trial_balance_net,
  open_items by `invoice:` meta, render_entry, Windows-safe bean_check via
  `python -m beancount.scripts.check`).
- Done: `closeops/rules.py` (load matching + learned, matcher). Load-only; learning
  is Wave 2.
- Done: `scripts/gen_data.py --seed 42` generates company.json, bank CSV with
  derived running balance + statement-balance.json, invoices.json (30, 7 unbooked:
  6 Sep incl. 14,500 legal > materiality, 1 Oct), fixed-assets.csv (FA-001..004),
  rules yaml, Dodo fixtures, and `ledger/main.beancount` (42 accounts, opening
  2026-08-01, August booked+balanced, Sep booked bills/AR/Dodo + reconciling,
  includes 2026-09 stubs). Traps T1–T15 incl. 2 Dodo payouts.
- Done: `scripts/fetch_dodo.py --fixture` (seeded; `--live` via SDK test_mode);
  `scripts/verify_data.py` prints trap counts.
- Done: `tests/test_models.py`, `tests/test_ledger.py` + `tests/fixtures/`.
- Acceptance met: bean-check passes on main.beancount; trial balance nets 0.00;
  CSV closing == statement-balance.json (245694.16); verify_data prints
  auto 95 / exceptions 21 / reconciling 4 (targets ~95/~20/4). 21 tests pass.
- Decisions: bank-rec open items live in the ledger (AP-#### with `invoice:` meta);
  invoices.json is the separate accruals subledger. Dodo opening balance 0 and
  payments−refunds==payout gross so C10 can net; po_002 fee omitted on purpose
  (trap T14 second payout). Reconciling items (3 cheques + 1 deposit) are
  ledger-only, not on the September statement.
- Next: controls-ci worker (C1–C10, report, cli), then Wave 2 bank-rec.

## Sun 6 Sep — ci-gate
- Branch `build/ci-gate`. Only `.github/workflows/controls.yml` + CONTEXT.md.
- Problem: main was red because C7/C10 fail until Sep bank-rec/Dodo entries exist,
  making every `build/*` PR red for unrelated reasons.
- Fix: controls are informational on `build/*` PRs but still gate real close work.
  Tests still gate EVERY PR unconditionally (no continue-on-error on Tests).
  Controls step keeps `continue-on-error`; Report + PR comment still post on every PR.
- `Fail if controls failed` now conditional — fails the job only when controls failed AND:
  * `github.head_ref` starts with `close/`, OR
  * `github.event.pull_request.title` starts with `close(`, OR
  * push to main AND a `ledger/2026-09/*.beancount` file has a real transaction
    (line begins with a date and has a `*`/`!` flag or the `txn` keyword:
    `^YYYY-MM-DD +(\*|!|txn)`), detected by the `Detect real close entries on main` shell step.
    Scope is the 2026-09 include files only (where Wave 2 close work lands), per spec.
- Result: `build/*` PRs stay green when only controls fail; `close/*` branches / `close(` PRs
  and post-entry pushes to main still fail on controls.

## Sun 6 Sep — controls-ci (Wave 1)
- Branch `build/controls-ci`. TDD: tests first, then impl.
- `closeops/controls.py`: C1-C10 per plan §8. `ControlResult` defined here (self-contained; can move to models.py at integration). `run_all(repo_root)` wires controls to repo files defensively (missing data → failing result, no crash). Money via Decimal only.
  - C7 uses plan formula: ledger bank == statement closing + outstanding cheques − deposits in transit.
  - C10: Dodo:Balance == Σpayments − Σrefunds − Σ paid-out gross, where paid-out gross = payout.amount + payout.fee.
- `closeops/report.py`: `close-report.md` + `metrics.json` — header, control table, metrics/funnel block, entries, exceptions (collapsed in <details> when >5), reconciling items.
- `closeops/cli.py`: `check [--json]`, `report`, `status`. Entry point `closeops`; also `python -m closeops.cli`. prepare/decide/apply/baseline/rerun left to Wave 2.
- `.github/workflows/controls.yml`: PR + push main; pytest -q; `closeops check --json` (continue-on-error, PIPESTATUS exit); `closeops report`; `gh pr comment --body-file close-report.md` on PRs; fail if controls failed. No secrets.
- Tests: `tests/test_controls.py` (per control, hand-built beancount fixtures), `tests/test_report.py`. 32 passing.
- Note for integration: controls read `data/company.json` (key aliases tolerated) and expect ledger/main.beancount from data-ledger; C1 fails standalone until data-ledger merges (expected).
- Next: open PR `build: controls-ci`, address CI comments.

## Sun 6 Sep — start
- Repo created; AO orchestrator started with the BUILD prompt (plan.md §10.1).
- Next: wave 1 workers `data-ledger`, `controls-ci`.
- Decision: Python 3.10 on the build machine; `requires-python >= 3.10`.
- Decision: zero spend. No paid model API in the product; judgment happens in AO workers on the Team subscription; `closeops decide` = packet + validate; Neatlogs traces steps via spans (free tier).
