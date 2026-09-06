Task: depreciation, period 2026-09, branch close/depreciation.
1. pip install -e .[trace] ; closeops prepare depreciation
2. closeops decide depreciation --packet ; read work/depreciation/packet.md and write work/depreciation/decisions.json:
   auto-post only when score >= 0.9, otherwise exception with the best candidate as proposed_entry
   and a one-sentence rationale citing evidence ids. Then closeops decide depreciation --validate and fix
   every violation it lists.
   Never invent amounts. Never auto-post to Equity:Suspense.
3. closeops apply depreciation ; closeops check
4. Commit ledger/2026-09/depreciation.beancount and exceptions/depreciation.yaml, message
   "close(2026-09): depreciation entries". Push. gh pr create with the summary table from close-report.md.
5. If CI fails only on C9 (open exceptions): reply "Needs controller review: N open exceptions"
   and stop. Any other control: fix, commit, push, once. Then stop.
