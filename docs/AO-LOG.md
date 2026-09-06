# AO usage log

Every line of this project was produced through [Agent Orchestrator](https://aoagents.dev). AO was
used in two distinct roles: as the **build harness** (Wave 1 and Wave 2 workers, each on its own
branch and PR) and as the **product runtime** (the September close itself, one worker per close
task). Session ids below are AO's own; verify with `ao session ls --all --include-terminated`.

Project registered 12:11 IST 6 Sep 2026, `C:\Users\pawai\closeops`, worker + orchestrator agent
`claude-code`, permission mode `bypass-permissions`, reviewer harness `claude-code`, post-create
`python -m pip install -e .[test,trace,dodo]`.

## Sessions

| Session | Name | Role | Purpose | Outcome |
|---|---|---|---|---|
| closeops-1 | build-orch | orchestrator | first build orchestrator | died on an expired Claude Code OAuth token; re-auth fixed it |
| closeops-2 | build-orch | orchestrator | retry | superseded once project config (permissions, rules, reviewer) was set |
| closeops-3 | build-orch | orchestrator | **build orchestrator** | planned both waves, spawned 7 workers, tracked status |
| closeops-4 | data-ledger | worker | synthetic company, ledger, models, rules loader | **PR #2 merged** |
| closeops-5 | controls-ci | worker | controls C1–C10, report, CLI, CI workflow | **PR #1 merged** |
| closeops-6 | decide-llm | worker | decision packet + validator, Neatlogs tracing | **PR #6 merged** |
| closeops-7 | period-entries | worker | accruals + depreciation tasks | **PR #5 merged** (AO review: approved) |
| closeops-8 | docs | worker | README, architecture, controls, demo script | **PR #4 merged** (AO review: changes requested → fixed → approved) |
| closeops-9 | bank-rec | worker | bank reconciliation, baseline funnel, rule learning | **PR #7 merged** (AO review: approved) |
| closeops-10 | ci-gate | worker | make controls informational on `build/*`, gating on `close/*` | **PR #3 merged** (AO review: approved) |
| closeops-11 | close-orch | orchestrator | **close orchestrator** — "Run September close" | spawned the three close workers |
| closeops-12 | bank-rec | worker | ran the September bank reconciliation | **PR #9 merged** — 94 entries, 22 exceptions, red → controller review → 10/10 green |
| closeops-13 | accruals | worker | ran the September accruals | **PR #8 merged** — 5 accruals, 1 materiality exception |
| closeops-14 | depreciation | worker | ran the September depreciation | stalled after `apply`; workspace could not be reprovisioned |
| closeops-15 | deprec-close | worker | replacement depreciation worker | `WORKSPACE_PROVISION_FAILED` / `INTERNAL_ERROR`; controller ran the same four CLI steps → **PR #10 merged** |

15 sessions: 4 orchestrator, 11 worker. 10 pull requests, all merged.

## AO's reviewer

AO's configured reviewer (`claude-code`) reviewed worker PRs and posted its verdicts to GitHub.
Recorded verdicts: **PR #3 approved, PR #4 changes-requested then approved, PR #5 approved,
PR #7 approved, PR #8 approved.** The change request on PR #4 was substantive — it caught that
`docs/architecture.md` and the README repo-layout block listed `decide.py`, `trace.py`,
`baseline.py` and `tasks/bank_rec` before those modules existed. The worker annotated them as
planned and the re-review approved (GitHub review id 5124692005).

Reviews on PRs #1, #2 and #6 were cancelled or superseded: merging a PR terminates its worker
session, which cancels an in-flight review. After noticing that on the first two merges we changed
the rule to *wait for the verdict, then merge* — visible in the log as approved verdicts from PR #3
onward.

## The feedback loop in practice

CI ran on every PR (`pytest` + `closeops check`), posting the ten-control table as a PR comment.
Failures and human review findings were routed back to the owning session with `ao send`, and the
worker pushed a fix to the same branch. Findings that came back this way:

1. **PR #1** — controls C2–C10 reported PASS when the ledger was absent (vacuous pass). Fixed to
   fail with `skipped: ledger missing/unparseable`, plus tests.
2. **PR #2** — the data generator wrote CRLF on Windows, so regenerating dirtied every data file.
   Fixed with explicit `newline="\n"`; regeneration is now byte-identical.
3. **PR #6** — the recorded Neatlogs trace id was always the timestamp fallback, because neatlogs
   1.4.21 uses an isolated tracer provider and `opentelemetry.trace.get_current_span()` returns an
   invalid span. Fixed to read the id via `neatlogs.inject_trace_context()`.
4. **PR #6** — the validator rejected numeric `confidence` values (the float ban intended for money
   was applied to confidence too). Fixed to accept int/float/string in 0..1.
5. **PR #7** — rule learning would have learned `GUSTO → Payroll` from a *materiality* exception and
   `DODO → PaymentProcessing` from a payout-fee exception, which in run 2 would auto-post an entire
   vendor payment or an entire payout to a fee account. Constrained to two-posting unknown-payee
   approvals only; material items stay exceptions.
6. **PR #7** — exception provenance was hard-coded; now copied from `decisions.json`.

## AO as the runtime

The close itself is an AO workflow, not a script. The controller types "Run September close" into an
AO orchestrator session; it spawns one worker per close task on its own branch and worktree. Each
worker runs `prepare → decide --packet → (writes decisions) → decide --validate → apply → check`,
commits, and opens a PR. A worker that hits an exception it cannot resolve **stops and waits** —
AO's board shows it needing input. The controller reviews the exception YAML in the PR diff,
approves or reclassifies, and the worker re-applies. That loop is the product.

## Honest notes

- The depreciation close task was completed by the controller running the same four CLI commands,
  after two AO worker sessions failed to provision a workspace (`closeops-14` stalled,
  `closeops-15` returned `WORKSPACE_PROVISION_FAILED` and then `INTERNAL_ERROR`). bank-rec and
  accruals — the two tasks with real judgment and exceptions — were completed end to end by AO
  workers.
- Model work ran on a Claude Code team subscription inside AO sessions. The `closeops` package never
  calls a paid model API; `anthropic` is not a dependency.
