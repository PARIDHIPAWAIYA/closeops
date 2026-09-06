"""Ledger helpers + generated-dataset acceptance for the data-ledger worker.

Acceptance (plan.md Wave 1):
  * bean-check passes on ledger/main.beancount
  * trial balance nets to zero
  * CSV closing balance == statement-balance.json
  * trap counts match plan section 4 (~95 auto, ~20 exceptions, 4 reconciling)
"""
from __future__ import annotations

import csv
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from closeops import ledger, rules  # noqa: E402
import gen_data  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "mini.beancount"
MAIN = ROOT / "ledger" / "main.beancount"


# --------------------------- unit: ledger.py --------------------------------
def test_balance_at_date_on_fixture():
    entries, errors, _ = ledger.load_ledger(FIXTURE)
    assert errors == []
    assert ledger.balance(entries, "Assets:Bank:Operating") == Decimal("10000.00")
    # AR invoice is dated 2026-09-05; not counted before that date.
    assert ledger.balance(entries, "Assets:AR", "2026-09-04") == Decimal("0")
    assert ledger.balance(entries, "Assets:AR", "2026-09-30") == Decimal("2000.00")


def test_trial_balance_nets_zero_fixture():
    entries, _, _ = ledger.load_ledger(FIXTURE)
    assert ledger.trial_balance_net(entries, "2026-09-30") == Decimal("0")


def test_open_items_ap_and_ar():
    entries, _, _ = ledger.load_ledger(FIXTURE)
    ap = ledger.open_items(entries, "Liabilities:AP")
    assert len(ap) == 1
    assert ap[0]["invoice"] == "AP-0001"
    assert ap[0]["remaining"] == Decimal("1250.00")
    ar = ledger.open_items(entries, "Assets:AR")
    assert ar[0]["remaining"] == Decimal("-2000.00")  # sign-flipped control balance


def test_render_entry_roundtrips_through_beancount(tmp_path):
    text = ledger.render_entry(
        "2026-09-14", "ACME CORP", "split payment",
        [("Liabilities:AP", Decimal("1250.00")),
         ("Assets:Bank:Operating", Decimal("-1250.00"))],
        meta={"source": "data/bank/sep-2026.csv#L41", "confidence": "0.71"},
    )
    assert 'confidence: "0.71"' in text
    doc = FIXTURE.read_text(encoding="utf-8") + "\n" + text
    f = tmp_path / "combined.beancount"
    f.write_text(doc, encoding="utf-8")
    ok, out = ledger.bean_check(f)
    assert ok, out


def test_bean_check_module_form_reports_bad_file(tmp_path):
    bad = tmp_path / "bad.beancount"
    bad.write_text(
        'option "operating_currency" "USD"\n'
        "2026-08-01 open Assets:Bank:Operating USD\n"
        '2026-09-01 * "x" "unbalanced"\n'
        "  Assets:Bank:Operating  100.00 USD\n",
        encoding="utf-8",
    )
    ok, _ = ledger.bean_check(bad)
    assert ok is False


# --------------------------- unit: rules.py ---------------------------------
def test_load_rules_and_match():
    rs = rules.load_rules(ROOT / "data" / "rules" / "matching.yaml",
                          ROOT / "data" / "rules" / "learned.yaml")
    assert len(rs) >= 5
    hit = rules.match("GUSTO PAYROLL", rs)
    assert hit is not None and hit.account == "Expenses:Payroll:Salaries"
    assert rules.match("ZOOM VIDEO", rs).account == "Expenses:Software"
    assert rules.match("TOTALLY UNKNOWN VENDOR", rs) is None


# --------------------------- acceptance: dataset ----------------------------
def test_dataset_is_deterministic():
    a = gen_data.build_dataset(42)
    b = gen_data.build_dataset(42)
    assert a["statement_balance"] == b["statement_balance"]
    assert len(a["bank_lines"]) == len(b["bank_lines"])
    assert [l["amount"] for l in a["bank_lines"]] == [l["amount"] for l in b["bank_lines"]]


def test_trap_counts_match_plan():
    ds = gen_data.build_dataset(42)
    auto = sum(1 for l in ds["bank_lines"] if l["outcome"] == "auto")
    exc = sum(1 for l in ds["bank_lines"] if l["outcome"] == "exception")
    recon = len(ds["reconciling"])
    assert abs(auto - 95) <= 2, auto
    assert abs(exc - 20) <= 2, exc
    assert recon == 4, recon


def test_generated_ledger_bean_check_passes():
    assert MAIN.exists(), "run scripts/gen_data.py to generate ledger/main.beancount"
    ok, out = ledger.bean_check(MAIN)
    assert ok, out
    entries, errors, _ = ledger.load_ledger(MAIN)
    assert errors == []


def test_generated_trial_balance_nets_zero():
    entries, _, _ = ledger.load_ledger(MAIN)
    assert ledger.trial_balance_net(entries, "2026-09-30") == Decimal("0")


def test_csv_closing_equals_statement_balance():
    csv_path = ROOT / "data" / "bank" / "sep-2026.csv"
    bal_path = ROOT / "data" / "bank" / "statement-balance.json"
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    csv_closing = Decimal(rows[-1]["Balance"])
    json_closing = Decimal(json.loads(bal_path.read_text())["closing_balance"])
    assert csv_closing == json_closing


def test_dodo_fixtures_balance_for_c10():
    ds = gen_data.build_dataset(42)
    d = ds["dodo"]
    payments = sum(Decimal(p["total_amount"]) for p in d["payments"])
    refunds = sum(Decimal(r["amount"]) for r in d["refunds"])
    gross = sum(Decimal(p["amount"]) + Decimal(p["fee"]) for p in d["payouts"])
    # po_002 reports fee 0.00 by design, so add back the true inferred fee.
    assert payments - refunds == Decimal("15000.00")
    assert gross == Decimal("15000.00") - Decimal("150.00")  # missing fee on po_002


def test_invoices_have_six_unbooked_september_bills():
    ds = gen_data.build_dataset(42)
    unbooked_sep = [i for i in ds["invoices"]
                    if not i["booked"] and i["service_period"] == "2026-09"]
    october = [i for i in ds["invoices"]
               if not i["booked"] and i["service_period"] == "2026-10"]
    over_materiality = [i for i in unbooked_sep if Decimal(i["amount"]) >= Decimal("10000")]
    assert len(unbooked_sep) == 6
    assert len(october) == 1
    assert len(over_materiality) == 1


def test_fixed_assets_present():
    ds = gen_data.build_dataset(42)
    ids = {a["id"] for a in ds["fixed_assets"]}
    assert ids == {"FA-001", "FA-002", "FA-003", "FA-004"}
