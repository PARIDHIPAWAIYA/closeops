"""One test per control C1-C10, on hand-built fixtures (plan section 8)."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest

from closeops import controls
from closeops.controls import ControlResult
from tests.helpers import posting, txn, d, PERIOD_FILE

MATERIALITY = Decimal("10000.00")
AS_OF = date(2026, 9, 30)


# --- C1: ledger parses and balances -----------------------------------------

BALANCED_LEDGER = """\
option "title" "Test"
option "operating_currency" "USD"

2026-08-01 open Assets:Bank:Operating USD
2026-08-01 open Equity:OpeningBalances USD
2026-08-01 open Expenses:Rent USD

2026-08-01 * "Opening"
  Assets:Bank:Operating   10000.00 USD
  Equity:OpeningBalances

2026-09-05 * "Rent"
  source: "data/bank/sep-2026.csv#L5"
  Expenses:Rent            2000.00 USD
  Assets:Bank:Operating
"""

UNBALANCED_LEDGER = """\
option "title" "Test"
option "operating_currency" "USD"

2026-08-01 open Assets:Bank:Operating USD
2026-08-01 open Expenses:Rent USD

2026-09-05 * "Bad"
  Assets:Bank:Operating    100.00 USD
  Expenses:Rent            -50.00 USD
"""


def _write(tmp_path, text):
    p = tmp_path / "main.beancount"
    p.write_text(text, encoding="utf-8")
    return p


def test_c1_pass(tmp_path):
    r = controls.c1_ledger_balances(_write(tmp_path, BALANCED_LEDGER))
    assert isinstance(r, ControlResult)
    assert r.id == "C1"
    assert r.passed


def test_c1_fail_unbalanced(tmp_path):
    r = controls.c1_ledger_balances(_write(tmp_path, UNBALANCED_LEDGER))
    assert not r.passed


# --- C2: trial balance nets to zero -----------------------------------------

def test_c2_pass():
    entries = [txn(d("2026-09-10"), [
        posting("Expenses:Rent", "2000.00"),
        posting("Assets:Bank:Operating", "-2000.00"),
    ])]
    assert controls.c2_trial_balance(entries, AS_OF).passed


def test_c2_fail_nonzero():
    entries = [txn(d("2026-09-10"), [
        posting("Expenses:Rent", "2000.00"),
        posting("Assets:Bank:Operating", "-1900.00"),
    ])]
    assert not controls.c2_trial_balance(entries, AS_OF).passed


# --- C3: period lock --------------------------------------------------------

def test_c3_pass():
    entries = [txn(d("2026-09-05"), [
        posting("Expenses:Rent", "1.00"), posting("Assets:Bank:Operating", "-1.00"),
    ], filename=PERIOD_FILE)]
    assert controls.c3_period_lock(entries, date(2026, 9, 1)).passed


def test_c3_fail_pre_lock():
    entries = [txn(d("2026-08-31"), [
        posting("Expenses:Rent", "1.00"), posting("Assets:Bank:Operating", "-1.00"),
    ], filename=PERIOD_FILE)]
    assert not controls.c3_period_lock(entries, date(2026, 9, 1)).passed


def test_c3_ignores_non_period_files():
    # An August entry that lives outside ledger/2026-09/* is fine.
    entries = [txn(d("2026-08-31"), [
        posting("Expenses:Rent", "1.00"), posting("Assets:Bank:Operating", "-1.00"),
    ], filename="ledger/main.beancount")]
    assert controls.c3_period_lock(entries, date(2026, 9, 1)).passed


# --- C4: non-empty source ---------------------------------------------------

def test_c4_pass():
    entries = [txn(d("2026-09-05"), [
        posting("Expenses:Rent", "1.00"), posting("Assets:Bank:Operating", "-1.00"),
    ], source="data/bank/sep-2026.csv#L5", filename=PERIOD_FILE)]
    assert controls.c4_entry_source(entries).passed


def test_c4_fail_missing_source():
    entries = [txn(d("2026-09-05"), [
        posting("Expenses:Rent", "1.00"), posting("Assets:Bank:Operating", "-1.00"),
    ], filename=PERIOD_FILE)]
    assert not controls.c4_entry_source(entries).passed


# --- C5: materiality needs approved-by --------------------------------------

def test_c5_pass_with_approval():
    # approved-by sits at transaction level, as beancount metadata renders it.
    entries = [txn(d("2026-09-30"), [
        posting("Expenses:Legal", "14500.00"),
        posting("Liabilities:Accrued:Expenses", "-14500.00"),
    ], source="data/ap/invoices.json", filename=PERIOD_FILE,
        meta={"approved-by": "controller"})]
    assert controls.c5_materiality(entries, MATERIALITY).passed


def test_c5_fail_no_approval():
    entries = [txn(d("2026-09-30"), [
        posting("Expenses:Legal", "14500.00"),
        posting("Liabilities:Accrued:Expenses", "-14500.00"),
    ], source="data/ap/invoices.json", filename=PERIOD_FILE)]
    assert not controls.c5_materiality(entries, MATERIALITY).passed


def test_c5_pass_below_materiality():
    entries = [txn(d("2026-09-30"), [
        posting("Expenses:Rent", "2000.00"),
        posting("Assets:Bank:Operating", "-2000.00"),
    ], source="x", filename=PERIOD_FILE)]
    assert controls.c5_materiality(entries, MATERIALITY).passed


# --- C6: no duplicates ------------------------------------------------------

def _dup():
    return txn(d("2026-09-14"), [
        posting("Liabilities:AP", "1250.00"),
        posting("Assets:Bank:Operating", "-1250.00"),
    ], source="data/bank/sep-2026.csv#L41", filename=PERIOD_FILE)


def test_c6_fail_duplicate():
    assert not controls.c6_no_duplicates([_dup(), _dup()]).passed


def test_c6_pass_unique():
    e2 = txn(d("2026-09-15"), [
        posting("Liabilities:AP", "300.00"),
        posting("Assets:Bank:Operating", "-300.00"),
    ], source="data/bank/sep-2026.csv#L42", filename=PERIOD_FILE)
    assert controls.c6_no_duplicates([_dup(), e2]).passed


# --- C7: bank balance reconciles --------------------------------------------

def _bank_entries(closing_ledger):
    return [txn(d("2026-09-30"), [
        posting("Assets:Bank:Operating", str(closing_ledger)),
        posting("Equity:OpeningBalances", str(-Decimal(str(closing_ledger)))),
    ])]


def test_c7_pass():
    # ledger == statement + outstanding cheques - deposits in transit
    entries = _bank_entries("10000.00")
    reconciling = {"outstanding_cheques": ["1500.00"],
                   "deposits_in_transit": ["500.00"]}
    r = controls.c7_bank_reconciles(entries, "Assets:Bank:Operating",
                                    Decimal("9000.00"), reconciling, AS_OF)
    assert r.passed


def test_c7_fail_off_by_100():
    entries = _bank_entries("10000.00")
    reconciling = {"outstanding_cheques": ["1500.00"],
                   "deposits_in_transit": ["500.00"]}
    r = controls.c7_bank_reconciles(entries, "Assets:Bank:Operating",
                                    Decimal("9100.00"), reconciling, AS_OF)
    assert not r.passed


# --- C8: suspense == 0 ------------------------------------------------------

def test_c8_pass():
    entries = [txn(d("2026-09-10"), [
        posting("Equity:Suspense", "0.00"),
        posting("Assets:Bank:Operating", "0.00"),
    ])]
    assert controls.c8_suspense_zero(entries, "Equity:Suspense", AS_OF).passed


def test_c8_fail_nonzero():
    entries = [txn(d("2026-09-10"), [
        posting("Equity:Suspense", "250.00"),
        posting("Assets:Bank:Operating", "-250.00"),
    ])]
    assert not controls.c8_suspense_zero(entries, "Equity:Suspense", AS_OF).passed


# --- C9: no open exceptions -------------------------------------------------

RESOLVED_YAML = """\
- id: BR-001
  task: bank-rec
  status: approved
