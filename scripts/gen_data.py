#!/usr/bin/env python
"""Generate the synthetic Northwind Labs dataset and opening ledger.

Everything is derived from ``--seed`` (default 42), so the dataset is
reproducible. One run writes:

  data/company.json
  data/bank/sep-2026.csv            bank statement (derived running balance)
  data/bank/statement-balance.json  opening/closing balance for control C7
  data/ap/invoices.json             AP subledger for accruals (~30, ~6 unbooked)
  data/fixed-assets.csv             FA-001..FA-004 for depreciation
  data/rules/matching.yaml          seed matching rules
  data/rules/learned.yaml           empty (Wave 2 writes here)
  data/dodo/{payouts,payments,refunds}.json   via fetch_dodo --fixture
  ledger/main.beancount             options, accounts, opening balances, August,
                                    September booked bills/invoices, includes
  ledger/2026-09/{bank-rec,accruals,depreciation}.beancount   stubs

The bank statement encodes traps T1..T15 from plan.md section 4. Each generated
bank line carries a ``trap`` and ``outcome`` tag (auto | exception); reconciling
items (outstanding cheques, deposit in transit) are ledger-only. verify_data.py
imports :func:`build_dataset` to count them.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import random
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_dodo  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CENTS = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENTS, rounding=ROUND_HALF_UP)


def fmt(d: Decimal) -> str:
    return f"{d:.2f}"


def write_lf(path: Path, text: str) -> None:
    """Write UTF-8 text with LF newlines regardless of platform.

    ``newline="\\n"`` disables the text-mode translation that would otherwise turn
    every ``\\n`` into ``\\r\\n`` on Windows, so regenerating the dataset does not
    dirty every file with line-ending-only diffs.
    """
    path.write_text(text, encoding="utf-8", newline="\n")


# ---------------------------------------------------------------------------
# Static reference data
# ---------------------------------------------------------------------------
ACCOUNTS = [
    "Assets:Bank:Operating",
    "Assets:AR",
    "Assets:Dodo:Balance",
    "Assets:Prepaid:Insurance",
    "Assets:Prepaid:Software",
    "Assets:FixedAssets:Computers",
    "Assets:FixedAssets:Furniture",
    "Assets:FixedAssets:AccumulatedDepreciation",
    "Liabilities:AP",
    "Liabilities:Accrued:Expenses",
    "Liabilities:Accrued:Payroll",
    "Liabilities:CreditCard",
    "Liabilities:DeferredRevenue",
    "Liabilities:SalesTaxPayable",
    "Equity:OpeningBalances",
    "Equity:RetainedEarnings",
    "Equity:Suspense",
    "Income:Subscriptions",
    "Income:Services",
    "Income:Interest",
    "Income:Other",
    "Expenses:Payroll:Salaries",
    "Expenses:Payroll:Taxes",
    "Expenses:Payroll:Benefits",
    "Expenses:Rent",
    "Expenses:Software",
    "Expenses:Hosting",
    "Expenses:Marketing",
    "Expenses:Travel",
    "Expenses:Meals",
    "Expenses:Insurance",
    "Expenses:Legal",
    "Expenses:Accounting",
    "Expenses:BankFees",
    "Expenses:PaymentProcessing",
    "Expenses:Depreciation",
    "Expenses:Office",
    "Expenses:Utilities",
    "Expenses:Contractors",
    "Expenses:FX",
    "Expenses:Telecom",
    "Expenses:Supplies",
]

EXPENSE_POOL = [
    "Expenses:Software", "Expenses:Hosting", "Expenses:Marketing",
    "Expenses:Travel", "Expenses:Meals", "Expenses:Legal", "Expenses:Accounting",
    "Expenses:Office", "Expenses:Utilities", "Expenses:Contractors",
    "Expenses:Telecom", "Expenses:Supplies", "Expenses:Insurance",
]

VENDORS = [
    "ACME CORP", "GLOBEX LLC", "INITECH", "UMBRELLA CO", "STARK INDS",
    "WAYNE ENT", "HOOLI INC", "VANDELAY", "SOYLENT", "CYBERDYNE",
    "TYRELL CORP", "OSCORP", "NAKATOMI", "GEKKO CAP", "BLUTH CO",
    "DUNDER MIFFLIN", "PRESTIGE WW", "WERNHAM HOGG", "MASSIVE DYN",
    "VEHEMENT CAP", "PIED PIPER", "ARAMARK", "STAPLES", "CINTAS",
    "GRAINGER", "FEDEX", "UPS STORE", "COMCAST", "VERIZON", "ATT BIZ",
    "PG AND E", "DELOITTE", "KPMG", "ADOBE", "ATLASSIAN", "TWILIO",
    "SEGMENT", "DATADOG", "SNOWFLAKE", "OKTA", "CLOUDFLARE", "STRIPE",
    "SALESFORCE", "HUBSPOT", "ZENDESK", "AIRTABLE", "DROPBOX", "ASANA",
    "MIRO", "LOOM", "LINEAR", "SENTRY", "PAGERDUTY",
]

CUSTOMERS = [
    "NORTHSTAR", "BLUE OCEAN", "EVERGREEN", "SUMMIT CO", "PINNACLE",
    "HORIZON", "BEACON", "KEYSTONE", "MERIDIAN", "VANGUARD",
    "CATALYST", "MOMENTUM", "APEX", "ZENITH", "NOVA GRP",
]

RULE_PAYEES = ["GITHUB", "NOTION", "SLACK", "FIGMA"]


# ---------------------------------------------------------------------------
# Bank lines + open items (traps T1..T15)
# ---------------------------------------------------------------------------
def build_bank_and_open_items(rng: random.Random) -> dict:
    ap_bills: list[dict] = []
    ar_invoices: list[dict] = []
    lines: list[dict] = []
    reconciling: list[dict] = []

    bill_seq = 0
    ar_seq = 0

    def sep(day: int) -> str:
        return f"2026-09-{day:02d}"

    def add_line(day, desc, amount, ref, trap, outcome):
        lines.append({
            "date": sep(day),
            "description": desc[:32],
            "amount": money(amount),
            "reference": ref,
            "trap": trap,
            "outcome": outcome,
        })

    def new_bill(date, vendor, amount, account, sp="2026-09"):
        nonlocal bill_seq
        bill_seq += 1
        b = {
            "id": f"AP-{bill_seq:04d}",
            "vendor": vendor,
            "date": date,
            "amount": money(amount),
            "account": account,
            "service_period": sp,
        }
        ap_bills.append(b)
        return b

    def new_ar(date, customer, amount):
        nonlocal ar_seq
        ar_seq += 1
        inv = {
            "id": f"AR-{ar_seq:04d}",
            "customer": customer,
            "date": date,
            "amount": money(amount),
        }
        ar_invoices.append(inv)
        return inv

    # -- T1: exact match to open AP bill (53, auto) ------------------------
    for i in range(53):
        vendor = VENDORS[i % len(VENDORS)]
        acct = EXPENSE_POOL[i % len(EXPENSE_POOL)]
        amt = money(Decimal(500) + Decimal(i) * Decimal("63.50"))
        b = new_bill(sep(1), vendor, amt, acct)
        day = 2 + (i % 26)
        add_line(day, f"{vendor} PAYMENT", -amt, f"ACH{1000 + i}", "T1", "auto")

    # -- T2: exact match to open AR invoice (15, auto) --------------------
    for i in range(15):
        cust = CUSTOMERS[i % len(CUSTOMERS)]
        amt = money(Decimal(1200) + Decimal(i) * Decimal("155.00"))
        new_ar(sep(1), cust, amt)
        day = 3 + (i % 25)
        add_line(day, f"DEPOSIT {cust}", amt, f"DEP{2000 + i}", "T2", "auto")

    # -- T3: recurring payee via rule (16, auto) -------------------------
    t3 = (
        [("GUSTO PAYROLL", money("12500.00")), ("GUSTO PAYROLL", money("3200.00")),
         ("WEWORK MEMBERSHIP", money("4100.00"))]
        + [(f"{p} SUBSCRIPTION", money(90 + n * 45)) for n, p in enumerate(RULE_PAYEES)]
    )
    while len(t3) < 16:
        p = RULE_PAYEES[len(t3) % len(RULE_PAYEES)]
        t3.append((f"{p} SUBSCRIPTION", money(120 + len(t3) * 30)))
    for i, (desc, amt) in enumerate(t3[:16]):
        add_line(2 + (i % 26), desc, -amt, f"CARD{3000 + i}", "T3", "auto")

    # -- T4: bank fee / interest (6, auto) -------------------------------
    for i in range(4):
        add_line(4 + i, "SERVICE FEE", money(-35 - i * 5), f"FEE{i}", "T4", "auto")
    for i in range(2):
        add_line(28, "INTEREST PAID", money(180 + i * 20), f"INT{i}", "T4", "auto")

    # -- T5: split payment, one line covers 2 bills (5, exception) -------
    for i in range(5):
        vendor = f"SPLITCO {i+1}"
        a1 = money(Decimal("4100.00") + Decimal(i) * Decimal("120"))
        a2 = money(Decimal("2050.00") + Decimal(i) * Decimal("75"))
        new_bill(sep(1), vendor, a1, "Expenses:Software")
        new_bill(sep(1), vendor, a2, "Expenses:Hosting")
        add_line(6 + i, f"{vendor} PAYMENT", -(a1 + a2), f"ACH{4000 + i}", "T5", "exception")

    # -- T6: partial payment, remainder open (4, exception) --------------
    for i in range(4):
        vendor = f"PARTIAL {i+1}"
        full = money(Decimal("5200.00") + Decimal(i) * Decimal("140"))
        new_bill(sep(1), vendor, full, "Expenses:Marketing")
        paid = money(full * Decimal("0.6"))
        add_line(9 + i, f"{vendor} PAYMENT", -paid, f"ACH{4100 + i}", "T6", "exception")

    # -- T7: FX / rounding within 1% or $5 (3, exception) ----------------
    for i in range(3):
        vendor = f"EUROVEND {i+1}"
        billed = money(Decimal("6100.00") + Decimal(i) * Decimal("210"))
        new_bill(sep(1), vendor, billed, "Expenses:Software")
        paid = money(billed * Decimal("1.008"))  # 0.8% FX difference
        add_line(12 + i, f"{vendor} EUR PAYMENT", -paid, f"WIRE{i}", "T7", "exception")

    # -- T8: duplicate charge, two ZOOM -499 same day --------------------
    add_line(14, "ZOOM VIDEO", money("-499.00"), "CARD8001", "T8", "auto")
    add_line(14, "ZOOM VIDEO", money("-499.00"), "CARD8002", "T8", "exception")

    # -- T9: unknown payee (3, exception) --------------------------------
    for i, desc in enumerate(["POS 4471 SHENZHEN", "POS 8823 SHENZHEN",
                              "ATM WITHDRAWAL LAGOS"]):
        add_line(15 + i, desc, money(-820 - i * 130), f"POS{i}", "T9", "exception")

    # -- T10: short-pay with 2% discount (3, exception) ------------------
    for i in range(3):
        vendor = f"DISCOUNT {i+1}"
        full = money(Decimal("7100.00") + Decimal(i) * Decimal("160"))
        new_bill(sep(1), vendor, full, "Expenses:Accounting")
        paid = money(full * Decimal("0.98"))
        add_line(18 + i, f"{vendor} PAYMENT", -paid, f"ACH{4200 + i}", "T10", "exception")

    # -- T11: outstanding cheques -> reconciling (3, not a bank line) ----
    for i, (num, amt) in enumerate([("1042", money("3400.00")),
                                    ("1043", money("1750.00")),
                                    ("1044", money("980.00"))]):
        reconciling.append({
            "type": "outstanding_cheque",
            "cheque_no": num,
            "date": sep(29),
            "amount": amt,
            "payee": f"CONTRACTOR {i+1}",
            "trap": "T11",
        })

    # -- T12: deposit in transit -> reconciling (1) ----------------------
    reconciling.append({
        "type": "deposit_in_transit",
        "date": sep(30),
        "amount": money("4500.00"),
        "customer": "LATE PAYER CO",
        "trap": "T12",
    })

    # -- T13: Sep line paying an August bill (2, auto) -------------------
    for i, (vendor, amt, acct) in enumerate([
        ("LEGAL EAGLE LLP", money("8100.00"), "Expenses:Legal"),
        ("ADWORKS MEDIA", money("8200.00"), "Expenses:Marketing"),
    ]):
        new_bill("2026-08-10", vendor, amt, acct)
        add_line(20 + i, f"{vendor} PAYMENT", -amt, f"ACH{4300 + i}", "T13", "auto")

    # -- T14: Dodo payouts (2: first auto, second exception) -------------
    payouts = fetch_dodo.build_fixtures()["payouts"]
    for i, po in enumerate(payouts):
        outcome = "auto" if i == 0 else "exception"
        add_line(18 + i * 7, "DODO PAYOUT", money(po["amount"]),
                 po["payout_id"], "T14", outcome)

    # -- T15: same amount, two vendors (2: one auto, one exception) ------
    new_bill(sep(1), "AWS", money("1800.00"), "Expenses:Hosting")
    new_bill(sep(1), "DATADOG", money("1800.00"), "Expenses:Software")
    add_line(22, "DATADOG SUBSCRIPTION", money("-1800.00"), "ACH4400", "T15", "auto")
    add_line(23, "AMZN AWS EC2 USAGE", money("-1800.00"), "ACH4401", "T15", "exception")

    return {
        "ap_bills": ap_bills,
        "ar_invoices": ar_invoices,
        "bank_lines": lines,
        "reconciling": reconciling,
    }


# ---------------------------------------------------------------------------
# Depreciation priors (booked through August so Wave 2 reads them)
# ---------------------------------------------------------------------------
def fixed_assets() -> list[dict]:
    return [
        {"id": "FA-001", "description": "MacBook Pro fleet", "cost": money("28000.00"),
         "salvage": money("0.00"), "life_months": 36, "in_service": "2026-02-01",
         "account": "Assets:FixedAssets:Computers"},
        {"id": "FA-002", "description": "Office desks", "cost": money("9600.00"),
         "salvage": money("0.00"), "life_months": 60, "in_service": "2026-03-15",
         "account": "Assets:FixedAssets:Furniture"},
        {"id": "FA-003", "description": "Server rack", "cost": money("12000.00"),
         "salvage": money("1200.00"), "life_months": 36, "in_service": "2026-09-20",
         "account": "Assets:FixedAssets:Computers"},
        {"id": "FA-004", "description": "Legacy laptops", "cost": money("4800.00"),
         "salvage": money("0.00"), "life_months": 36, "in_service": "2023-08-01",
         "account": "Assets:FixedAssets:Computers"},
    ]


def monthly_dep(asset: dict) -> Decimal:
    return money((asset["cost"] - asset["salvage"]) / asset["life_months"])


def accumulated_through_july(assets: list[dict]) -> Decimal:
    """Prior accumulated depreciation through 2026-07-31."""
    total = Decimal("0")
    fa = {a["id"]: a for a in assets}
    total += monthly_dep(fa["FA-001"]) * 6          # Feb..Jul
    total += monthly_dep(fa["FA-002"]) * 5          # Mar..Jul (full months)
    total += fa["FA-004"]["cost"]                   # fully depreciated by 2026-07
    return money(total)


def august_depreciation(assets: list[dict]) -> Decimal:
    fa = {a["id"]: a for a in assets}
    return money(monthly_dep(fa["FA-001"]) + monthly_dep(fa["FA-002"]))


# ---------------------------------------------------------------------------
# AP subledger for accruals (independent from ledger open items)
# ---------------------------------------------------------------------------
def build_invoices(rng: random.Random) -> list[dict]:
    invoices: list[dict] = []
    # 6 unbooked September-service bills drive accruals.
    unbooked_sep = [
        ("Legal retainer", "Rickard & Co", "14500.00", "Expenses:Legal"),      # > materiality
        ("Hosting overage", "AWS", "3200.00", "Expenses:Hosting"),
        ("Contractor sprint", "DevShop", "6800.00", "Expenses:Contractors"),
        ("Marketing agency", "AdWorks", "4500.00", "Expenses:Marketing"),
        ("Utilities", "PG&E", "1250.00", "Expenses:Utilities"),
        ("Travel reimburse", "Concur", "2100.00", "Expenses:Travel"),
    ]
    for i, (desc, vendor, amt, acct) in enumerate(unbooked_sep):
        invoices.append({
            "id": f"INV-{i+1:03d}", "vendor": vendor, "date": "2026-09-28",
            "due": "2026-10-15", "amount": amt, "currency": "USD",
            "account": acct, "service_period": "2026-09", "booked": False,
            "description": desc,
        })
    # 1 unbooked October-service bill: must NOT accrue.
    invoices.append({
        "id": "INV-007", "vendor": "Insurance Plus", "date": "2026-09-29",
        "due": "2026-10-31", "amount": "3600.00", "currency": "USD",
        "account": "Expenses:Insurance", "service_period": "2026-10", "booked": False,
        "description": "October premium billed early",
    })
    # ~23 booked September bills for realism.
    for i in range(23):
        vendor = VENDORS[i % len(VENDORS)]
        acct = EXPENSE_POOL[i % len(EXPENSE_POOL)]
        amt = money(Decimal(900) + Decimal(i) * Decimal("110.00"))
        invoices.append({
            "id": f"INV-{i+8:03d}", "vendor": vendor.title(), "date": "2026-09-12",
            "due": "2026-10-12", "amount": fmt(amt), "currency": "USD",
            "account": acct, "service_period": "2026-09", "booked": True,
            "description": f"{vendor.title()} September services",
        })
    return invoices


# ---------------------------------------------------------------------------
# Ledger construction
# ---------------------------------------------------------------------------
def build_ledger_txns(ds: dict) -> tuple[list[dict], dict]:
    """Return (txns, opening_amounts). Each txn: date, payee, narration, meta,
    postings [(account, Decimal|None)]. Opening plug goes to Equity:OpeningBalances."""
    assets = ds["fixed_assets"]
    dodo = ds["dodo"]

    opening = {
        "Assets:Bank:Operating": money("500000.00"),
        "Assets:AR": money("40000.00"),
        "Assets:Dodo:Balance": money("0.00"),
        "Assets:Prepaid:Insurance": money("12000.00"),
        "Assets:Prepaid:Software": money("6000.00"),
        "Assets:FixedAssets:Computers": money("32800.00"),   # FA-001 + FA-004
        "Assets:FixedAssets:Furniture": money("9600.00"),    # FA-002
        "Assets:FixedAssets:AccumulatedDepreciation": -accumulated_through_july(assets),
        "Liabilities:CreditCard": money("-8000.00"),
        "Liabilities:DeferredRevenue": money("-15000.00"),
    }
    plug = -sum(opening.values())
    opening_postings = [(a, v) for a, v in opening.items()]
    opening_postings.append(("Equity:OpeningBalances", money(plug)))

    txns: list[dict] = []

    def add(date, payee, narr, postings, meta=None):
        txns.append({"date": date, "payee": payee, "narration": narr,
                     "postings": postings, "meta": meta or {}})

    add("2026-08-01", "Opening", "Opening balances", opening_postings)

    # -- August activity (fully booked and balanced) ---------------------
    add("2026-08-05", "Gusto", "August payroll", [
        ("Expenses:Payroll:Salaries", money("60000.00")),
        ("Expenses:Payroll:Taxes", money("9000.00")),
        ("Expenses:Payroll:Benefits", money("4000.00")),
        ("Assets:Bank:Operating", money("-73000.00")),
    ], {"source": "data/bank/aug-2026.csv"})
    add("2026-08-05", "WeWork", "August rent", [
        ("Expenses:Rent", money("12000.00")),
        ("Assets:Bank:Operating", money("-12000.00")),
    ], {"source": "data/bank/aug-2026.csv"})
    add("2026-08-15", "Northstar", "August AR collection", [
        ("Assets:Bank:Operating", money("30000.00")),
        ("Assets:AR", money("-30000.00")),
    ], {"source": "data/bank/aug-2026.csv"})
    add("2026-08-20", "Adobe", "August software (card)", [
        ("Expenses:Software", money("3000.00")),
        ("Liabilities:CreditCard", money("-3000.00")),
    ], {"source": "data/ap/invoices.json"})
    add("2026-08-31", "Depreciation", "August depreciation", [
        ("Expenses:Depreciation", august_depreciation(assets)),
        ("Assets:FixedAssets:AccumulatedDepreciation", -august_depreciation(assets)),
    ], {"source": "data/fixed-assets.csv"})

    # -- Open AP bills (bank-rec targets), booked & unpaid ---------------
    for b in ds["ap_bills"]:
        add(b["date"], b["vendor"], f"{b['vendor']} bill", [
            (b["account"], b["amount"]),
            ("Liabilities:AP", -b["amount"]),
        ], {"invoice": b["id"], "source": "data/ap/invoices.json"})

    # -- Open AR invoices (bank-rec targets), booked & unpaid ------------
    for inv in ds["ar_invoices"]:
        add(inv["date"], inv["customer"], f"{inv['customer']} invoice", [
            ("Assets:AR", inv["amount"]),
            ("Income:Subscriptions", -inv["amount"]),
        ], {"invoice": inv["id"], "source": "data/ap/invoices.json"})

    # -- Dodo payments and refunds (build Dodo:Balance for C10) ----------
    for p in dodo["payments"]:
        amt = money(p["total_amount"])
        add(p["created_at"], "Dodo", f"Subscription {p['payment_id']}", [
            ("Assets:Dodo:Balance", amt),
            ("Income:Subscriptions", -amt),
        ], {"source": "data/dodo/payments.json", "dodo": p["payment_id"]})
    for r in dodo["refunds"]:
        amt = money(r["amount"])
        add(r["created_at"], "Dodo", f"Refund {r['refund_id']}", [
            ("Income:Subscriptions", amt),
            ("Assets:Dodo:Balance", -amt),
        ], {"source": "data/dodo/refunds.json", "dodo": r["refund_id"]})

    # -- Reconciling ledger entries (not on the September statement) ------
    for item in ds["reconciling"]:
        if item["type"] == "outstanding_cheque":
            add(item["date"], item["payee"], f"Cheque #{item['cheque_no']}", [
                ("Expenses:Contractors", item["amount"]),
                ("Assets:Bank:Operating", -item["amount"]),
            ], {"source": "data/bank/reconciling.json",
                "reconciling": f"cheque-{item['cheque_no']}"})
        else:  # deposit_in_transit
            add(item["date"], item["customer"], "Deposit in transit", [
                ("Assets:Bank:Operating", item["amount"]),
                ("Assets:AR", -item["amount"]),
            ], {"source": "data/bank/reconciling.json",
                "reconciling": "deposit-in-transit"})

    return txns, opening


def render_ledger(ds: dict) -> str:
    txns, opening = build_ledger_txns(ds)
    out = io.StringIO()
    out.write('option "title" "Northwind Labs Inc."\n')
    out.write('option "operating_currency" "USD"\n\n')
    for acct in ACCOUNTS:
        out.write(f"2026-08-01 open {acct} USD\n")
    out.write("\n")

    # Balance assertions validate the generator (start-of-day = post-opening).
    balances = [
        ("2026-08-02", "Assets:Bank:Operating", opening["Assets:Bank:Operating"]),
        ("2026-08-02", "Assets:AR", opening["Assets:AR"]),
    ]

    directives = []
    for t in txns:
        directives.append(("txn", t["date"], t))
    for date, acct, amt in balances:
        directives.append(("balance", date, (acct, amt)))
    directives.sort(key=lambda d: (d[1], 0 if d[0] == "txn" else 1))

    for kind, date, payload in directives:
        if kind == "balance":
            acct, amt = payload
            out.write(f"{date} balance {acct}  {fmt(amt)} USD\n\n")
            continue
        t = payload
        out.write(f'{date} * "{t["payee"]}" "{t["narration"]}"\n')
        for k, v in t["meta"].items():
            out.write(f'  {k}: "{v}"\n')
        for acct, amt in t["postings"]:
            if amt is None:
                out.write(f"  {acct}\n")
            else:
                out.write(f"  {acct}  {fmt(amt)} USD\n")
        out.write("\n")

    out.write('include "2026-09/bank-rec.beancount"\n')
    out.write('include "2026-09/accruals.beancount"\n')
    out.write('include "2026-09/depreciation.beancount"\n')
    return out.getvalue()


# ---------------------------------------------------------------------------
# Assemble + write
# ---------------------------------------------------------------------------
def build_dataset(seed: int = 42) -> dict:
    rng = random.Random(seed)
    bank = build_bank_and_open_items(rng)
    ds = {
        "seed": seed,
        "company": {
            "name": "Northwind Labs Inc.",
            "currency": "USD",
            "period": "2026-09",
            "period_lock_before": "2026-09-01",
            "materiality": "10000.00",
            "bank_account": "Assets:Bank:Operating",
            "suspense_account": "Equity:Suspense",
            "processor_clearing": "Assets:Dodo:Balance",
            "headcount": 25,
            "description": "25-person B2B SaaS",
        },
        "fixed_assets": fixed_assets(),
        "invoices": build_invoices(rng),
        "dodo": fetch_dodo.build_fixtures(seed),
        **bank,
    }

    # Derive the bank statement running balance from the ledger's September
    # starting bank balance (opening + August activity).
    _, opening = build_ledger_txns(ds)
    aug_bank_delta = money("-73000.00") + money("-12000.00") + money("30000.00")
    opening_bank_sep1 = money(opening["Assets:Bank:Operating"] + aug_bank_delta)

    running = opening_bank_sep1
    ordered = sorted(range(len(ds["bank_lines"])),
                     key=lambda i: (ds["bank_lines"][i]["date"], i))
    for i in ordered:
        running = money(running + ds["bank_lines"][i]["amount"])
        ds["bank_lines"][i]["balance"] = running
    ds["bank_lines"] = [ds["bank_lines"][i] for i in ordered]

    ds["statement_balance"] = {
        "account": "Assets:Bank:Operating",
        "currency": "USD",
        "opening_date": "2026-09-01",
        "opening_balance": fmt(opening_bank_sep1),
        "closing_date": "2026-09-30",
        "closing_balance": fmt(running),
    }
    return ds


def write_all(ds: dict) -> None:
    (ROOT / "data" / "bank").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "ap").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "rules").mkdir(parents=True, exist_ok=True)
    (ROOT / "ledger" / "2026-09").mkdir(parents=True, exist_ok=True)

    write_lf(ROOT / "data" / "company.json",
             json.dumps(ds["company"], indent=2) + "\n")

    # bank CSV
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["Date", "Description", "Amount", "Balance", "Reference"])
    for ln in ds["bank_lines"]:
        w.writerow([ln["date"], ln["description"], fmt(ln["amount"]),
                    fmt(ln["balance"]), ln["reference"]])
    write_lf(ROOT / "data" / "bank" / "sep-2026.csv", buf.getvalue())

    write_lf(ROOT / "data" / "bank" / "statement-balance.json",
             json.dumps(ds["statement_balance"], indent=2) + "\n")

    write_lf(ROOT / "data" / "ap" / "invoices.json",
             json.dumps(ds["invoices"], indent=2) + "\n")

    # fixed assets CSV
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["id", "description", "cost", "salvage", "life_months",
                "in_service", "account"])
    for a in ds["fixed_assets"]:
        w.writerow([a["id"], a["description"], fmt(a["cost"]), fmt(a["salvage"]),
                    a["life_months"], a["in_service"], a["account"]])
    write_lf(ROOT / "data" / "fixed-assets.csv", buf.getvalue())

    # matching rules
    matching = """\
