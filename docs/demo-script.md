# Demo script and Devpost outline

Shot list for the demo video (plan.md §11) and the Devpost submission outline (plan.md §12). Record
the runtime close before cutting the video; leave the results placeholders in the README filled in
first.

---

## Demo video (≤ 5:00)

1080p, mic on, no music over speech, unlisted YouTube. The video must show three things the rubric
asks for: AO build sessions, the working product, and the evaluation/improvement process.

| Time | Shot | Say |
|---|---|---|
| 0:00 | Bank CSV beside the ledger | "Month-end close is a person matching 120 bank lines to bills by hand. We made the close run as pull requests." |
| 0:20 | AO board during the build; session list | "Every part was built by AO workers on their own branches: data, controls, bank rec, the decision step, period entries, docs. CI comments went back to the owning worker." |
| 0:50 | Orchestrator chat: "Run September close"; three workers appear | "At runtime, AO is the product." |
| 1:15 | PR diff of `bank-rec.beancount`; CI comment, C9 red | "Every entry links to its evidence. Ten controls on every PR. Twenty lines needed a human." |
| 1:45 | **Neatlogs** session: prepare → decide → apply → check spans; one exception's `trace:` id | "Every step of the close is traced, and every exception links to its trace." |
| 2:00 | Needs You; approve a split, reject the duplicate; push; green; merge | "The agent proposes with a confidence and waits. Only approved entries reach the ledger." |
| 2:35 | **Dodo payout** line reconciled: net = gross − refunds − fee, fee booked | "Processor payouts reconcile against Dodo's payout records; the fee books itself." |
| 2:55 | Accruals PR (materiality exception; October bill refused); depreciation green | — |
| 3:20 | `close-report.md`: funnel 62 → 74 → 80 → 100; **run 1 → run 2** 80 → 87 | "Approved exceptions become rules. The second close needs fewer humans." |
| 3:50 | Architecture (12 s) | "Code prepares and validates, the model only judges, git is the audit trail and the gate." |

> Funnel numbers above are plan targets. Use the real numbers from `close-report.md` /
> `metrics.json` after the recorded close — do not narrate targets as results.

### Checklist before recording

- [ ] Runtime close has actually run; `close-report.md` and `metrics.json` are on `main`.
- [ ] `closeops check` on `main` is 10/10 green.
- [ ] AO board shows build workers + three close workers + report worker (`ao session ls --all`).
- [ ] One red CI comment (C9 open exceptions) and one green CI comment are visible.
- [ ] Neatlogs session shows the four spans and an exception trace id.
- [ ] A Dodo payout line is visibly reconciled with the fee split.

### The human review loop (what 2:00 shows)

1. `close(2026-09): bank-rec` is red on C9 with ~20 open exceptions; the worker reports "Needs
   controller review".
2. The controller edits `exceptions/bank-rec.yaml`: approve the splits / partials / FX / discount /
   payout-fee; reject the duplicate and the Shenzhen POS with notes; commit to the branch.
3. In AO chat: "exceptions reviewed, apply and push" → the worker re-runs `apply` (which learns
   rules), CI goes green, merge from AO.
4. Accruals has one materiality item, handled the same way; depreciation is green first time.
5. The report PR shows ten controls green plus the funnel and run 1 / run 2.

---

## Devpost outline

**Name:** Close-as-Code
**Tagline:** "Month-end close that runs as reviewed pull requests, orchestrated by AO."
**Track:** Track 2.

- **Problem / users** — Controllers and outsourced accounting firms close monthly from bank exports,
  AP bills, processor payouts, and asset schedules, matching by hand. (plan.md §1.)
- **What it does** — A month-end close that runs as pull requests over a plain-text Beancount ledger
  in git. AO spawns one agent worker per task; deterministic code prepares and validates, the model
  only makes judgment calls under an enforced contract; ten controls run in CI; the controller
  reviews diffs and approves exceptions; approved exceptions become rules so the next close is more
  automated. (plan.md §0.)
- **How we built it with AO** — Build waves (data-ledger + controls-ci, then bank-rec, decide-llm,
  period-entries, docs), one worker per branch, the PR/CI loop routing comments back to the owning
  worker, and AO as the runtime for the close itself. Session list screenshot.
- **Architecture** — The deterministic sandwich, the ten controls, the exception contract, the
  0.9 auto-post threshold, demotion. (plan.md §2; docs/architecture.md.)
- **Evaluation and results** — The four-tier funnel (exact → rules-only → agent → after review),
  run 1 → run 2 improvement, proposal-acceptance rate, and controls green. Use the real numbers.
- **Reliability** — Decimal money (never float), `bean-check` on every apply, the 0.9 auto-post
  threshold, suspense forced to zero, the period lock, duplicate detection, and the human gate on
  materiality and on every exception.
- **Sponsor tools** —
  - **AO** is the runtime: the controller runs the close by talking to an AO orchestrator; workers,
    branches, the Kanban board, and the "Needs You" queue are the product surface.
  - **Neatlogs** traces every judgment; each exception links to its trace.
  - **Dodo Payments** is the payout source (test-mode API via the SDK, or seeded fixture — state
    which was used).
- **What's next** — ERP adapters, prepaids, flux commentary.
- **Team** — members and roles.
- **Links** — repo, demo video, close-report.md.

### AO evidence to attach

- `ao session ls --all` screenshot (build workers + close workers + report worker).
- Kanban board with the "Needs You" column populated.
- One red CI comment and one green CI comment.
- The merged-PR list.
