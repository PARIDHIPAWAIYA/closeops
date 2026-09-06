"""Test helpers: build beancount entries by hand so controls tests stand alone.

These do not depend on the data-ledger worker's generated ledger; each control
test constructs the minimal entries it needs.
"""
from __future__ import annotations

from datetime import date

from beancount.core import data
from beancount.core.amount import Amount
from beancount.core.number import D


def posting(account, number, meta=None):
    """A single posting. Pass number=None for an elided amount."""
    units = None if number is None else Amount(D(str(number)), "USD")
    return data.Posting(account, units, None, None, None, meta)


def txn(day, postings, narration="entry", source=None, filename="main.beancount",
        meta=None):
    """A transaction. `filename` decides whether a control treats it as a
    period (ledger/2026-09/*) entry; `source` sets the source meta."""
    m = {"filename": filename, "lineno": 1}
    if source is not None:
        m["source"] = source
    if meta:
        m.update(meta)
    return data.Transaction(m, day, "*", None, narration,
                            data.EMPTY_SET, data.EMPTY_SET, list(postings))


PERIOD_FILE = "ledger/2026-09/bank-rec.beancount"


def d(s):
    return date.fromisoformat(s)
