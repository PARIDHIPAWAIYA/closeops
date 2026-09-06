# Close report — Northwind Labs Inc. (2026-09)
**Controls: 10/10 — PASS ✅**

## Controls
| # | Control | Result | Detail |
|---|---------|--------|--------|
| C1 | Ledger parses and balances | ✅ |  |
| C2 | Trial balance nets to zero | ✅ |  |
| C3 | Period lock | ✅ |  |
| C4 | Non-empty source | ✅ |  |
| C5 | Materiality approved | ✅ |  |
| C6 | No duplicates | ✅ |  |
| C7 | Bank reconciles | ✅ |  |
| C8 | Suspense is zero | ✅ |  |
| C9 | No open exceptions | ✅ |  |
| C10 | Dodo balance | ✅ |  |

**10/10 controls passed.**

## Metrics
- Controls: 10/10 passed
- Exceptions: 0 open, 23 approved, 0 rejected

| Tier | Auto-rate |
|------|-----------|
| Exact baseline | 60.3% |
| Rules only | 79.3% |
| Agent | 81.0% |
| After review | 100.0% |

- Run 1 auto-rate: 81.0% · Run 2 auto-rate: 83.6%

## Entries
- **bank-rec**: 116 entries
- **accruals**: 6 entries
- **depreciation**: 3 entries

## Exceptions
<details>
<summary>Exceptions (23)</summary>

| ID | Task | Issue | Confidence | Status |
|----|------|-------|-----------|--------|
| AC-001 | accruals | INV-001 (14500.00 "Rickard & Co") accrual is at/above materiality 10000.00 an... | 0.90 | approved |
| BR-001 | bank-rec | Line 5 (-12500.00 'GUSTO PAYROLL') - material amount - needs controller approval | 0.90 | approved |
| BR-002 | bank-rec | Line 25 (-6150.00 'SPLITCO 1 PAYMENT') - matches only as a split across multi... | 0.70 | approved |
| BR-003 | bank-rec | Line 31 (-6345.00 'SPLITCO 2 PAYMENT') - matches only as a split across multi... | 0.70 | approved |
| BR-004 | bank-rec | Line 36 (-6540.00 'SPLITCO 3 PAYMENT') - matches only as a split across multi... | 0.70 | approved |
| BR-005 | bank-rec | Line 41 (-6735.00 'SPLITCO 4 PAYMENT') - matches only as a split across multi... | 0.70 | approved |
| BR-006 | bank-rec | Line 42 (-3120.00 'PARTIAL 1 PAYMENT') - partial payment, remainder stays open | 0.65 | approved |
| BR-007 | bank-rec | Line 47 (-6930.00 'SPLITCO 5 PAYMENT') - matches only as a split across multi... | 0.70 | approved |
| BR-008 | bank-rec | Line 48 (-3204.00 'PARTIAL 2 PAYMENT') - partial payment, remainder stays open | 0.65 | approved |
| BR-009 | bank-rec | Line 53 (-3288.00 'PARTIAL 3 PAYMENT') - partial payment, remainder stays open | 0.65 | approved |
| BR-010 | bank-rec | Line 58 (-3372.00 'PARTIAL 4 PAYMENT') - partial payment, remainder stays open | 0.65 | approved |
| BR-011 | bank-rec | Line 59 (-6148.80 'EUROVEND 1 EUR PAYMENT') - amount differs from the bill wi... | 0.80 | approved |
| BR-012 | bank-rec | Line 64 (-6360.48 'EUROVEND 2 EUR PAYMENT') - amount differs from the bill wi... | 0.80 | approved |
| BR-013 | bank-rec | Line 69 (-6572.16 'EUROVEND 3 EUR PAYMENT') - amount differs from the bill wi... | 0.80 | approved |
| BR-014 | bank-rec | Line 71 (-499.00 'ZOOM VIDEO') - possible duplicate charge | 0.40 | approved |
| BR-015 | bank-rec | Line 76 (-820.00 'POS 4471 SHENZHEN') - unknown counterparty, no confident match | 0.20 | approved |
| BR-016 | bank-rec | Line 81 (-950.00 'POS 8823 SHENZHEN') - unknown counterparty, no confident match | 0.20 | approved |
| BR-017 | bank-rec | Line 86 (-1080.00 'ATM WITHDRAWAL LAGOS') - unknown counterparty, no confiden... | 0.20 | approved |
| BR-018 | bank-rec | Line 89 (-6958.00 'DISCOUNT 1 PAYMENT') - partial payment, remainder stays open | 0.65 | approved |
| BR-019 | bank-rec | Line 90 (9700.00 'DODO PAYOUT') - processor payout with fee missing from the ... | 0.95 | approved |
| BR-020 | bank-rec | Line 93 (-7114.80 'DISCOUNT 2 PAYMENT') - partial payment, remainder stays open | 0.65 | approved |
| BR-021 | bank-rec | Line 96 (-7271.60 'DISCOUNT 3 PAYMENT') - partial payment, remainder stays open | 0.65 | approved |
| BR-022 | bank-rec | Line 111 (4850.00 'DODO PAYOUT') - processor payout with fee missing from the... | 0.80 | approved |
</details>

## Reconciling items
**Outstanding cheques**
- cheque-1042 -3400.00
- cheque-1043 -1750.00
- cheque-1044 -980.00
**Deposits in transit**
- deposit-in-transit -4500.00
