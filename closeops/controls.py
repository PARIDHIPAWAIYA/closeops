"""Accounting controls C1-C10 (plan section 8).

Each control returns a ControlResult. Controls read the beancount ledger and a
handful of JSON/YAML files directly, so they do not depend on the task modules.
Money is always Decimal, never float.

ControlResult is defined here so this module stands alone; during integration it
can be re-exported from models.py without changing callers.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Sequence

import yaml
from beancount import loader
from beancount.core import data

ZERO = Decimal("0")
CENT = Decimal("0.005")  # tolerance for money comparisons
PERIOD_TAG = "2026-09"
PERIOD_END = date(2026, 9, 30)


@dataclass
class ControlResult:
    id: str
    name: str
    passed: bool
    detail: str = ""

    def as_dict(self) -> dict:
        return {"id": self.id, "name": self.name,
                "passed": self.passed, "detail": self.detail}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _transactions(entries: Iterable) -> list:
    return [e for e in entries if isinstance(e, data.Transaction)]


def _filename(entry) -> str:
    meta = getattr(entry, "meta", None) or {}
    return (meta.get("filename") or "").replace("\\", "/")


def _is_period(entry, period_tag: str = PERIOD_TAG) -> bool:
    return period_tag in _filename(entry)


def account_balance(entries: Iterable, account: str,
                    as_of: date = PERIOD_END) -> Decimal:
    """Sum of postings to `account` for transactions dated on/before `as_of`."""
    total = ZERO
    for e in _transactions(entries):
        if e.date > as_of:
            continue
        for p in e.postings:
            if p.account == account and p.units is not None:
                total += p.units.number
    return total


def _dec(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _sum(values: Iterable) -> Decimal:
    return sum((_dec(v) for v in values), ZERO)


# --------------------------------------------------------------------------- #
# C1 — ledger parses and balances
# --------------------------------------------------------------------------- #

def c1_ledger_balances(ledger_path) -> ControlResult:
    path = Path(ledger_path)
    if not path.exists():
        return ControlResult("C1", "Ledger parses and balances", False,
                             f"ledger not found: {path}")
    _, errors, _ = loader.load_file(str(path))
    if not errors:
        return ControlResult("C1", "Ledger parses and balances", True)
    msgs = "; ".join(getattr(e, "message", str(e)) for e in errors[:3])
    return ControlResult("C1", "Ledger parses and balances", False,
                         f"{len(errors)} error(s): {msgs}")


# --------------------------------------------------------------------------- #
# C2 — trial balance nets to zero
# --------------------------------------------------------------------------- #

def c2_trial_balance(entries: Sequence, as_of: date = PERIOD_END) -> ControlResult:
    total = ZERO
    for e in _transactions(entries):
        if e.date > as_of:
            continue
        for p in e.postings:
            if p.units is not None:
                total += p.units.number
    passed = abs(total) < CENT
    detail = "" if passed else f"trial balance nets to {total}"
    return ControlResult("C2", "Trial balance nets to zero", passed, detail)


# --------------------------------------------------------------------------- #
# C3 — period lock
# --------------------------------------------------------------------------- #

def c3_period_lock(entries: Sequence, period_lock_before: date,
                   period_tag: str = PERIOD_TAG) -> ControlResult:
    bad = [e for e in _transactions(entries)
           if _is_period(e, period_tag) and e.date < period_lock_before]
    if not bad:
        return ControlResult("C3", "Period lock", True)
    where = ", ".join(f"{e.date} {e.narration!r}" for e in bad[:3])
    return ControlResult("C3", "Period lock", False,
                         f"{len(bad)} entry(ies) before {period_lock_before}: {where}")


# --------------------------------------------------------------------------- #
# C4 — every period entry has a non-empty source
# --------------------------------------------------------------------------- #

def c4_entry_source(entries: Sequence, period_tag: str = PERIOD_TAG) -> ControlResult:
    bad = []
    for e in _transactions(entries):
        if not _is_period(e, period_tag):
            continue
        source = (e.meta or {}).get("source")
        if not source or not str(source).strip():
            bad.append(e)
    if not bad:
        return ControlResult("C4", "Non-empty source", True)
    where = ", ".join(f"{e.date} {e.narration!r}" for e in bad[:3])
    return ControlResult("C4", "Non-empty source", False,
                         f"{len(bad)} entry(ies) missing source: {where}")


# --------------------------------------------------------------------------- #
# C5 — postings at/above materiality carry approved-by
# --------------------------------------------------------------------------- #

def c5_materiality(entries: Sequence, materiality: Decimal,
                   period_tag: str = PERIOD_TAG) -> ControlResult:
    materiality = _dec(materiality)
    bad = []
    for e in _transactions(entries):
        if not _is_period(e, period_tag):
            continue
        txn_meta = e.meta or {}
        for p in e.postings:
            if p.units is None:
                continue
            if abs(p.units.number) >= materiality:
                approved = (p.meta or {}).get("approved-by") or txn_meta.get("approved-by")
                if not approved or not str(approved).strip():
                    bad.append((e, p))
    if not bad:
        return ControlResult("C5", "Materiality approved", True)
    e, p = bad[0]
    return ControlResult("C5", "Materiality approved", False,
                         f"{len(bad)} posting(s) >= {materiality} without approved-by "
                         f"(e.g. {p.account} {p.units.number} on {e.date})")


# --------------------------------------------------------------------------- #
# C6 — no duplicate entries (date, postings set, source)
# --------------------------------------------------------------------------- #

def _dup_key(e):
    postings = frozenset(
        (p.account, str(p.units.number) if p.units is not None else None)
        for p in e.postings)
    source = (e.meta or {}).get("source")
    return (e.date, postings, source)


def c6_no_duplicates(entries: Sequence, period_tag: str = PERIOD_TAG) -> ControlResult:
    seen: dict = {}
    dups = []
    for e in _transactions(entries):
        if not _is_period(e, period_tag):
            continue
        key = _dup_key(e)
        if key in seen:
            dups.append(e)
        else:
            seen[key] = e
    if not dups:
        return ControlResult("C6", "No duplicates", True)
    where = ", ".join(f"{e.date} {e.narration!r}" for e in dups[:3])
    return ControlResult("C6", "No duplicates", False,
                         f"{len(dups)} duplicate entry(ies): {where}")


# --------------------------------------------------------------------------- #
# C7 — bank balance reconciles
# --------------------------------------------------------------------------- #

def _reconciling_amounts(reconciling: dict, key: str) -> Decimal:
    items = (reconciling or {}).get(key, []) or []
    total = ZERO
    for item in items:
        if isinstance(item, dict):
            total += _dec(item.get("amount", 0))
        else:
            total += _dec(item)
    return total


def c7_bank_reconciles(entries: Sequence, bank_account: str,
                       statement_closing: Decimal, reconciling: dict,
                       as_of: date = PERIOD_END) -> ControlResult:
    ledger_balance = account_balance(entries, bank_account, as_of)
    outstanding = _reconciling_amounts(reconciling, "outstanding_cheques")
    deposits = _reconciling_amounts(reconciling, "deposits_in_transit")
    expected = _dec(statement_closing) + outstanding - deposits
    diff = ledger_balance - expected
    passed = abs(diff) < CENT
    detail = "" if passed else (
        f"ledger bank {ledger_balance} != statement {statement_closing} "
        f"+ outstanding {outstanding} - deposits {deposits} = {expected} "
        f"(off by {diff})")
    return ControlResult("C7", "Bank reconciles", passed, detail)


# --------------------------------------------------------------------------- #
# C8 — suspense is zero
# --------------------------------------------------------------------------- #

def c8_suspense_zero(entries: Sequence, suspense_account: str,
                     as_of: date = PERIOD_END) -> ControlResult:
    bal = account_balance(entries, suspense_account, as_of)
    passed = abs(bal) < CENT
    detail = "" if passed else f"{suspense_account} = {bal} at {as_of}"
    return ControlResult("C8", "Suspense is zero", passed, detail)


# --------------------------------------------------------------------------- #
# C9 — no open exceptions
# --------------------------------------------------------------------------- #

def c9_no_open_exceptions(exceptions_dir) -> ControlResult:
    directory = Path(exceptions_dir)
    open_ids = []
    if directory.exists():
        for path in sorted(directory.glob("*.yaml")):
            try:
                items = yaml.safe_load(path.read_text(encoding="utf-8")) or []
            except yaml.YAMLError as exc:
                return ControlResult("C9", "No open exceptions", False,
                                     f"cannot parse {path.name}: {exc}")
            for item in items:
                if isinstance(item, dict) and item.get("status") == "open":
                    open_ids.append(item.get("id", "?"))
    if not open_ids:
        return ControlResult("C9", "No open exceptions", True)
    return ControlResult("C9", "No open exceptions", False,
                         f"{len(open_ids)} open: {', '.join(str(i) for i in open_ids[:6])}")


# --------------------------------------------------------------------------- #
# C10 — Dodo clearing balance
# --------------------------------------------------------------------------- #

def _payout_gross(payout: dict) -> Decimal:
    # gross processed = net paid out (amount) + processor fee
    return _dec(payout.get("amount", 0)) + _dec(payout.get("fee", 0))


def c10_dodo_balance(entries: Sequence, payments: Sequence, refunds: Sequence,
                     payouts: Sequence, dodo_account: str,
                     as_of: date = PERIOD_END) -> ControlResult:
    paid = _sum(p.get("total_amount", 0) for p in payments)
    refunded = _sum(r.get("amount", 0) for r in refunds)
    paid_out = _sum(
        _payout_gross(po) for po in payouts
        if str(po.get("status", "success")).lower() == "success")
    expected = paid - refunded - paid_out
    ledger_balance = account_balance(entries, dodo_account, as_of)
    diff = ledger_balance - expected
    passed = abs(diff) < CENT
    detail = "" if passed else (
        f"{dodo_account} {ledger_balance} != payments {paid} - refunds {refunded} "
        f"- paid-out gross {paid_out} = {expected} (off by {diff})")
    return ControlResult("C10", "Dodo balance", passed, detail)


# --------------------------------------------------------------------------- #
# repo wiring
# --------------------------------------------------------------------------- #

_COMPANY_DEFAULTS = {
    "name": "Northwind Labs Inc.",
    "currency": "USD",
    "period": "2026-09",
    "period_lock_before": "2026-09-01",
    "materiality": "10000.00",
    "bank_account": "Assets:Bank:Operating",
    "suspense_account": "Equity:Suspense",
    "dodo_account": "Assets:Dodo:Balance",
}


_CONTROL_NAMES = {
    1: "Ledger parses and balances",
    2: "Trial balance nets to zero",
    3: "Period lock",
    4: "Non-empty source",
    5: "Materiality approved",
    6: "No duplicates",
    7: "Bank reconciles",
    8: "Suspense is zero",
    9: "No open exceptions",
    10: "Dodo balance",
}


def _pick(company: dict, *keys, default=None):
    for k in keys:
        if k in company and company[k] not in (None, ""):
            return company[k]
    return default


def load_company(path) -> dict:
    """Read data/company.json, tolerating several key spellings, with defaults."""
    company = dict(_COMPANY_DEFAULTS)
    path = Path(path)
    if path.exists():
        try:
            company.update(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    return company


def _load_json(path, default):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def run_all(repo_root=".") -> list:
    """Run all ten controls against a repository checkout. Missing data yields a
    failing ControlResult (with a clear reason) rather than an exception."""
    root = Path(repo_root)
    company = load_company(root / "data" / "company.json")

    bank = _pick(company, "bank_account", "bank", default="Assets:Bank:Operating")
    suspense = _pick(company, "suspense_account", "suspense", default="Equity:Suspense")
    dodo = _pick(company, "dodo_account", "processor_clearing", "dodo",
                 default="Assets:Dodo:Balance")
    materiality = _dec(_pick(company, "materiality", default="10000.00"))
    lock_raw = _pick(company, "period_lock_before", default="2026-09-01")
    period_lock = date.fromisoformat(str(lock_raw))
    period = str(_pick(company, "period", default="2026-09"))

    ledger_path = root / "ledger" / "main.beancount"
    results = [c1_ledger_balances(ledger_path)]

    # If the ledger is missing or produces no usable entries, C2-C10 cannot be
    # evaluated honestly: a control that "passes" on an empty ledger is a false
    # pass. Skip them explicitly as FAIL so absence never reads as compliance.
    entries: list = []
    if ledger_path.exists():
        entries, _, _ = loader.load_file(str(ledger_path))
    if not entries:
        reason = "skipped: ledger missing/unparseable"
        for cid in range(2, 11):
            results.append(ControlResult(f"C{cid}", _CONTROL_NAMES[cid], False, reason))
        return results

    results.append(c2_trial_balance(entries))
    results.append(c3_period_lock(entries, period_lock, period))
    results.append(c4_entry_source(entries, period))
    results.append(c5_materiality(entries, materiality, period))
    results.append(c6_no_duplicates(entries, period))

    # C7 requires the statement closing balance; never default it to 0.
    statement_path = root / "data" / "bank" / "statement-balance.json"
    statement = _load_json(statement_path, None) if statement_path.exists() else None
    if statement is None:
        results.append(ControlResult(
            "C7", _CONTROL_NAMES[7], False,
            "statement-balance.json missing or unparseable"))
    else:
        statement_closing = _dec(
            _pick(statement, "closing", "closing_balance", "balance", default="0"))
        reconciling = _load_json(root / "exceptions" / "bank-rec-reconciling.json", {})
        results.append(c7_bank_reconciles(entries, bank, statement_closing, reconciling))

    results.append(c8_suspense_zero(entries, suspense))
    results.append(c9_no_open_exceptions(root / "exceptions"))

    # C10 requires all three Dodo sources; never default any to an empty list.
    dodo_dir = root / "data" / "dodo"
    dodo_files = {name: dodo_dir / f"{name}.json"
                  for name in ("payments", "refunds", "payouts")}
    missing = [name for name, path in dodo_files.items() if not path.exists()]
    if missing:
        results.append(ControlResult(
            "C10", _CONTROL_NAMES[10], False,
            f"dodo file(s) missing: {', '.join(missing)}"))
    else:
        payments = _load_json(dodo_files["payments"], [])
        refunds = _load_json(dodo_files["refunds"], [])
        payouts = _load_json(dodo_files["payouts"], [])
        results.append(c10_dodo_balance(entries, payments, refunds, payouts, dodo))

    return results


def render_table(results: Sequence) -> str:
    """Plain-text control table for the CLI."""
    lines = ["  #    Control                        Result",
             "  ---  -----------------------------  ------"]
    for r in results:
        mark = "PASS" if r.passed else "FAIL"
        lines.append(f"  {r.id:<4} {r.name:<29}  {mark}")
        if not r.passed and r.detail:
            lines.append(f"       -> {r.detail}")
    passed = sum(1 for r in results if r.passed)
    lines.append(f"\n  {passed}/{len(results)} controls passed")
    return "\n".join(lines)