- id: BR-002
  task: bank-rec
  status: rejected
"""

OPEN_YAML = """\
- id: BR-003
  task: bank-rec
  status: open
"""


def test_c9_pass(tmp_path):
    (tmp_path / "bank-rec.yaml").write_text(RESOLVED_YAML, encoding="utf-8")
    assert controls.c9_no_open_exceptions(tmp_path).passed


def test_c9_fail_open(tmp_path):
    (tmp_path / "bank-rec.yaml").write_text(RESOLVED_YAML + OPEN_YAML, encoding="utf-8")
    assert not controls.c9_no_open_exceptions(tmp_path).passed


def test_c9_pass_empty_dir(tmp_path):
    assert controls.c9_no_open_exceptions(tmp_path).passed


# --- C10: Dodo balance ------------------------------------------------------

PAYMENTS = [{"total_amount": "1000.00"}, {"total_amount": "500.00"}]
REFUNDS = [{"amount": "100.00"}]
PAYOUTS = [{"payout_id": "po_1", "amount": "800.00", "fee": "20.00", "status": "success"}]


def _dodo_entries():
    # net Dodo:Balance = 1000 + 500 - 100 - (800+20) = 580
    return [
        txn(d("2026-09-02"), [posting("Assets:Dodo:Balance", "1000.00"),
                              posting("Income:Subscriptions", "-1000.00")]),
        txn(d("2026-09-05"), [posting("Assets:Dodo:Balance", "500.00"),
                              posting("Income:Subscriptions", "-500.00")]),
        txn(d("2026-09-08"), [posting("Assets:Dodo:Balance", "-100.00"),
                              posting("Income:Subscriptions", "100.00")]),
        txn(d("2026-09-28"), [posting("Assets:Bank:Operating", "800.00"),
                              posting("Expenses:PaymentProcessing", "20.00"),
                              posting("Assets:Dodo:Balance", "-820.00")]),
    ]


def test_c10_pass():
    r = controls.c10_dodo_balance(_dodo_entries(), PAYMENTS, REFUNDS, PAYOUTS,
                                  "Assets:Dodo:Balance", AS_OF)
    assert r.passed


def test_c10_fail_dropped_payout():
    r = controls.c10_dodo_balance(_dodo_entries(), PAYMENTS, REFUNDS, [],
                                  "Assets:Dodo:Balance", AS_OF)
    assert not r.passed


# --- run_all: absent data must never read as compliance ---------------------

MIN_LEDGER = """\
option "operating_currency" "USD"

