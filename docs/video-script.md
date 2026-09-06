# Demo video — full narration script

**Target 4:30. Read the right-hand column out loud. Everything in it is verified true.**

## Before you hit record

Open these, in this order, as tabs/windows you can alt-tab between:

1. **VS Code / editor** with `data/bank/sep-2026.csv` open
2. **AO desktop** — closeops project, Board view, left sidebar collapsed so the Ready column is visible
3. **GitHub PR #9** — https://github.com/PARIDHIPAWAIYA/closeops/pull/9
4. **GitHub PR list** — https://github.com/PARIDHIPAWAIYA/closeops/pulls?q=is%3Apr
5. **Neatlogs** — app.neatlogs.com, the `closeops` workflow
6. **The close package page** — the published dashboard link
7. Have `shot-06-close-running.png` and the timelapse video ready to cut in

Settings: 1080p, microphone on, no background music under speech. Speak slightly slower than feels
natural. If you fluff a line, pause two seconds and say it again — it's easy to cut.

---

## THE SCRIPT

### [0:00–0:25] The problem
**SHOW:** the bank CSV scrolling — 116 rows of `ACH DEBIT`, `WIRE`, `POS` lines.

> "This is a month of bank transactions for a small software company. A hundred and sixteen lines.
> Somewhere in the accounting team, a person is going to sit with this and match every single line
> against an unpaid bill or an invoice, by hand. Then book accruals, run depreciation, and hope
> nothing slipped through. That's month-end close, and it takes days.
>
> We made the close run as pull requests."

---

### [0:25–0:45] What it is
**SHOW:** `ledger/main.beancount` — the plain-text ledger.

> "The general ledger is a plain text file in a git repository. Agents propose journal entries as
> pull requests. Ten accounting controls run on every one of them. And anything the agent isn't
> sure about stops and waits for a human. We call it Close-as-Code."

---

### [0:45–1:20] AO as the build harness — SPONSOR
**SHOW:** the GitHub PR list — 10 merged PRs. Then cut to the timelapse for a few seconds.

> "Every line of this was built through Agent Orchestrator. A build orchestrator read our plan,
> split it into two waves, and spawned one worker per piece — the data and the ledger, the controls,
> bank reconciliation, the decision step, period entries, the docs. Each on its own branch, each
> opening its own pull request. Ten pull requests, all merged.
>
> AO's own reviewer reviewed them too. On the docs PR it requested changes — it caught that our
> architecture document listed modules that didn't exist in the code yet. The worker fixed it, and
> the re-review approved. That's not a rubber stamp, that's a real review.
>
> And when CI failed, AO routed the failure straight back to the worker that owned the branch.
> Six substantive problems got fixed that way — including controls that were reporting *pass* when
> the ledger was missing entirely. A check that passes on no data is worse than no check."

---

### [1:20–1:45] AO as the runtime — SPONSOR
**SHOW:** the AO board / `shot-06-close-running.png` with three workers running.

> "But AO isn't just how we built it. At close time, AO *is* the product.
>
> The controller types one sentence — 'Run September close.' The orchestrator spawns one agent per
> close task: bank reconciliation, accruals, depreciation. Each gets its own branch and its own
> workspace. This board is the close dashboard — you watch the month close in real time."

---

### [1:45–2:10] The entries, with evidence
**SHOW:** PR #9 → Files changed → scroll `ledger/2026-09/bank-rec.beancount`. Pause on one entry so
the metadata is readable.

> "Here's what came back. Ninety-four entries booked automatically.
>
> Look at a single entry. It carries the source — the exact line of the bank statement it came from.
> The invoice it pays. A confidence score. And a Neatlogs trace ID, so you can go from a number in
> the ledger all the way back to the reasoning that produced it. Nothing is booked without evidence."

---

### [2:10–2:35] The controls, and the agent stopping
**SHOW:** PR #9 → the first CI comment: **Controls 7/10 — FAIL**, C9 red.

> "Ten accounting controls run in CI on every pull request and post the result as a comment.
> Period lock. Materiality approval. Duplicate detection. Bank reconciliation. Suspense must be zero.
>
> And this one is red. Twenty-two open exceptions. The agent booked what it was confident about and
> then it *stopped*. It doesn't guess. Twenty-two lines it wouldn't post on its own authority."

---

### [2:35–3:05] The human review — the most important 30 seconds
**SHOW:** scroll `exceptions/bank-rec.yaml` in the diff, then the controller review commit.

> "So I review them, as a diff. Split payments. Partial payments. Currency differences. A possible
> duplicate charge. Three payments to counterparties it simply couldn't identify.
>
> I approve all twenty-two — but I overrule the agent on four of them. That duplicate Zoom charge:
> the money really did leave the account, so it isn't a second software expense, it's a receivable
> we're owed back. Those two Shenzhen card payments are our office supplies vendor. The Lagos ATM
> withdrawal is travel, not a mystery.
>
> And this is the part that matters. If I'd just approved everything exactly as proposed, two
> thousand eight hundred and fifty would have been left sitting in a suspense account, and control
> C8 would have failed. The human decision was load-bearing. It wasn't a rubber stamp."

