Task: bank-rec, period 2026-09, branch close/bank-rec.
1. pip install -e .[llm] ; closeops prepare bank-rec
2. closeops decide bank-rec   (if it fails for lack of credentials: write work/bank-rec/decisions.json
   by hand per docs/controls.md "bank-rec" — auto-post only when score >= 0.9, otherwise exception
   with the best candidate as proposed_entry and a one-sentence rationale citing evidence ids.)
   Read decisions.json. If you disagree with any decision, change it and say why here in chat.
   Never invent amounts. Never auto-post to Equity:Suspense.
3. closeops apply bank-rec ; closeops check
4. Commit ledger/2026-09/bank-rec.beancount and exceptions/bank-rec.yaml, message
   "close(2026-09): bank-rec entries". Push. gh pr create with the summary table from close-report.md.
5. If CI fails only on C9 (open exceptions): reply "Needs controller review: N open exceptions"
   and stop. Any other control: fix, commit, push, once. Then stop.