# Seed matching rules for recurring bank lines.
# Each rule: match (regex, case-insensitive), account, confidence.
- match: "GUSTO"
  account: "Expenses:Payroll:Salaries"
  confidence: 0.90
- match: "WEWORK"
  account: "Expenses:Rent"
  confidence: 0.90
- match: "SERVICE FEE"
  account: "Expenses:BankFees"
  confidence: 0.95
- match: "INTEREST PAID"
  account: "Income:Interest"
  confidence: 0.95
- match: "GITHUB|NOTION|SLACK|ZOOM|FIGMA"
  account: "Expenses:Software"
  confidence: 0.90
"""
    write_lf(ROOT / "data" / "rules" / "matching.yaml", matching)
    write_lf(ROOT / "data" / "rules" / "learned.yaml",
             "# Learned rules are appended by Wave 2 (rerun). Starts empty.\n[]\n")

    # Dodo fixtures
    fetch_dodo.write_fixtures(ds["dodo"])

    # ledger
    write_lf(ROOT / "ledger" / "main.beancount", render_ledger(ds))
    for task in ("bank-rec", "accruals", "depreciation"):
        stub = ROOT / "ledger" / "2026-09" / f"{task}.beancount"
        write_lf(stub,
                 f";; ledger/2026-09/{task}.beancount\n"
                 f";; Written by the {task} worker (Wave 2). Placeholder so main parses.\n")


def summary(ds: dict) -> dict:
    outcomes = {"auto": 0, "exception": 0}
    for ln in ds["bank_lines"]:
        outcomes[ln["outcome"]] = outcomes.get(ln["outcome"], 0) + 1
    return {
        "bank_lines": len(ds["bank_lines"]),
        "auto": outcomes["auto"],
        "exceptions": outcomes["exception"],
        "reconciling": len(ds["reconciling"]),
        "ap_bills": len(ds["ap_bills"]),
        "ar_invoices": len(ds["ar_invoices"]),
        "invoices": len(ds["invoices"]),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generate the closeops dataset")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)

    ds = build_dataset(args.seed)
    write_all(ds)
    s = summary(ds)
    print(f"seed={args.seed}  wrote dataset under {ROOT}")
    print(f"  bank lines: {s['bank_lines']}  auto: {s['auto']}  "
          f"exceptions: {s['exceptions']}  reconciling: {s['reconciling']}")
    print(f"  ap bills: {s['ap_bills']}  ar invoices: {s['ar_invoices']}  "
          f"invoices.json: {s['invoices']}")
    print(f"  bank closing balance: {ds['statement_balance']['closing_balance']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
