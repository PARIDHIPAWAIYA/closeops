# CONTEXT

Running log. Newest entry first. Keep it short: what is done, what is next, decisions.

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

## Sun 6 Sep — start
- Repo created; AO orchestrator started with the BUILD prompt (plan.md §10.1).
- Next: wave 1 workers `data-ledger`, `controls-ci`.
- Decision: Python 3.10 on the build machine; `requires-python >= 3.10`.
- Decision: zero spend. No paid model API in the product; judgment happens in AO workers on the Team subscription; `closeops decide` = packet + validate; Neatlogs traces steps via spans (free tier).
