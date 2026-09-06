# Close-as-Code — full build plan (Track 2, Syndicate by Maximor)

Self-contained. Merges Navaneeth's `plan.md` with the verified facts and improvements. Follow §9 in order; everything else is reference while building.

---

## 0. Context and decision

**What we build.** A month-end close that runs as pull requests. The general ledger is a plain-text Beancount file in git. AO spawns one agent worker per close task (bank reconciliation, accruals, depreciation). Each worker runs deterministic preparation, makes the judgment calls itself from a decision packet (validated by code before anything is applied), deterministic validation, and opens a PR of journal entries. GitHub Actions runs ten accounting controls on every PR. Failed controls route back to the worker via AO; anything the agent cannot resolve waits in AO's "Needs You" column with a proposed fix and a confidence. The controller approves/rejects in the PR and merges. The AO board is the close dashboard. Approved exceptions become matching rules, so the second run auto-posts more than the first.

**Why Track 2 (verified on Devpost, Sun 6 Sep).** Judges: Prateek Karnal, Maaz (AO); Rayed, Shubham, Prayag, Siddhant (Maximor); Ajay (Neatlogs). Four of seven are from an AI-close company; AO is both sponsor and judge; one judge is from an observability company. Rubric: AO usage 25 · Technical/Reliability 25 · Track fit 25 · Demo 15 · Innovation 10. This design makes AO the *runtime* (max AO score), gives accountants controls/materiality/period lock/evidence/sign-off (Maximor), and traces every model judgment (Neatlogs).

**Clock.** Now ≈ 12:00 IST Sunday 6 Sep. Deadline **Mon 7 Sep 03:30 IST** (Sun 6 PM EDT). ~15 h. Submit by 02:45.

**Hard rules.** Everything created after the window opened (Sat 21:30 IST). AO used from the first commit to the last; judges check repos, commit history and AO sessions. Demo video must show AO build sessions, the working product, and the evaluation/improvement process. One track, one Devpost project, every member registered. Discord mandatory.