2026-08-01 open Assets:Bank:Operating USD
2026-08-01 open Equity:OpeningBalances USD

2026-08-01 * "Opening"
  Assets:Bank:Operating   100.00 USD
  Equity:OpeningBalances
"""


def _build_min_repo(root, with_statement=True, with_dodo=True):
    (root / "ledger").mkdir(parents=True, exist_ok=True)
    (root / "ledger" / "main.beancount").write_text(MIN_LEDGER, encoding="utf-8")
    (root / "data" / "bank").mkdir(parents=True, exist_ok=True)
    if with_statement:
        (root / "data" / "bank" / "statement-balance.json").write_text(
            json.dumps({"closing": "100.00"}), encoding="utf-8")
    dodo = root / "data" / "dodo"
    dodo.mkdir(parents=True, exist_ok=True)
    if with_dodo:
        for name in ("payments", "refunds", "payouts"):
            (dodo / f"{name}.json").write_text("[]", encoding="utf-8")
    return root


def test_run_all_shape(tmp_path):
    results = controls.run_all(tmp_path)
    assert len(results) == 10
    assert all(isinstance(r, ControlResult) for r in results)
    assert [r.id for r in results] == [f"C{i}" for i in range(1, 11)]


def test_run_all_missing_ledger_fails_c2_to_c10(tmp_path):
    by_id = {r.id: r for r in controls.run_all(tmp_path)}
    for i in range(2, 11):
        assert not by_id[f"C{i}"].passed, f"C{i} must FAIL when ledger is missing"
        assert "skipped" in by_id[f"C{i}"].detail.lower()


def test_run_all_missing_statement_fails_c7(tmp_path):
    _build_min_repo(tmp_path, with_statement=False, with_dodo=True)
    by_id = {r.id: r for r in controls.run_all(tmp_path)}
    assert not by_id["C7"].passed
    assert "statement" in by_id["C7"].detail.lower()


def test_run_all_missing_dodo_fails_c10(tmp_path):
    _build_min_repo(tmp_path, with_statement=True, with_dodo=False)
    by_id = {r.id: r for r in controls.run_all(tmp_path)}
    assert not by_id["C10"].passed
    assert "dodo" in by_id["C10"].detail.lower()


def test_run_all_c9_passes_when_exceptions_absent(tmp_path):
    # With a valid ledger and no exceptions/ dir, "no open exceptions" is genuine.
    _build_min_repo(tmp_path)
    by_id = {r.id: r for r in controls.run_all(tmp_path)}
    assert by_id["C9"].passed