---

### [3:05–3:20] Green
**SHOW:** PR #9 → the second CI comment: **Controls 10/10 — PASS**. Then the merge.

> "The worker re-applies with my approvals, and the same pull request goes green. Ten out of ten.
> Merged. And the whole conversation — what the agent proposed, what I overruled, and why — is
> permanently in the history. That's the audit trail, for free."

---

### [3:20–3:35] Neatlogs — SPONSOR
**SHOW:** Neatlogs, the closeops workflow, a close session with its spans.

> "Every step of the close is traced in Neatlogs — prepare, decide, apply, and each of the ten
> controls as its own span. All ninety-four entries and all twenty-two exceptions carry a real trace
> ID. When an auditor asks 'why is this number here', you can answer it."

---

### [3:35–3:50] Dodo Payments — SPONSOR
**SHOW:** the `DODO PAYOUT` lines in the bank CSV, then the booked entry with the fee split.

> "The company is a SaaS business, so its bank statement has payouts from its payment processor.
> We reconcile those against Dodo Payments' payout records — gross sales, minus refunds, minus the
> processing fee, equals the deposit that actually hits the bank. The fee books itself to payment
> processing expense, and control C10 checks the processor clearing account nets to zero.
> That's a real close task, not a bolted-on integration."

---

### [3:50–4:15] The numbers — measurable results
**SHOW:** the close package page — the funnel chart, then the run 1 → run 2 card.

> "Now, how much does the agent actually add? Most demos give you one big accuracy number with
> nothing to compare it to. Here's ours, honestly.
>
> Matching on amount alone gets you sixty percent. Add deterministic rules, seventy-nine. The agent
> takes it to eighty-one. And the controller closes the last nineteen percent to a hundred.
>
> The agent's own share is small — and I'd rather show you that than inflate it. What it really buys
> you is that the remaining nineteen percent arrive as *proposed entries with evidence and a
> confidence*, not as a list of unmatched rows.
>
> And it improves. Those two counterparties I identified became rules. On the second run it
> auto-posts eighty-three point six percent instead of eighty-one. Next month is cheaper than this
> month — and it refuses to learn unsafe rules: it will never learn from a split, an FX difference,
> or a materiality approval."

---

### [4:15–4:30] Close
**SHOW:** the close package page, scrolled to the control register with all ten green.

> "Deterministic code prepares the work and validates the result. The agent only makes the judgment
> calls, and it never writes to the ledger directly. Git is the approval gate and the audit trail.
> And AO is both how we built this and how it runs.
>
> Next step is adapters onto real ledgers — QuickBooks and NetSuite export — so this runs against
> books that already exist. Thanks for watching."

---

## Numbers — do not misquote these

| Fact | Value |
|---|---|
| Bank statement lines | 116 |
| Auto-posted | 94 |
| Exceptions to a human | 23 (22 bank-rec + 1 accruals) |
| Reclassified by the controller | 4 exceptions, 3 distinct decisions |
| Reconciling items | 4 (3 outstanding cheques, 1 deposit in transit) |
| Controls | 7/10 before review → **10/10** after |
| Funnel | 60.3% → 79.3% → 81.0% → 100% |
| Run 1 → run 2 | 81.0% → 83.6%, 2 rules learned |
| Suspense if blind-approved | 2,850.00 (would fail C8) |
| Accruals | 5 booked, 17,850.00; October bill refused; 14,500 retainer held for approval |
| Depreciation | 3 entries, 1,087.78; FA-004 flagged fully depreciated |
| AO | 15 sessions (4 orchestrator, 11 worker), 10 PRs, all merged |
| Tests | 128 passing, CI green on main |

## Do NOT say

- ❌ "All three close tasks ran through AO." → Two did (bank-rec, accruals). Depreciation was run by
  the controller after AO failed to provision a workspace twice. It's documented in `docs/AO-LOG.md`.
  If you want to mention it: *"one of the three hit an AO workspace bug, so I ran those same four
  commands myself — it's in the log."* Judges respect that far more than a gap they discover later.
- ❌ "We used the live Dodo API." → Fixtures shaped like Dodo's test-mode API. The `--live` path is
  written and wired but we never got a key. Say *"Dodo's payout records"* and leave it there, or say
  *"test-mode-shaped data"* if you want to be explicit.
- ❌ "The agent rejected the duplicate." → All 23 were approved; four were reclassified.
- ❌ "It's connected to a real accounting system." → Synthetic company, by design.

## If you only have 3 minutes

Cut: the Dodo section (3:35), and shorten the AO build section (0:45) to two sentences.
**Never cut:** the red-CI-to-human-review-to-green sequence (2:10–3:20). That is the entire pitch.
