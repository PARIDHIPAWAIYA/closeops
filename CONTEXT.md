# CONTEXT

Running log. Newest entry first. Keep it short: what is done, what is next, decisions.

## Sun 6 Sep - runtime close: depreciation (branch close/depreciation-2)
- prepare -> decide --packet (0 lines; depreciation is fully deterministic) -> apply -> check.
- 3 entries booked, total 1087.78: FA-001 777.78 (full month), FA-002 160.00 (full month),
  FA-003 150.00 (half-month, in service 2026-09-20). FA-004 flagged fully depreciated, no entry.
- check: 10/10 controls pass (bank-rec and accruals already merged to main).
- Note: the AO worker sessions for this task (closeops-14, then closeops-15) hit an AO
  workspace-provisioning failure and internal errors, so the controller ran the same four
  CLI steps directly. bank-rec and accruals were both completed end to end by AO workers.


## Sun 6 Sep — runtime close: accruals (branch close/accruals)
- Ran the accruals close per docs/prompts/worker-accruals.md: prepare -> decide
  (packet/validate) -> apply -> check on branch close/accruals off main.
- prepare: 6 unbooked Sep-service bills; INV-007 (service_period 2026-10) skipped.
- decide: accruals uses deterministic materiality routing in apply (no per-line
  candidate scoring), so the packet renders 0 lines and decisions.json is empty;
  `decide --validate` passes and stamps provenance (decided_by=worker, session,
  trace).
- apply: 5 non-material accruals auto-posted (17,850.00 total: Hosting 3,200,
  Contractors 6,800, Marketing 4,500, Utilities 1,250, Travel 2,100), all Dr
  expense / Cr Liabilities:Accrued:Expenses dated 2026-09-30. The 14,500 legal
  retainer (INV-001) is >= materiality 10,000 -> routed to exceptions/accruals.yaml
  as one OPEN exception AC-001 for controller approval (exercises C5 + C9).
- check: C1-C6, C8 pass. C9 FAIL (1 open: AC-001) — the expected materiality
  exception awaiting a human; NOT resolved by the worker. C7/C10 FAIL are
  pre-bank-rec cross-task failures (September bank/Dodo postings not on this branch),
  documented earlier and outside accruals scope.
- Committed ledger/2026-09/accruals.beancount + exceptions/accruals.yaml
  ("close(2026-09): accruals entries"). 128 tests pass. PR #8 opened.
- Controller approved AC-001 (status: approved, reviewer_note) on close/accruals.
  Pulled, re-ran apply -> the 14,500 legal retainer books with an `approved-by`
  meta (6 entries booked total, 0 open exceptions). Committed
  ("close(2026-09): book approved accrual AC-001") and pushed.
- CI on PR #8: C1-C6, C8, C9 PASS (C9 now green — no open exceptions). C7/C10
  remain red only because close/bank-rec runtime postings are not on this branch
  (accruals posts nothing to Bank/Dodo); expected, resolves on merge. No
  accruals-side fix. Task complete.
## Sun 6 Sep — runtime close: bank-rec (branch close/bank-rec, PR #9)
- Ran the close worker per docs/prompts/worker-bank-rec.md: prepare -> decide
  --packet -> wrote work/bank-rec/decisions.json (116 lines) -> decide --validate
  (passed, stamped decided_by=worker session=closeops-12) -> apply -> check.
- Decisions followed the contract: auto-post the top candidate only at score
  >= 0.90; the 20 sub-0.90 / demotion lines -> "exception" (5 splits, 4 partials,
  3 FX, 3 discounts, 3 unknown-payee, 1 ZOOM duplicate, 1 Dodo po_002 fee-missing),
  each with a one-sentence rationale citing evidence ids. Never auto-posted to
  Suspense; no amounts invented.
- apply booked **94 entries** and opened **22 open exceptions**. Two extra vs the
  20 I flagged came from apply's independent materiality gate: GUSTO -12,500 (L5,
  material) and Dodo payout po_001 (L90, gross 10,000 == materiality) were demoted
  to exceptions so C5 stays green.
