"""Depreciation task (plan.md 6.3).

Straight-line ``(cost - salvage) / life`` per month. An asset placed in service
*during* the close period gets a half month. Once an asset is fully depreciated
it books nothing and is flagged. Prior accumulated depreciation is read from the
ledger (per-asset ``asset:`` meta) so a re-run never over-depreciates.

Money is always :class:`decimal.Decimal`; never float.
"""
from __future__ import annotations

import csv
import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from beancount.core import data

from .. import ledger
from ..models import Asset

PERIOD = "2026-09"
PERIOD_YEAR = 2026
PERIOD_MONTH = 9
DEPR_DATE = "2026-09-30"
PRIOR_DATE = "2026-08-31"          # last day before the period, for prior balances
DEPRECIATION_ACCOUNT = "Expenses:Depreciation"
ACCUMULATED_ACCOUNT = "Assets:FixedAssets:AccumulatedDepreciation"

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def _repo(repo) -> Path:
    return Path(repo)


def load_assets(repo=".") -> list[Asset]:
    """Read data/fixed-assets.csv into Asset records."""
    path = _repo(repo) / "data" / "fixed-assets.csv"
    assets: list[Asset] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            assets.append(Asset.from_dict(row))
    return assets


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def monthly_amount(asset: Asset) -> Decimal:
    """Straight-line depreciation for one full month, rounded to cents."""
    base = asset.cost - asset.salvage
    return _quantize(base / Decimal(asset.life_months))


def _months_before_period(asset: Asset) -> int:
    """Whole months from the in-service month up to (not incl.) the period.

    0 means the asset enters service in the period month; negative means it is
    not yet in service.
    """
    y, m, _ = (int(part) for part in asset.in_service.split("-"))
    return (PERIOD_YEAR - y) * 12 + (PERIOD_MONTH - m)


def prior_accumulated(repo, asset_id: str) -> Decimal:
    """Accumulated depreciation already booked for ``asset_id``.

    Read from ledger postings to the accumulated-depreciation account that carry
    a matching ``asset:`` meta and are dated before the period. Returns a
    positive magnitude. On the first run (no per-asset meta yet) this is 0.
    """
    main = _repo(repo) / "ledger" / "main.beancount"
    if not main.exists():
        return ZERO
    entries, _, _ = ledger.load_ledger(main)
    cutoff = ledger._as_of(PRIOR_DATE)
    total = ZERO
    for entry in entries:
        if not isinstance(entry, data.Transaction) or entry.date > cutoff:
            continue
        for posting in entry.postings:
            if posting.account != ACCUMULATED_ACCOUNT or posting.units is None:
                continue
            meta = posting.meta or {}
            if meta.get("asset") == asset_id or (entry.meta or {}).get("asset") == asset_id:
                total += posting.units.number
    return -total  # contra-asset is stored negative; report the magnitude


def schedule_for(asset: Asset, prior_accum: Decimal | None = None) -> dict:
    """Compute this period's depreciation for one asset.

    Returns a dict: id, description, account, monthly, amount, half_month,
    fully_depreciated, in_service, prior_accumulated.
    """
    monthly = monthly_amount(asset)
    base = asset.cost - asset.salvage
    months_before = _months_before_period(asset)

    if prior_accum is None:
        # Estimate from the schedule when the ledger carries no per-asset history.
        prior_accum = min(monthly * max(months_before, 0), base)

    result = {
        "id": asset.id,
        "description": asset.description,
        "account": asset.account,
        "monthly": monthly,
        "amount": ZERO,
        "half_month": False,
        "fully_depreciated": False,
        "in_service": True,
        "prior_accumulated": _quantize(prior_accum),
    }

    if months_before < 0:
        # Not yet in service this period: nothing to book.
        result["in_service"] = False
        return result

    if months_before >= asset.life_months or prior_accum >= base:
        result["fully_depreciated"] = True
        return result

    if months_before == 0:
        # Placed in service during the period -> half month.
        result["half_month"] = True
        amount = _quantize(monthly / Decimal(2))
    else:
        amount = monthly

    # Never depreciate past the depreciable base (final-month remainder).
    remaining = base - prior_accum
    if amount > remaining:
        amount = _quantize(remaining)
    result["amount"] = amount
    return result


def prepare(repo=".") -> dict:
    """Deterministic schedule for every asset -> work/depreciation/candidates.json."""
    repo = _repo(repo)
    schedules = []
    for asset in load_assets(repo):
        prior = prior_accumulated(repo, asset.id)
        # If the ledger has no per-asset history, fall back to the estimate.
        sched = schedule_for(asset, prior if prior > 0 else None)
        schedules.append(sched)

    out_dir = repo / "work" / "depreciation"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "task": "depreciation",
        "period": PERIOD,
        "schedules": [_json_safe(s) for s in schedules],
    }
    (out_dir / "candidates.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8")
    return {"schedules": schedules}


def _json_safe(sched: dict) -> dict:
    out = dict(sched)
    for key in ("monthly", "amount", "prior_accumulated"):
        out[key] = str(out[key])
    return out


def apply(repo=".") -> dict:
    """Render one entry per depreciating asset -> ledger/2026-09/depreciation.beancount."""
    repo = _repo(repo)
    schedules = prepare(repo)["schedules"]

    booked: list[str] = []
    flagged: list[str] = []
    blocks: list[str] = []
    total = ZERO

    header = (
        ";; ledger/2026-09/depreciation.beancount\n"
        ";; Generated by `closeops apply depreciation` (plan 6.3). Do not edit by hand.\n"
    )
    for sched in schedules:
        if not sched["in_service"]:
            continue
        if sched["fully_depreciated"] or sched["amount"] == ZERO:
            flagged.append(sched["id"])
            continue
        amount = sched["amount"]
        total += amount
        payee = f'{sched["id"]} {sched["description"]}'
        meta = {
            "source": f'data/fixed-assets.csv#{sched["id"]}',
            "task": "depreciation",
            "asset": sched["id"],
        }
        postings = [
            (DEPRECIATION_ACCOUNT, amount),
            (ACCUMULATED_ACCOUNT, -amount),
        ]
        blocks.append(ledger.render_entry(
            DEPR_DATE, payee, "September depreciation", postings, meta=meta))
        booked.append(sched["id"])

    out_path = repo / "ledger" / "2026-09" / "depreciation.beancount"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(header + "\n" + "\n".join(blocks), encoding="utf-8")

    ok, out = ledger.bean_check(repo / "ledger" / "main.beancount")
    return {
        "booked": booked,
        "flagged": flagged,
        "total": total,
        "bean_check_ok": ok,
        "bean_check_output": out,
    }
