"""Accruals task acceptance (plan.md 6.2).

  * October-service bill is not accrued.
  * The 14,500 legal retainer is at/above materiality -> one open exception.
  * Non-material September bills auto-post; totals match hand-computed numbers.
  * apply output leaves the ledger passing bean-check.
"""
from __future__ import annotations

import shutil
from decimal import Decimal
from pathlib import Path

import yaml

from closeops import ledger
from closeops.tasks import accruals

ROOT = Path(__file__).resolve().parents[1]

# Hand-computed from data/ap/invoices.json (booked:false, service_period 2026-09):
#   INV-001 Legal        14,500.00   (>= materiality 10,000 -> exception)
#   INV-002 Hosting       3,200.00
#   INV-003 Contractors   6,800.00
#   INV-004 Marketing     4,500.00
#   INV-005 Utilities     1,250.00
#   INV-006 Travel        2,100.00
#   INV-007 Insurance     3,600.00   service_period 2026-10 -> do NOT accrue
NON_MATERIAL_TOTAL = Decimal("17850.00")   # 3200+6800+4500+1250+2100
MATERIAL_TOTAL = Decimal("14500.00")


def _copy_repo(tmp_path: Path) -> Path:
    for sub in ("data", "ledger"):
        shutil.copytree(ROOT / sub, tmp_path / sub)
    (tmp_path / "exceptions").mkdir(exist_ok=True)
    return tmp_path


# ------------------------------- prepare ------------------------------------
def test_october_bill_not_accrued(tmp_path):
    repo = _copy_repo(tmp_path)
    plan = accruals.prepare(repo)
    accrued_ids = {a["id"] for a in plan["accruals"]}
    assert "INV-007" not in accrued_ids
    skipped_ids = {s["id"] for s in plan["skipped"]}
    assert "INV-007" in skipped_ids


def test_only_unbooked_september_bills_accrued(tmp_path):
    repo = _copy_repo(tmp_path)
    plan = accruals.prepare(repo)
    accrued_ids = {a["id"] for a in plan["accruals"]}
    assert accrued_ids == {"INV-001", "INV-002", "INV-003",
                           "INV-004", "INV-005", "INV-006"}


def test_materiality_flagged(tmp_path):
    repo = _copy_repo(tmp_path)
    plan = accruals.prepare(repo)
    by_id = {a["id"]: a for a in plan["accruals"]}
    assert by_id["INV-001"]["needs_approval"] is True
    assert by_id["INV-002"]["needs_approval"] is False


def test_accrual_totals(tmp_path):
    repo = _copy_repo(tmp_path)
    plan = accruals.prepare(repo)
    total = sum((Decimal(a["amount"]) for a in plan["accruals"]), Decimal("0"))
    assert total == NON_MATERIAL_TOTAL + MATERIAL_TOTAL
    non_material = sum(
        (Decimal(a["amount"]) for a in plan["accruals"] if not a["needs_approval"]),
        Decimal("0"))
    assert non_material == NON_MATERIAL_TOTAL


# -------------------------------- apply -------------------------------------
def test_apply_creates_one_open_exception(tmp_path):
    repo = _copy_repo(tmp_path)
    accruals.prepare(repo)
    accruals.apply(repo)
    items = yaml.safe_load((repo / "exceptions" / "accruals.yaml").read_text())
    open_items = [i for i in items if i["status"] == "open"]
    assert len(open_items) == 1
    exc = open_items[0]
    assert exc["source"].endswith("INV-001")
    postings = exc["proposed_entry"]["postings"]
    net = sum((Decimal(str(p["amount"])) for p in postings), Decimal("0"))
    assert net == Decimal("0")


def test_apply_books_only_non_material(tmp_path):
    repo = _copy_repo(tmp_path)
    accruals.prepare(repo)
    accruals.apply(repo)
    entries, errors, _ = ledger.load_ledger(repo / "ledger" / "main.beancount")
    assert errors == []
    accrued = -ledger.balance(entries, "Liabilities:Accrued:Expenses", "2026-09-30")
    # Only the five non-material September bills are booked on first apply.
    assert accrued == NON_MATERIAL_TOTAL


def test_apply_passes_bean_check(tmp_path):
    repo = _copy_repo(tmp_path)
    accruals.prepare(repo)
    accruals.apply(repo)
    ok, out = ledger.bean_check(repo / "ledger" / "main.beancount")
    assert ok, out


def test_apply_approved_materiality_is_booked(tmp_path):
    """Approval round-trip: once the controller approves the exception, a
    re-apply books the 14,500 entry with an approved-by meta (so C5 stays green)."""
    repo = _copy_repo(tmp_path)
    accruals.prepare(repo)
    accruals.apply(repo)
    exc_path = repo / "exceptions" / "accruals.yaml"
    items = yaml.safe_load(exc_path.read_text())
    for i in items:
        if i["status"] == "open":
            i["status"] = "approved"
            i["reviewer_note"] = "CFO approved retainer"
    exc_path.write_text(yaml.safe_dump(items, sort_keys=False))

    accruals.apply(repo)
    entries, errors, _ = ledger.load_ledger(repo / "ledger" / "main.beancount")
    assert errors == []
    accrued = -ledger.balance(entries, "Liabilities:Accrued:Expenses", "2026-09-30")
    assert accrued == NON_MATERIAL_TOTAL + MATERIAL_TOTAL
    legal = ledger.balance(entries, "Expenses:Legal", "2026-09-30")
    # Wayne Ent (INV-013, booked) is already in main; the accrual adds 14,500.
    assert legal >= MATERIAL_TOTAL
    # The material posting must carry approved-by, or C5 would fail.
    from beancount.core import data
    material = [
        e for e in entries if isinstance(e, data.Transaction)
        and "2026-09" in (e.meta or {}).get("filename", "").replace("\\", "/")
        and any(p.units and abs(p.units.number) >= Decimal("10000")
                for p in e.postings)
    ]
    assert material, "expected the 14,500 accrual in the period ledger"
    for e in material:
        approved = (e.meta or {}).get("approved-by") or any(
            (p.meta or {}).get("approved-by") for p in e.postings)
        assert approved, "material accrual booked without approved-by"