**Repo working rules (owner's).** TDD — failing test first per module. Keep `plan.md` (this file, copied in) and `CONTEXT.md` current. Small commits, plain messages, **no AI attribution trailers**, no `AGENTS.md`. Push only to the hackathon repo.

**Improvements over the handover plan (all in scope):**
1. `closeops decide` — the judgment step is a CLI command with two halves: `decide --packet` renders the candidates as a compact decision packet for the AO worker (Claude Code on the team subscription — **zero API spend**), and `decide --validate` checks the worker's `decisions.json` against the schema and contract before `apply` will touch it. **No paid model API anywhere in the product.** Neatlogs traces the whole close (prepare → decide → apply → check) through `@neatlogs.span` decorators, which need no LLM call.
2. **Dodo Payments** payout reconciliation (trap T14, control C10) — Northwind is a SaaS; reconciling processor payouts is a real close task. Test-mode API via the `dodopayments` SDK, fixture fallback.
3. **Rule learning** — approved exceptions become rules; `closeops rerun` shows run 1 → run 2 improvement (the hackathon's stated goal: "improve reliability over time").
4. **Four-tier funnel** in metrics — exact baseline → rules-only → agent → after review, plus proposal-acceptance rate, so the model's contribution is visible and honest.
5. Generated data (not hand-written), Windows-safe `bean-check`, exception YAML links to its trace, sponsor shots in the video.

---

## 1. Product spec

**Users.** Controllers/accountants at small companies and outsourced firms who close monthly from bank exports, AP bills, processor payouts and asset schedules.

**User story.** "I type *Run September close*. Agents reconcile the bank (including the Dodo payouts), book accruals and depreciation, and open one PR each. I review entries as diffs, approve or reject the exceptions they could not resolve, merge. The close report says what was automated, what needed me, why, and what the system learned."

**MVP (must ship).** Synthetic company, August closed, September open · tasks `bank-rec`, `accruals`, `depreciation` · `decide` packet/validate step with Neatlogs spans · ten controls with PR comment · exception queue with approve/reject in PR · rule learning + rerun metric · AO orchestrator prompt that runs the close · metrics funnel · README, architecture doc, video, Devpost.

**Stretch (only after the runtime demo run succeeded).** `prepaids` task; `flux` commentary; approve/reject via PR-comment commands; Dodo live API if the key arrives.

**Out of scope.** Real ERP integration; UI beyond AO board + markdown report; multi-currency beyond the FX trap.

---

## 2. Architecture

```
controller ── "Run September close" ──▶ AO orchestrator (Claude Code, kind=orchestrator)
                                             │ spawns, one branch+worktree each
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

**Deterministic sandwich.** Code prepares candidates and evidence; the model only makes judgment calls under a contract code enforces; code validates and renders. Ledger writes are always safe; reasoning is auditable (Neatlogs trace id on every exception).

---

## 3. Repository layout — `C:\Users\pawai\closeops`

```
closeops/
  README.md  plan.md  CONTEXT.md  .env.example  .gitignore (work/ .env __pycache__ .venv)
  pyproject.toml            # package closeops; deps beancount>=3.2 pyyaml click python-dateutil
                            # extras: test=[pytest] trace=[neatlogs] dodo=[dodopayments]
  ledger/main.beancount     # options, accounts, opening balances, August, Sep booked bills/invoices, includes
  ledger/2026-09/{bank-rec,accruals,depreciation}.beancount   # written by workers
  data/company.json  data/bank/sep-2026.csv  data/bank/statement-balance.json
  data/ap/invoices.json  data/fixed-assets.csv
  data/dodo/{payouts,payments,refunds}.json
  data/rules/matching.yaml  data/rules/learned.yaml
  exceptions/{bank-rec,accruals,depreciation}.yaml  exceptions/bank-rec-reconciling.json
  work/                     # gitignored: candidates.json, decisions.<hash>.json per task
  scripts/gen_data.py  scripts/fetch_dodo.py  scripts/verify_data.py
  closeops/
    cli.py        # prepare | decide | apply | check | report | baseline | rerun | status
    ledger.py     # load, balances by account/date, open items, render entries, bean-check
    models.py     # StatementLine Invoice Asset Payout Candidate Decision Exception ControlResult
    decide.py     # packet renderer + decisions.json validator; trace.py: Neatlogs init/spans
    tasks/{bank_rec,accruals,depreciation}.py
    controls.py   # C1–C10
    report.py     # close-report.md + metrics.json
    baseline.py   # exact matcher + rules-only tier
    rules.py      # load matching + learned; learn from approved exceptions
  tests/  test_ledger test_bank_rec test_accruals test_depreciation test_controls
          test_report test_decide test_rules test_dodo  fixtures/
  .github/workflows/controls.yml
  docs/architecture.md docs/controls.md docs/demo-script.md docs/prompts/{orchestrator-build,orchestrator-close,worker-bank-rec,worker-accruals,worker-depreciation}.md
  close-report.md  metrics.json     # regenerated on main after the close
```

---

## 4. Data design (all generated by `scripts/gen_data.py --seed 42`)

**Company** `data/company.json`: Northwind Labs Inc., USD, period `2026-09`, `period_lock_before` `2026-09-01`, materiality 10,000.00, bank `Assets:Bank:Operating`, suspense `Equity:Suspense`, processor clearing `Assets:Dodo:Balance`. 25-person B2B SaaS.

**Chart of accounts (~42).** Assets: `Bank:Operating`, `AR`, `Dodo:Balance`, `Prepaid:Insurance`, `Prepaid:Software`, `FixedAssets:Computers`, `FixedAssets:Furniture`, `FixedAssets:AccumulatedDepreciation`. Liabilities: `AP`, `Accrued:Expenses`, `Accrued:Payroll`, `CreditCard`, `DeferredRevenue`. Equity: `OpeningBalances`, `RetainedEarnings`, `Suspense`. Income: `Subscriptions`, `Services`, `Interest`. Expenses: `Payroll:{Salaries,Taxes,Benefits}`, `Rent`, `Software`, `Hosting`, `Marketing`, `Travel`, `Meals`, `Insurance`, `Legal`, `Accounting`, `BankFees`, `PaymentProcessing`, `Depreciation`, `Office`, `Utilities`, `Contractors`, `FX`. Opening balances 2026-08-01 via `Equity:OpeningBalances`; August fully booked and balanced.

**Bank statement** `data/bank/sep-2026.csv` — `Date,Description,Amount,Balance,Reference`; ~120 lines; uppercase bank-style descriptions ≤32 chars; running balance derived by the generator and its closing figure written to `statement-balance.json`.

**Traps = test plan for `bank_rec.py`:**

| # | Category | n | Expected outcome |
|---|---|---|---|
| T1 | Exact match to open AP bill | ~50 | auto-post, ≥0.95 |
| T2 | Exact match to open AR invoice | ~15 | auto-post |
| T3 | Recurring payee via rule (GUSTO ×2, WEWORK, GITHUB, NOTION…) | ~15 | auto-post 0.9 |
| T4 | Bank fee / interest | 6 | auto-post BankFees / Interest |
| T5 | Split payment (one line, 2–3 bills) | 5 | exception, proposed split, ~0.7 |
| T6 | Partial payment | 4 | exception, partial application, remainder open |
| T7 | FX/rounding within 1% or $5 | 3 | exception, bill + `Expenses:FX`, 0.8 |
| T8 | Duplicate charge (two ZOOM −499 same day) | 2 | first auto-posts; second **demoted** to exception "possible duplicate" |
| T9 | Unknown payee (`POS 4471 SHENZHEN`) | 3 | exception <0.5, proposed Suspense, needs human |
| T10 | Short-pay with 2% discount | 3 | exception, discount contra |
| T11 | Outstanding cheque #1042 dated Sep 29 | 3 | reconciling item, not an entry |
| T12 | Deposit in transit (ledger Sep 30, statement Oct 1) | 1 | reconciling item |
| T13 | Sep line paying an August bill | 2 | auto-post, cites Aug bill |
| **T14** | **Dodo payout** `DODO PAYOUT` ×2: net = gross − refunds − fee | 2 | first auto-posts with fee split (0.95); second's fee is absent from the payout record → exception 0.8 proposing `Expenses:PaymentProcessing` |
| **T15** | **Same amount, two vendors** (two open bills 1,800.00: AWS and Datadog; description says DATADOG) | 2 | deterministic top candidate is ambiguous; model picks by description token; one case where the description contradicts → **demoted** to exception |

Targets: ~95 auto-posted, ~20 exceptions, 4 reconciling items. Baseline exact-match ≈ 62%; rules-only ≈ 74%; agent ≈ 80% auto + all exceptions with proposals; after review 100%; run 2 ≈ 87%.

**Vendor bills** `data/ap/invoices.json` (~30): `{id, vendor, date, due, amount, currency, account, service_period, booked}`. ~6 `booked:false` September-service bills drive accruals; one above materiality (14,500 legal retainer); one with `service_period: 2026-10` (must not accrue).

**Fixed assets** `data/fixed-assets.csv`: FA-001 MacBooks 28,000 / 36 mo from 2026-02-01 · FA-002 desks 9,600 / 60 mo from 2026-03-15 · FA-003 server rack 12,000, salvage 1,200, in service 2026-09-20 (half-month) · FA-004 old laptops 4,800 / 36 mo from 2023-08-01 (fully depreciated → book nothing, flag).

**Dodo** `data/dodo/`: 2 payouts (`payout_id, amount, fee, currency, status:"success", created_at, payout_document_url`), ~8 payments (`payment_id, total_amount, currency, created_at, customer`), 2 refunds (`refund_id, payment_id, amount`). `scripts/fetch_dodo.py --fixture` (default, seeded) or `--live` (SDK `DodoPayments(bearer_token=env DODO_PAYMENTS_API_KEY, environment="test_mode")`; `client.payouts.list()`, `client.payments.list()`, `client.refunds.list()` filtered to September). README states which was used. Ledger: payments Dr `Assets:Dodo:Balance` / Cr `Income:Subscriptions` (booked by generator in August/September as they occur); refunds reverse; payout Dr Bank (net) + Dr `Expenses:PaymentProcessing` (fee) / Cr `Assets:Dodo:Balance` (gross − refunds).

**Matching rules** `data/rules/matching.yaml` — list of `{match: regex, account, confidence}` for GUSTO, WEWORK, SERVICE FEE, INTEREST PAID, GITHUB|NOTION|SLACK|ZOOM|FIGMA. `learned.yaml` starts empty.

**Exception YAML** `exceptions/<task>.yaml`:
```yaml
- id: BR-007
  task: bank-rec
  source: "data/bank/sep-2026.csv#L41"
  issue: "Line 41 (-1,250.00 'ACME CORP') matches INV-118 (1,200.00) + INV-121 (50.00) only as a split"
  proposed_entry: {date: 2026-09-14, narration: "...", postings: [{account, amount, meta}]}
  confidence: 0.71
  decided_by: closeops-decide      # closeops-decide | worker | human
  trace: "neatlogs:<trace-id or workflow+timestamp>"
  status: open                     # open | approved | rejected
  reviewer_note: ""
```

---

## 5. Beancount notes

Beancount 3.2.x, Python 3.12 (`pip install beancount`). Transactions: `2026-09-14 * "ACME CORP" "narration"` with indented `key: "value"` metadata (`source`, `task`, `confidence`, `approved-by`, `decided_by`, `trace`) and postings `Account  -1250.00 USD` (one may omit amount). Balance assertions apply at start of date → assert Sep 30 close on `2026-10-01`. Validate with `python -m beancount.scripts.check ledger/main.beancount` (Windows-safe). Python API: `from beancount import loader; entries, errors, options_map = loader.load_file(path)`; sum `p.units.number` per account for `date <= as_of`. **Decimal everywhere; never float for money.**

---

## 6. Close tasks — one contract, three commands (+ decide)

- `closeops prepare <task>` → `work/<task>/candidates.json` (deterministic).
- `closeops decide <task> --packet` → `work/<task>/packet.md`; the worker writes `decisions.json`; `decide --validate` gates it (see §7).
- `closeops apply <task>` → validates decisions, renders `ledger/2026-09/<task>.beancount` + `exceptions/<task>.yaml`, learns rules from approved exceptions, runs bean-check (deterministic).

**Decision contract (enforced in `apply`, regardless of what `decide` said).** Per line: `{choice: <candidate_id>|"exception", rationale, confidence}`. Auto-post only if the chosen candidate's score ≥ 0.9. Anything else → exception with the chosen candidate as `proposed_entry`. The model may **demote** a ≥0.9 candidate to exception (duplicate, conflicting description). Never invent amounts. Never auto-post to Suspense.

### 6.1 `bank-rec`
**prepare:** open items (AP booked-unpaid via `invoice:` meta not offset; AR unpaid; Sep ledger bank postings for timing; Dodo payouts). Candidates per line: `exact` 0.95 (+0.03 if description contains counterparty token; if two open items tie, both listed at 0.95 — T15) · `rule` (matching + learned) · `payout` 0.95 (net amount match to Dodo payout, fee split from record; 0.8 if fee missing) · `split` 0.70 · `partial` 0.65 · `fx` 0.80 · `duplicate` flag 0.40 · `none` 0.20 → Suspense. Evidence ids on every candidate.
**apply:** render auto-posts with meta; exceptions YAML; `exceptions/bank-rec-reconciling.json` (outstanding cheques, deposits in transit) for C7.
**tests:** one per T1–T15; `<0.9 can never auto-post`; demotion honored; apply output passes bean-check.

### 6.2 `accruals`
**prepare:** `booked:false` + `service_period == 2026-09` → Dr expense / Cr `Liabilities:Accrued:Expenses` dated 2026-09-30; October-service bills listed "do not accrue"; ≥ materiality → `needs_approval`. **apply:** materiality items become open exceptions (exercise C5 + C9). **tests:** October excluded; materiality → exception; totals.

### 6.3 `depreciation`
**prepare:** straight-line `(cost − salvage)/life` per month; half-month for in-service in September; zero if fully depreciated; prior accumulated read from ledger. **apply:** one entry per asset with `asset:` meta. **tests:** FA-001 full, FA-003 half, FA-004 zero, sum.

---

## 7. `closeops decide` — the judgment step, zero-cost (`closeops/decide.py`)

**Constraint: nothing in this project is paid for.** Model reasoning happens only inside AO worker sessions (Claude Code on the existing Team subscription). The Python package never calls a paid API.

- `closeops decide <task> --packet` → writes `work/<task>/packet.md`: the decision contract, chart of accounts, rules, and every statement line with its ranked candidates and evidence ids, in ≤20-line chunks. The worker reads the packet and writes `work/<task>/decisions.json`.
- `closeops decide <task> --validate` → schema check (`choice`, `rationale`, `confidence` per line; every line covered; `choice` is a real candidate id or `"exception"`), contract check (auto-post only when the chosen candidate score ≥ 0.9; demotions allowed; no Suspense auto-posts; no invented amounts — postings must equal candidate postings). Exit 1 with a readable list of violations; `apply` refuses to run until validate passes.
- `decisions.json` records `decided_by: worker`, the AO session id (from `AO_SESSION_ID` env if present) and a timestamp, so every judgment is attributable.
- Tests: fixture `tests/fixtures/decisions-bank-rec.json` (hand-written, covers T1–T15); validate rejects an auto-post below 0.9, an unknown candidate id, a missing line, a Suspense auto-post; `apply` refuses unvalidated decisions.
- **Neatlogs (free tier; verified against neatlogs 1.4.21 on this machine):** at the top of `closeops/cli.py`: `neatlogs.init(api_key=os.environ.get("NEATLOGS_API_KEY"), workflow_name="closeops", tags=["syndicate", period])`, skipped entirely when the env var is unset. Decorate `prepare`, `decide`, `apply` and `check` with `@neatlogs.span(kind="WORKFLOW", name=f"<step>:{task}", tags=[task], session_id=f"close-{period}")`, and each control function with `@neatlogs.span(kind="TOOL", name="C7")`, so a close run shows as one session with per-step spans, candidate counts, decision counts and control outcomes as captured output. Use `neatlogs.extract_trace_context()` to record the trace id into `decisions.json` and each exception's `trace:`; fall back to `workflow_name+timestamp`.
- **Verified SDK facts (Python 3.10 build machine):** beancount 3.2.3 → `python -m beancount.scripts.check FILE`; dodopayments 1.115.0 → `client.payouts.list()`, `client.payouts.breakup()`, `client.payments.list()`, `client.refunds.list()`, `client.balances.retrieve_ledger()`; `environment="test_mode"` → `https://test.dodopayments.com` (test mode moves no money). `anthropic` is **not** a dependency.

## 8. Controls (`closeops check`), CLI, CI

| # | Control | Fails when |
|---|---|---|
| C1 | Ledger parses and balances (`bean-check`, `errors == []`) | unbalanced posting |
| C2 | Trial balance nets to zero at Sep 30 | — |
| C3 | Period lock: no `ledger/2026-09/*` entry before `period_lock_before` | entry dated 2026-08-31 |
| C4 | Every Sep entry has non-empty `source` | missing source |
| C5 | Any posting ≥ materiality has `approved-by` | 14,500 without approval |
| C6 | No duplicate (date, postings set, source) | duplicated entry |
| C7 | Ledger bank balance Sep 30 == statement closing + outstanding cheques − deposits in transit | off by 100 |
| C8 | `Equity:Suspense` == 0 at Sep 30 | unresolved unknown payee |
| C9 | No `status: open` in `exceptions/*.yaml` | one open |
| **C10** | `Assets:Dodo:Balance` == Σ payments − Σ refunds − Σ paid-out gross | a payout dropped |

`close-report.md`: header · control table · metrics block (funnel, run 1/run 2) · per-task entries table · exceptions table · reconciling items. Collapse long tables in `<details>` so the PR comment stays readable.

**CLI:** `closeops prepare|decide|apply <task>` · `check [--json]` · `report` · `baseline bank-rec` · `rerun bank-rec` · `status`. Entry point `closeops = closeops.cli:main`; workers may use `python -m closeops.cli`.

**CI** `.github/workflows/controls.yml` (on PR + push main; `contents: read`, `pull-requests: write`): checkout → setup-python 3.12 → `pip install -e .[test,trace,dodo]` → `pytest -q` → `closeops check --json` with `continue-on-error` capturing exit → `gh pr comment --body-file close-report.md` on PRs → fail if controls failed. No secrets in CI: `decide` tests use the fake.

---

## 9. Build plan (IST, from 12:00 Sunday)

### Step 0 — 12:00–13:00, human, **screen-record it**
1. `claude` once and `/login` so AO-spawned sessions authenticate on the Team subscription (no API key, no spend).
2. `gh auth status`.
3. AO desktop for Windows from the AO releases page (current build); launch; `ao doctor` if CLI present. If it fails after 30 min → §13 fallback, ask in Discord `#syndicate-help`.
4. `python -m pip install beancount pyyaml click pytest anthropic neatlogs dodopayments`.
5. Accounts (all free tiers): Neatlogs (key → `NEATLOGS_API_KEY`), Dodo test mode (`DODO_PAYMENTS_API_KEY`, optional). No Anthropic API key: model work runs on the Team subscription inside AO. `.env` local only.
6. `mkdir C:\Users\pawai\closeops && cd … && git init -b main`; add README (2 lines), plan.md (this), CONTEXT.md, `.gitignore`, `.env.example`; `git commit -m "Initial scaffold"`; `gh repo create <account>/closeops --public --source=. --push`; add teammate as collaborator.
7. AO: Add project → repo path; worker agent Claude Code; base branch main; setup command `pip install -e .[test,trace,dodo]`. Spawn orchestrator (kind=orchestrator, mode=chat), paste the BUILD prompt (§10.1).

### Wave 1 — 13:00–16:00 (parallel)
- **`data-ledger`** (`build/data-ledger`): `scripts/gen_data.py` (seeded; bank CSV with derived running balance; August entries; Sep booked bills/AR; cheque + deposit in transit; T1–T15 incl. Dodo payouts; invoices; assets; Dodo fixtures via `fetch_dodo.py --fixture`), `ledger/main.beancount`, `models.py`, `ledger.py`, `rules.py` (load only), tests. Acceptance: bean-check passes; TB zero; CSV closing = statement-balance; `verify_data.py` prints trap counts.
- **`controls-ci`** (`build/controls-ci`): `controls.py` C1–C10, `report.py`, `cli.py` with `check/report/status`, workflow, tests per control on fixtures. Acceptance: CI runs on its own PR and posts the comment.
Merge order: data-ledger, then controls-ci rebased.

### Wave 2 — 16:00–20:00 (parallel, after wave 1 merges)
- **`bank-rec`**: `tasks/bank_rec.py` (incl. `payout` candidates), `baseline.py` (exact + rules-only tiers), `rules.py` learning + `rerun`, CLI `prepare/apply/baseline/rerun`, tests T1–T15. Acceptance: candidates for all lines; fixture decisions apply cleanly; baseline block written; rerun with a learned rule raises auto-rate.
- **`decide-llm`** (name kept ≤20 chars): `decide.py` packet renderer + validator, `trace.py` Neatlogs init and spans on all steps, tests. Acceptance: packet renders for real candidates; fixture decisions pass validate; each planted violation is rejected; a run appears in Neatlogs when the key is set.
- **`period-entries`**: accruals + depreciation + tests. Acceptance: schedules match hand-computed numbers.
- **`docs`**: README (setup, run, architecture, controls, metrics, sponsor tools, "why git"), `docs/*.md`, all prompts, demo script.

### Step 3 — 20:00–22:30 runtime close (record everything)
Spawn orchestrator CLOSE session with §10.2. Three close workers run prepare → decide → apply → PR. Human review loop (§10.4). Fix via `fix/*` workers if needed. Then `closeops rerun bank-rec` on main for run 2; `closeops report`; commit `close-report.md` + `metrics.json`.

### Step 4 — 22:30–02:45
22:30–00:30 README results, Neatlogs + Dodo + AO screenshots, `CONTEXT.md`. 00:30–02:00 video (§11), Devpost (§12). 02:00–02:45 buffer, tag `v0.1.0`, **submit**. Nothing new after 02:15.

**Cut order if behind at 20:00:** Dodo live API (fixture stays) → rule learning/rerun → funnel tiers (keep baseline vs agent) → docs worker (README by hand) → depreciation. **Never cut:** `decide --validate` + Neatlogs spans, the recorded runtime close, the controls, bank-rec + one other task.

---

## 10. AO prompts (save under `docs/prompts/`)

### 10.1 Orchestrator BUILD
```
You are the build orchestrator for closeops, a plain-text-ledger month-end close that runs as
pull requests. Read plan.md fully first. Deliver the MVP in plan.md §3–§8 by spawning workers on
separate branches. Order:
  wave 1 (parallel): data-ledger, controls-ci
  wave 2 (parallel, after wave 1 merges): bank-rec, decide-llm, period-entries, docs
Each worker: TDD (tests first), small commits with plain messages, no AI attribution trailers,
update CONTEXT.md with what it did, open a PR, and address CI comments. Review each PR for
correctness against plan.md before asking me to merge. One-line status per worker. Do not expand
scope beyond MVP; stretch items only when I say so. Worker names ≤ 20 characters.
```

### 10.2 Orchestrator CLOSE ("Run September close")
```
You are the close orchestrator for Northwind Labs, period 2026-09. Goal: complete the September
close as reviewed pull requests. Spawn three workers in parallel, one per task, on branches
close/<task>: bank-rec, accruals, depreciation. Each follows docs/prompts/worker-<task>.md
exactly, opens a PR titled "close(2026-09): <task>", and stops when CI is green or when it hits
an exception it cannot resolve without a human. Never resolve exceptions yourself. When a worker
reports a CI failure that is NOT an open-exception failure, send it the CI comment and ask it to
fix and push. When all three PRs are merged, spawn close/report to run `closeops rerun bank-rec`
and `closeops report` on main and open a PR with close-report.md and metrics.json.
Report per task: entries proposed, exceptions open, PR link.
```

### 10.3 Worker template `worker-<task>.md`
```
Task: <task>, period 2026-09, branch close/<task>.
1. pip install -e .[trace] ; closeops prepare <task>
2. closeops decide <task> --packet ; read work/<task>/packet.md and write work/<task>/decisions.json:
   auto-post only when score >= 0.9, otherwise exception with the best candidate as proposed_entry
   and a one-sentence rationale citing evidence ids. Then closeops decide <task> --validate and fix
   every violation it lists.
   Never invent amounts. Never auto-post to Equity:Suspense.
3. closeops apply <task> ; closeops check
4. Commit ledger/2026-09/<task>.beancount and exceptions/<task>.yaml, message
   "close(2026-09): <task> entries". Push. gh pr create with the summary table from close-report.md.
5. If CI fails only on C9 (open exceptions): reply "Needs controller review: N open exceptions"
   and stop. Any other control: fix, commit, push, once. Then stop.
```

### 10.4 Human review loop (what the video shows)
1. `close(2026-09): bank-rec` red on C9 with ~20 open exceptions; worker shows "Needs controller review".
2. Controller edits `exceptions/bank-rec.yaml`: approve splits/partials/FX/discount/payout-fee; reject the duplicate and the Shenzhen POS with notes; commit to the branch.
3. Via AO chat: "exceptions reviewed, apply and push" → worker re-runs `apply` (learns rules), CI green, merge from AO.
4. Accruals (one materiality item) same; depreciation green first time.
5. Report PR: ten controls green, funnel + run 1/run 2.

---

## 11. Demo video (≤ 5:00)

| Time | Shot | Say |
|---|---|---|
| 0:00 | Bank CSV beside the ledger | "Month-end close is a person matching 120 bank lines to bills by hand. We made the close run as pull requests." |
| 0:20 | AO board during the build; session list | "Every part was built by AO workers on their own branches: data, controls, bank rec, the decision step, period entries, docs. CI comments went back to the owning worker." |
| 0:50 | Orchestrator chat: "Run September close"; three workers appear | "At runtime, AO is the product." |
| 1:15 | PR diff of `bank-rec.beancount`; CI comment, C9 red | "Every entry links to its evidence. Ten controls on every PR. Twenty lines needed a human." |
| 1:45 | **Neatlogs** session: prepare → decide → apply → check spans, one exception's `trace:` id | "Every step of the close is traced, and every exception links to its trace." |
| 2:00 | Needs You; approve a split, reject the duplicate; push; green; merge | "The agent proposes with a confidence and waits. Only approved entries reach the ledger." |
| 2:35 | **Dodo payout** line reconciled: net = gross − refunds − fee, fee booked | "Processor payouts reconcile against Dodo's payout records; the fee books itself." |
| 2:55 | Accruals PR (materiality exception; October bill refused); depreciation green | |
| 3:20 | `close-report.md`: funnel 62 → 74 → 80 → 100; **run 1 → run 2** 80 → 87 | "Approved exceptions become rules. The second close needs fewer humans." |
| 3:50 | Architecture (12 s) | "Code prepares and validates, the model only judges, git is the audit trail and the gate." |

1080p, mic on, no music over speech, unlisted YouTube.

---

## 12. Devpost

Name **Close-as-Code** · tagline "Month-end close that runs as reviewed pull requests, orchestrated by AO." · Track 2 · problem/users (§1) · what it does (§0) · how we built it with AO (build waves, session list, PR/CI loop; AO as runtime) · architecture (§2, sandwich, ten controls, exception contract) · evaluation and results (funnel, run 1→2, proposal acceptance, controls green) · reliability (Decimal money, bean-check on every apply, 0.9 threshold, suspense zero, period lock, duplicates, human gate on materiality and every exception) · **sponsor tools** (AO runtime; Neatlogs traces every judgment, linked from exceptions; Dodo Payments test-mode API as payout source — or fixture, stated) · what's next (ERP adapters, prepaids, flux) · team · links.

Evidence for the AO section: `ao session ls --all` screenshot (build + close workers), Kanban with Needs You populated, one red and one green CI comment, merged PR list.

---

## 13. Risks

| Risk | Fallback |
|---|---|
| AO desktop fails on Windows | Exhaust Windows path 30 min + Discord; else run `claude` in `git worktree` folders, one branch/PR per task, screen-recorded; state honestly |
| Workers can't find `closeops` | `python -m closeops.cli`; AO setup command installs `-e .` |
| Team-plan usage cap hit mid-build | Stagger workers (2–3 at a time); the cap resets on a rolling window; nothing is billed |
| Neatlogs SDK API differs from notes | Keep init in one function; if `span` missing, rely on auto-instrumentation only |
| Dodo key not approved | Fixture (default) — same schema, stated in README |
| Beancount install fails | `beancount==2.3.6`; last resort hand parser for our subset |
| Bank-rec unstable at 19:00 | Cut traps to T1–T5, T8, T9, T14; honest counts |
| CI comment not routed by AO | Paste into worker chat via AO send; still demonstrates the loop |
| Out of time before runtime demo | Skip docs worker; skip depreciation; demo needs bank-rec + one task |

---

## 14. Definition of done / verification

- `pytest -q` green locally and in CI (no keys in CI).
- `closeops decide bank-rec --packet` then a worker-written `decisions.json` passes `--validate`; the close shows at app.neatlogs.com as one session with prepare/decide/apply/check spans tagged `bank-rec`.
- `closeops check` on `main` after the close: **ten** controls pass.
- Dodo: both `DODO PAYOUT` lines reconciled with fee split; tampering a payout fails C10.
- `metrics.json`: funnel four tiers; `proposal_acceptance_rate`; `run2.auto_rate > run1.auto_rate`.
- A deliberately bad PR (pre-lock date) turns CI red and the comment reaches the worker session (screenshot).
- `ao session ls --all` shows orchestrators, six build workers, three close workers, report worker.
- Fresh clone + README reproduces prepare/decide/apply/check.
- Video ≤ 5 min uploaded; Devpost submitted before 03:30 IST with every field in §12; `CONTEXT.md` final entry.
