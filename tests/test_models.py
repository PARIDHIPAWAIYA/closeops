"""Models must use Decimal for money and round-trip to/from plain dicts."""
from decimal import Decimal

import pytest

from closeops import models


def test_statement_line_uses_decimal():
    line = models.StatementLine(
        date="2026-09-03",
        description="GUSTO PAYROLL",
        amount=Decimal("-12500.00"),
        balance=Decimal("100000.00"),
        reference="T3-0001",
        lineno=4,
    )
    assert isinstance(line.amount, Decimal)
    assert isinstance(line.balance, Decimal)


def test_statement_line_from_dict_coerces_decimal():
    line = models.StatementLine.from_dict(
        {
            "date": "2026-09-03",
            "description": "GUSTO PAYROLL",
            "amount": "-12500.00",
            "balance": "100000.00",
            "reference": "T3-0001",
            "lineno": 4,
        }
    )
    assert line.amount == Decimal("-12500.00")
    assert isinstance(line.amount, Decimal)


def test_invoice_from_dict():
    inv = models.Invoice.from_dict(
        {
            "id": "BILL-001",
            "vendor": "WeWork",
            "date": "2026-09-01",
            "due": "2026-09-30",
            "amount": "3200.00",
            "currency": "USD",
            "account": "Expenses:Rent",
            "service_period": "2026-09",
            "booked": False,
        }
    )
    assert inv.amount == Decimal("3200.00")
    assert inv.booked is False
    assert inv.service_period == "2026-09"


def test_asset_from_dict_and_money_is_decimal():
    asset = models.Asset.from_dict(
        {
            "id": "FA-001",
            "description": "MacBooks",
            "cost": "28000.00",
            "salvage": "0.00",
            "life_months": 36,
            "in_service": "2026-02-01",
            "account": "Assets:FixedAssets:Computers",
        }
    )
    assert asset.cost == Decimal("28000.00")
    assert asset.life_months == 36


def test_payout_from_dict():
    p = models.Payout.from_dict(
        {
            "payout_id": "po_1",
            "amount": "9000.00",
            "fee": "300.00",
            "currency": "USD",
            "status": "success",
            "created_at": "2026-09-15",
            "payout_document_url": "https://example/doc",
        }
    )
    assert p.amount == Decimal("9000.00")
    assert p.fee == Decimal("300.00")


def test_candidate_and_decision_roundtrip():
    cand = models.Candidate(
        id="c1",
        kind="exact",
        score=Decimal("0.95"),
        account="Liabilities:AP",
        postings=[{"account": "Liabilities:AP", "amount": "1250.00"}],
        evidence=["BILL-118"],
    )
    d = cand.to_dict()
    assert d["score"] == "0.95"
    dec = models.Decision(line=4, choice="c1", rationale="exact", confidence=Decimal("0.95"))
    assert dec.to_dict()["confidence"] == "0.95"


def test_control_result_bool():
    ok = models.ControlResult(code="C1", passed=True, detail="balances")
    bad = models.ControlResult(code="C2", passed=False, detail="off by 100")
    assert ok.passed and not bad.passed