- `closeops check`: 7/10. C7/C9/C10 FAIL — all downstream of the 22 open
  exceptions (unposted cash movements). Verified in a throwaway copy that
  resolving the exceptions turns C7/C9/C10 green (C10 nets to the 150.00 residual
  = po_002's missing fee); blind-approving instead surfaces C8 (Suspense=2,850)
  and double-books the ZOOM duplicate — so the unknown-payee + duplicate items
  genuinely need a controller decision (reject / reclassify off Suspense).
- CI on PR #9: Tests 128 passed; only "Fail if controls failed" is red, from
  C7/C9/C10 (open-exception failures). No non-exception failure to fix.
- Committed ledger/2026-09/bank-rec.beancount, exceptions/bank-rec.yaml,
  exceptions/bank-rec-reconciling.json ("close(2026-09): bank-rec entries").
  close-report.md/metrics.json left untracked (CI regenerates + comments them).
- STOPPED per instructions: hit 22 open exceptions that need controller review;
  never resolved them. Needs controller review: 22 open exceptions.

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

## Sun 6 Sep — Wave 2: decide-llm (branch build/decide-llm)
- Scope: `closeops decide` (packet + validate), Neatlogs tracing, CLI `decide`
  subcommand. Zero paid API — no LLM client; judgment happens in AO workers.
- `closeops/decide.py`:
  - `render_packet(candidates, company, rules)` -> `work/<task>/packet.md`: the
    decision contract, chart of accounts, matching rules, and every statement
    line as a compact chunk (<=20 lines) with ranked candidates + evidence ids.
    Reads `work/<task>/candidates.json` (prepare output, plan 6.1).
  - `validate_decisions(candidates, decisions, suspense)` -> list of violations.
    Schema: every line covered once; `choice`/`rationale`/`confidence` present;
    choice is a real candidate id or `"exception"`. Contract: auto-post only when
    the chosen candidate scores >= 0.9; demotions to exception allowed; no
    Suspense auto-posts; no invented amounts (decision postings must equal the
    candidate's). `require_validated` raises `DecisionsInvalid` so `apply`
    refuses until validate passes.
  - `stamp_provenance` records `decided_by: worker`, `AO_SESSION_ID`, a UTC
    timestamp, and the trace id into decisions.json on a passing `--validate`.
- `closeops/trace.py`: `init` (Neatlogs, skipped entirely when NEATLOGS_API_KEY
  unset), `workflow_span`/`tool_span` decorators that are transparent
  passthroughs without a key and check enabled state at call time (so
  import-time decoration still traces once init runs). `current_trace_id` reads
  the active trace id via `neatlogs.inject_trace_context(carrier)` and parses the
  W3C `traceparent` (neatlogs 1.4.21's isolated tracer provider makes
  `opentelemetry.get_current_span()` return trace id 0 inside a span — plan 7
  corrected), falling back to `neatlogs:closeops-<timestamp>` when injection
  yields nothing. Live-verified: real 32-hex id lands in decisions.json.
- Wired: `trace.init()` at the top of the CLI group; `decide` command (packet/
  validate) under a `decide:<task>` WORKFLOW span; `check` under a WORKFLOW span;
  each control C1-C10 under a `TOOL` span. Existing check/report/status
  unchanged.
- Tests (no API key needed): `tests/test_decide.py` (packet renders; fixture
  decisions pass; planted violations rejected — below-0.9 auto-post, unknown
  candidate id, missing line, Suspense auto-post, invented amounts, missing
  rationale, unknown line; demotion allowed; apply gate refuses unvalidated),
  `tests/test_trace.py` (init/spans no-op without a key; traceparent parsed to
  the real id). Fixtures `tests/fixtures/{candidates,decisions}-bank-rec.json`
  cover T1-T15.
- Note: `candidates.json` schema is defined here against plan 6.1; bank-rec's
  prepare (parallel worker) must emit the same shape (`lines[].{line,date,
  description,amount,source,candidates[]}`, each candidate `{id,kind,score,
  account,postings[],evidence[],narration}`). `prepare`/`apply` span decoration
  lands with the bank-rec worker via `trace.workflow_span`.
- Rebased onto main after period-entries (PR #5) merged; cli.py keeps both the
  prepare/apply TASKS registry and the decide command in one group.
- Acceptance met: 76+ tests pass; packet renders for the fixture; fixture
  decisions pass validate; each planted violation rejected; CLI `decide
  bank-rec --packet` then `--validate` round-trips; a run reaches Neatlogs when
  the key is set (skipped cleanly when unset).
- Next: open PR `build: decide-llm`, address CI comments.

## Sun 6 Sep — Wave 2: bank-rec (branch build/bank-rec)
- `closeops/tasks/bank_rec.py`: `prepare` writes `work/bank-rec/candidates.json`
  (deterministic, plan §6.1) — per line, ranked candidates with evidence ids:
  exact 0.95 (+0.03 counterparty token; same-amount ties both listed — T15),
  rule (matching+learned), payout 0.95 / 0.80 if fee missing (T14), split 0.70,
  partial 0.65 (covers T10 discounts as short-pay), fx 0.80, duplicate 0.40,
  none 0.20→Suspense. `apply` enforces the contract independently of `decide`
  (auto-post only score≥0.9, never Suspense, never ≥materiality → those route to
  an exception for approval), renders `ledger/2026-09/bank-rec.beancount` (+meta),
  `exceptions/bank-rec.yaml`, and `exceptions/bank-rec-reconciling.json` for C7.
  Approved exceptions (status: approved, controller may edit proposed_entry, e.g.
  reclassify Suspense) re-post on the next apply with `approved-by` meta.
- Exact matching is token-gated (a same-amount item must share a counterparty
  token) so coincidental amount collisions (WEWORK 4100 vs an unrelated 4100
  bill) don't false-match. Open items exclude bank-rec's own entries so
  prepare/baseline stay idempotent after apply.
- `closeops/baseline.py`: four-tier funnel — exact 60.3% < rules 79.3% <
  agent(reference decider) 81.0% < after-review 100% (monotonic; agent's lower raw
  count vs a naive rules bot is the safety win — it holds material/ambiguous items
  and demotes duplicates). Writes `funnel` into metrics.json.
- `closeops/rules.py`: `learn_from_exceptions` learns **safely** — only from an
  approved exception whose kind is `none`/`rule`, with exactly two postings (bank
  + one real expense/income account), below materiality, and not already covered
  by an existing rule. Never fx/split/partial/payout/duplicate (those would
  auto-post a whole payment/payout to the wrong account). `save_learned`. `rerun`
  learns then re-scores: run1 81.0% → run2 ~83.6% (honest; e.g. reclassified
  unknown-payees SHENZHEN/LAGOS → Expenses:Office). Material lines (e.g. GUSTO
  12,500) stay exceptions in run 2.
- `closeops/cli.py`: registered `bank-rec` in the prepare/apply registry; added
  `baseline` and `rerun` subcommands. check/report/status untouched.
- Contract/C7 note: controls-ci's C7 uses `statement + Σoutstanding − Σdeposits`;
  `bank-rec-reconciling.json` stores signed contributions to match it (cheque =
  bank delta, negative; deposit = negated delta) so the book reconciles.
- Acceptance met: candidates for all 116 lines; reference decisions apply cleanly
  and pass bean-check; after approving exceptions all 10 controls pass (C7 and
  C10 satisfiable); baseline funnel + run1→run2 written. Tests: `tests/test_bank_rec.py`
  (one per T1–T15, `<0.9 never auto-posts`, duplicate/T15 demotion honored,
  material→approval, reconciling, baseline monotonic, rerun raises auto-rate).
  100 tests pass.
- Provenance: apply copies decisions.json top-level `trace`/`decided_by`/
  `session_id`/`timestamp` (stamped by decide-llm `--validate`) onto every entry
  and exception; falls back to constants when absent. Exceptions carry `kind`.
- Rejected exceptions stay unposted (the cash moved but has no correct account
  yet), so C7 fails until the controller supplies a corrected proposed_entry and
  approves — apply prints "N rejected line(s) remain unposted; C7 will fail...".
- Review round applied (PR #7): safe rule learning, provenance copy, rejected-line
  message, rebased onto origin/main. 101 tests pass.
- Next: address CI comments; re-rebase if decide-llm (PR #6) merges — cli.py will
  conflict (keep both import lines and both command blocks). decide-llm consumes
  `candidates.json` and writes the real `decisions.json` (this worker did not
  touch decide.py/trace.py).

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
