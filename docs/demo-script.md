# Demo video script — Close-as-Code

**Target: 4:00. Record at 1080p, mic on, no music over speech. Upload unlisted to YouTube.**

Everything below is real and already on `main` — nothing needs to be staged or re-run. Have these
tabs open before you start recording:

1. AO desktop, `closeops` project, Board view
2. `https://github.com/PARIDHIPAWAIYA/closeops/pull/9` (the bank-rec close PR — the whole story)
3. `https://github.com/PARIDHIPAWAIYA/closeops/pulls?q=is%3Apr` (all 10 PRs)
4. `close-report.md` on `main`
5. `app.neatlogs.com` — the closeops workflow
6. A terminal in `C:\Users\pawai\closeops`

---

| Time | Show | Say |
|---|---|---|
| **0:00–0:20** | `data/bank/sep-2026.csv` beside `ledger/main.beancount` in the editor | "Month-end close is a person matching a hundred and sixteen bank lines to bills by hand, booking accruals and depreciation, then hoping nothing slipped. We made the close run as pull requests." |
| **0:20–0:50** | AO board; then the PR list showing 10 merged PRs | "Every part of this was built by AO workers, one per branch: the data and ledger, the controls, bank rec, the decision step, period entries, docs. AO's own reviewer reviewed each PR — it caught documentation claiming modules that didn't exist yet, and the worker fixed it. Ten pull requests, all merged." |
| **0:50–1:15** | AO orchestrator chat: the "Run September close" prompt; three worker cards appear on the board | "At runtime AO *is* the product. The controller types 'Run September close'. The orchestrator spawns one agent per close task — bank rec, accruals, depreciation — each on its own branch." |
| **1:15–1:45** | PR #9, scroll the diff of `ledger/2026-09/bank-rec.beancount`; point at `source:`, `confidence:`, `trace:` metadata | "Ninety-four entries booked automatically. Every entry links to its evidence — the statement line, the invoice id — plus the confidence and a Neatlogs trace id. Deterministic code prepares the candidates and validates the result; the model only makes the judgment calls it's allowed to make." |
| **1:45–2:10** | PR #9, the first CI comment: **Controls 7/10 FAIL**, C9 red, exceptions table | "Ten accounting controls run on every pull request. This one is red: twenty-two open exceptions. The agent stopped and waited. It does not guess." |
| **2:10–2:45** | `exceptions/bank-rec.yaml` in the diff; then the controller commit `09bb516` | "I review them as a diff. Splits, partials, FX differences, a duplicate charge, three unknown payees. I approve all twenty-two, but I overrule the agent on three: the duplicate Zoom charge goes to a refund receivable, not a second software expense; the Shenzhen card payments are office supplies; the Lagos ATM is travel. That's the judgment a controller is paid for." |
| **2:45–3:05** | PR #9, the second CI comment: **Controls 10/10 PASS** | "The worker re-applies and the same pull request goes green. Ten of ten. And this matters — blind-approving everything would have left two thousand eight hundred and fifty sitting in suspense and failed control eight. The human decision was load-bearing." |
| **3:05–3:20** | Neatlogs: the closeops workflow, a close session with its spans | "Every step of the close is traced, and every exception carries its trace id, so you can go from a journal entry back to the reasoning that produced it." |
| **3:20–3:40** | `close-report.md` funnel table; then the run 1 → run 2 table | "Sixty percent of lines match on amount alone. Rules take it to seventy-nine, the agent to eighty-one, and the controller closes the last nineteen percent. Then it learns: the two unknown payees I identified became rules, and the second run auto-posts eighty-four percent. Next month is cheaper than this month." |
| **3:40–4:00** | `docs/architecture.md` diagram | "Deterministic code prepares and validates, the agent only judges, git is the audit trail and the approval gate, and AO is both how we built it and how it runs. Next: adapters onto real ledgers — QuickBooks and NetSuite export." |

---

## Numbers to keep straight

- 116 statement lines · 94 auto-posted · 23 exceptions (22 bank-rec + 1 accruals) · 4 reconciling items
- Accruals: 5 booked = 17,850.00; the October-service bill refused; the 14,500 legal retainer held for approval
- Depreciation: 3 entries = 1,087.78; FA-004 flagged fully depreciated
- Controls: 7/10 red before review → **10/10 green** after
- Funnel: 60.3% → 79.3% → 81.0% → 100%
- Run 1 81.0% → run 2 83.6%, two rules learned
- Dodo: 2 payouts reconciled, fee split booked to `Expenses:PaymentProcessing`, C10 green
- 15 AO sessions (4 orchestrator, 11 worker), 10 PRs, all merged

## Do not claim

- Do not say the depreciation close ran through an AO worker — it did not (AO workspace provisioning
  failed twice; the controller ran the same four CLI commands). bank-rec and accruals did.
- Do not say Dodo live API data was used — the demo used fixtures in the shape of Dodo's test-mode
  API. `--live` exists and is wired.
- Do not say the agent "rejected" anything — all 23 exceptions were approved, 3 with reclassification.
