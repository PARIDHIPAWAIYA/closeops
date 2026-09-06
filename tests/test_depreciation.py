"""Depreciation task acceptance (plan.md 6.3).

Straight-line (cost - salvage)/life per month; half-month for assets placed in
service during September; zero (flagged) once fully depreciated.

Hand-computed for period 2026-09 from data/fixed-assets.csv:
  FA-001 MacBooks  28,000 / 36            full month  ->   777.78
  FA-002 desks      9,600 / 60            full month  ->   160.00
  FA-003 server    (12,000-1,200) / 36    half month  ->   150.00  (in service 09-20)
  FA-004 laptops    4,800 / 36 from 2023  fully depr. ->     0.00  (flag, book nothing)
  September total                                      -> 1,087.78
"""
from __future__ import annotations

import shutil
from decimal import Decimal
from pathlib import Path

from closeops import ledger
from closeops.tasks import depreciation

ROOT = Path(__file__).resolve().parents[1]

SEPTEMBER_TOTAL = Decimal("1087.78")


def _copy_repo(tmp_path: Path) -> Path:
    for sub in ("data", "ledger"):
        shutil.copytree(ROOT / sub, tmp_path / sub)
    (tmp_path / "exceptions").mkdir(exist_ok=True)
    return tmp_path


def _asset(repo, asset_id):
    for a in depreciation.load_assets(repo):
        if a.id == asset_id:
            return a
    raise AssertionError(f"asset {asset_id} not found")


def _sched(repo, asset_id):
    return depreciation.schedule_for(_asset(repo, asset_id))


# ------------------------------ schedules -----------------------------------
def test_fa001_full_month(tmp_path):
    repo = _copy_repo(tmp_path)
    s = _sched(repo, "FA-001")
    assert s["amount"] == Decimal("777.78")
    assert s["fully_depreciated"] is False
    assert s["half_month"] is False


def test_fa002_full_month(tmp_path):
    repo = _copy_repo(tmp_path)
    s = _sched(repo, "FA-002")
    assert s["amount"] == Decimal("160.00")


def test_fa003_half_month(tmp_path):
    repo = _copy_repo(tmp_path)
    s = _sched(repo, "FA-003")
    assert s["amount"] == Decimal("150.00")
    assert s["half_month"] is True


def test_fa004_fully_depreciated(tmp_path):
    repo = _copy_repo(tmp_path)
    s = _sched(repo, "FA-004")
    assert s["amount"] == Decimal("0.00")
    assert s["fully_depreciated"] is True


def test_schedule_sum(tmp_path):
    repo = _copy_repo(tmp_path)
    total = sum(
        (depreciation.schedule_for(a)["amount"]
         for a in depreciation.load_assets(repo)),
        Decimal("0"))
    assert total == SEPTEMBER_TOTAL


# -------------------------------- apply -------------------------------------
def test_apply_books_three_assets_flags_fourth(tmp_path):
    repo = _copy_repo(tmp_path)
    depreciation.prepare(repo)
    result = depreciation.apply(repo)
    assert set(result["booked"]) == {"FA-001", "FA-002", "FA-003"}
    assert result["flagged"] == ["FA-004"]


def test_apply_depreciation_total(tmp_path):
    repo = _copy_repo(tmp_path)
    depreciation.prepare(repo)
    depreciation.apply(repo)
    entries, errors, _ = ledger.load_ledger(repo / "ledger" / "main.beancount")
    assert errors == []
    booked = (ledger.balance(entries, "Expenses:Depreciation", "2026-09-30")
              - ledger.balance(entries, "Expenses:Depreciation", "2026-08-31"))
    assert booked == SEPTEMBER_TOTAL


def test_apply_passes_bean_check(tmp_path):
    repo = _copy_repo(tmp_path)
    depreciation.prepare(repo)
    depreciation.apply(repo)
    ok, out = ledger.bean_check(repo / "ledger" / "main.beancount")
    assert ok, out


def test_apply_one_entry_per_asset_with_meta(tmp_path):
    repo = _copy_repo(tmp_path)
    depreciation.prepare(repo)
    depreciation.apply(repo)
    text = (repo / "ledger" / "2026-09" / "depreciation.beancount").read_text()
    for aid in ("FA-001", "FA-002", "FA-003"):
        assert f'asset: "{aid}"' in text
    assert 'asset: "FA-004"' not in text
