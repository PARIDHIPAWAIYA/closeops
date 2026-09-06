"""Beancount ledger helpers: load, balances, open items, render, bean-check.

Money stays :class:`decimal.Decimal` throughout (beancount already parses amounts
as Decimal). bean-check runs the Windows-safe module form
``python -m beancount.scripts.check``.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import date as _date
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Optional

from beancount import loader
from beancount.core import data


def load_ledger(path) -> tuple:
    """Load a beancount file. Returns (entries, errors, options_map)."""
    return loader.load_file(str(path))


def _as_of(value) -> Optional[_date]:
    if value is None or isinstance(value, _date):
        return value
    return _date.fromisoformat(str(value))


def balance(entries: Iterable, account: str, as_of=None) -> Decimal:
    """Sum postings to ``account`` with txn date <= ``as_of`` (all if None)."""
    cutoff = _as_of(as_of)
    total = Decimal("0")
    for entry in entries:
        if not isinstance(entry, data.Transaction):
            continue
        if cutoff is not None and entry.date > cutoff:
            continue
        for posting in entry.postings:
            if posting.account == account and posting.units is not None:
                total += posting.units.number
    return total


def balances_by_account(entries: Iterable, as_of=None) -> dict:
    """Return {account: Decimal} of summed postings up to ``as_of``."""
    cutoff = _as_of(as_of)
    totals: dict[str, Decimal] = {}
    for entry in entries:
        if not isinstance(entry, data.Transaction):
            continue
        if cutoff is not None and entry.date > cutoff:
            continue
        for posting in entry.postings:
            if posting.units is None:
                continue
            totals[posting.account] = totals.get(posting.account, Decimal("0")) + posting.units.number
    return totals


def trial_balance_net(entries: Iterable, as_of=None) -> Decimal:
    """Net of every posting; a balanced ledger nets to exactly zero."""
    return sum(balances_by_account(entries, as_of).values(), Decimal("0"))


def open_items(entries: Iterable, account: str, as_of=None) -> list[dict]:
    """Unsettled items on ``account`` grouped by their ``invoice`` metadata.

    A bill/invoice posts to the control account with an ``invoice`` meta; a
    later payment posts the opposite sign with the same ``invoice``. Anything
    whose grouped total is non-zero is still open.
    """
    cutoff = _as_of(as_of)
    groups: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, data.Transaction):
            continue
        if cutoff is not None and entry.date > cutoff:
            continue
        for posting in entry.postings:
            if posting.account != account or posting.units is None:
                continue
            inv = (posting.meta or {}).get("invoice") or (entry.meta or {}).get("invoice")
            if not inv:
                continue
            g = groups.setdefault(inv, {
                "invoice": inv, "account": account,
                "total": Decimal("0"), "date": entry.date, "payee": entry.payee,
            })
            g["total"] += posting.units.number
    items = []
    for g in groups.values():
        if g["total"] != 0:
            # Remaining amount owed/collectible is the sign-flipped control balance.
            g["remaining"] = -g["total"]
            items.append(g)
    return items


def render_entry(date, payee, narration, postings, meta=None, flag="*") -> str:
    """Render one transaction as beancount text.

    ``postings`` is a list of (account, amount) where amount is a Decimal or
    None (beancount infers the residual). ``meta`` is an ordered dict of string
    key/values written above the postings.
    """
    lines = [f'{date} {flag} "{payee}" "{narration}"']
    for key, value in (meta or {}).items():
        lines.append(f'  {key}: "{value}"')
    for account, amount in postings:
        if amount is None:
            lines.append(f"  {account}")
        else:
            lines.append(f"  {account}  {Decimal(amount):.2f} USD")
    return "\n".join(lines) + "\n"


def bean_check(path) -> tuple[bool, str]:
    """Run bean-check (Windows-safe module form). Returns (ok, combined output)."""
    proc = subprocess.run(
        [sys.executable, "-m", "beancount.scripts.check", str(path)],
        capture_output=True, text=True,
    )
    ok = proc.returncode == 0
    return ok, (proc.stdout + proc.stderr).strip()


def check_errors(path) -> list:
    """Load and return the list of loader errors ([] means it parses cleanly)."""
    _, errors, _ = load_ledger(path)
    return errors
