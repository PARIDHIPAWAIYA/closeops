# Devpost submission — copy/paste

**Submit at:** https://syndicate-by-maximor.devpost.com/ — before Sun 6 Sep 6:00 PM EDT / Mon 7 Sep 3:30 AM IST.

---

## Project name
Close-as-Code

## Tagline
Month-end close that runs as reviewed pull requests, orchestrated by AO.

## Track
Track 2 — Autonomous Office of the CFO

## Repository
https://github.com/PARIDHIPAWAIYA/closeops

## Demo video
_(paste unlisted YouTube link)_

---

## The problem and who has it

Controllers and accountants at small companies and outsourced accounting firms close the books by
hand every month: matching a bank export line by line against open bills and invoices, booking
accruals and depreciation, chasing the handful of lines that don't match, and assembling evidence
for the auditor afterwards. It is repetitive, it is judgment-heavy in exactly a few places, and the
audit trail is usually a spreadsheet and someone's memory.

96% of CFOs want AI on this work; 14% trust it end to end. The gap is not capability, it is control.

## What we built

The general ledger is a plain-text Beancount file in a git repository. The controller types
**"Run September close"** into an Agent Orchestrator session. AO spawns one agent worker per close
task — bank reconciliation, accruals, depreciation — each in its own branch and worktree. Each
worker runs the same four steps:

    closeops prepare <task>            # deterministic: candidates + evidence, no model
    closeops decide <task> --packet    # renders the judgment calls for the agent
    ...the agent writes decisions.json...
    closeops decide <task> --validate  # code enforces the contract, exit 1 on violation
    closeops apply <task>              # deterministic: render entries, bean-check

then commits and opens a pull request. **Ten accounting controls** run in GitHub Actions on every PR
and post their results as a comment. Anything the agent cannot resolve becomes an *exception* — a
proposed journal entry with evidence, a confidence, and a Neatlogs trace id — and the worker stops
and waits. The controller approves, rejects, or reclassifies in the PR diff; the worker re-applies;
the PR goes green; it merges. Approved exceptions become matching rules, so the next close needs
fewer humans.

**The deterministic sandwich:** code prepares and validates, the model only judges, and the model
never writes to the ledger. `apply` re-enforces the decision contract regardless of what the agent
said — auto-post only above 0.90 confidence, never to Suspense, never an invented amount.

## Architecture, tools, workflow, evaluation

- **Ledger:** Beancount 3.2 plain text in git; `Decimal` money throughout, never float.
- **Tasks:** `bank_rec` (exact / rule / split / partial / FX / payout / duplicate / unknown candidate
  kinds with evidence ids), `accruals` (service-period and materiality routing), `depreciation`
  (straight-line, half-month convention, fully-depreciated flagging).
- **Controls C1–C10:** ledger parses and balances · trial balance nets to zero · period lock ·
  evidence on every entry · materiality approval · no duplicates · bank reconciles against the
  statement plus outstanding cheques and deposits in transit · suspense is zero · no open exceptions ·
  processor balance nets.
- **Evaluation:** a four-tier funnel that isolates what the agent actually contributes, measured on
  116 real statement lines, plus a run 1 → run 2 comparison after rule learning.
- **Observability:** Neatlogs spans on every close step and control; each exception records its
  trace id.
- **Payments data:** Dodo Payments payout reconciliation — payouts, payments and refunds in the
  shape of Dodo's test-mode API, netting through an `Assets:Dodo:Balance` clearing account (C10).

## Measurable results

The September 2026 close, run end to end on 6 Sep 2026:

| | |
|---|---|
| Statement lines | 116 |
| Auto-posted | 94 |
| Exceptions raised for a human | 23 |
| Reconciling items | 4 |
| **Controls after review** | **10 / 10 green** |

**Funnel — what the agent adds:** exact amount match 60.3% → deterministic rules 79.3% → agent 81.0%
→ after controller review 100%. The remaining 19% arrive as *proposed entries with evidence and a
confidence*, not as a list of unmatched lines.

**Improvement over time:** run 1 81.0% → run 2 83.6% after learning two rules from the controller's
own decisions (Shenzhen POS → Office, Lagos ATM → Travel). Rule learning is deliberately
conservative — never from splits, partials, FX, payouts or duplicates, and material items stay
exceptions permanently.

**The human decision was load-bearing:** the controller approved all 23 exceptions but overruled the
agent on three — the duplicate Zoom charge to a refund receivable rather than a second expense, and
two unknown payees off Suspense. Blind-approving as proposed would have left 2,850 in Suspense and
failed control C8.

## Reliability and exception handling

`Decimal` money only; `bean-check` on every apply; auto-post threshold enforced in `apply`
independently of the agent; never auto-post to Suspense; no invented amounts (postings must match
the candidate); period lock; duplicate detection; human gate on every material posting and every
exception; controls fail closed on missing data (a control that cannot evaluate reports FAIL, not
PASS — a bug our own review caught and fixed). 128 tests, CI on every PR.

## How we used AO

AO was used in two roles, from the first commit to the last.

**As the build harness:** a build orchestrator read `plan.md`, planned two waves and spawned seven
workers — data-ledger, controls-ci, bank-rec, decide-llm, period-entries, docs, ci-gate — each on its
own branch, each opening a pull request. AO's configured reviewer reviewed those PRs and posted
verdicts to GitHub; on PR #4 it requested changes (documentation listed modules that did not exist
yet), the worker fixed it, and the re-review approved. CI failures and human review findings were
routed back to the owning session with `ao send` and fixed on the same branch — six substantive
findings, including controls that reported PASS on missing data, a Windows CRLF bug that made data
regeneration non-deterministic, a Neatlogs trace id that was always a fallback, and rule learning
that would have auto-posted an entire vendor payment to a fee account.

**As the product runtime:** a second orchestrator ran the close itself, spawning one worker per close
task. The bank-rec worker booked 94 entries, raised 22 exceptions, and stopped — AO's board showed it
waiting for a human. After the controller's review commit it re-applied and the same PR went green.

15 AO sessions (4 orchestrator, 11 worker), 10 pull requests, all merged. Full log with session ids,
verdicts and the routed findings: `docs/AO-LOG.md`.

**Honest note:** the depreciation close task was completed by the controller running the same four
CLI commands after two AO worker sessions failed to provision a workspace. bank-rec and accruals —
the two tasks with real judgment and exceptions — ran end to end through AO workers.

## Sponsor tools

- **Agent Orchestrator** — build harness and product runtime (above).
- **Neatlogs** — spans on every close step and control; every exception carries a trace id.
- **Dodo Payments** — payout reconciliation as a real close task. The demo used fixtures shaped like
  Dodo's test-mode API; `scripts/fetch_dodo.py --live` uses the `dodopayments` SDK against
  `test_mode`.

## What's next

Adapters onto real ledgers (QuickBooks / NetSuite export), prepaid amortisation and flux commentary
tasks, and approve/reject via PR comment commands so the controller never edits YAML.

## Team

Paridhi Pawaiya, Navaneeth _(add GitHub handles / Devpost names)_

## Cost note

Zero paid API spend. Model work ran inside AO worker sessions on a Claude Code subscription; the
`closeops` package never calls a paid model API and `anthropic` is not a dependency.
