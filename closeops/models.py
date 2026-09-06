"""Typed records for closeops.

Money is always a :class:`decimal.Decimal`; never a float. Every record has a
``from_dict`` that coerces JSON/YAML primitives into the right types and a
``to_dict`` that renders back to JSON-safe primitives (Decimals become strings so
no precision is lost on the round trip).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from decimal import Decimal
from typing import Any, Optional


def _dec(value: Any) -> Decimal:
    """Coerce a string/int/Decimal into Decimal. Reject floats loudly."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        raise TypeError(
            "money must not be a float; pass a string or Decimal, got %r" % (value,)
        )
    return Decimal(str(value))


def _money_str(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    return value


@dataclass
class StatementLine:
    """One row of the bank statement CSV."""

    date: str
    description: str
    amount: Decimal
    balance: Decimal
    reference: str
    lineno: int

    @classmethod
    def from_dict(cls, d: dict) -> "StatementLine":
        return cls(
            date=d["date"],
            description=d["description"],
            amount=_dec(d["amount"]),
            balance=_dec(d["balance"]),
            reference=d.get("reference", ""),
            lineno=int(d["lineno"]),
        )

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "description": self.description,
            "amount": _money_str(self.amount),
            "balance": _money_str(self.balance),
            "reference": self.reference,
            "lineno": self.lineno,
        }


@dataclass
class Invoice:
    """A vendor bill (AP) or customer invoice (AR)."""

    id: str
    vendor: str
    date: str
    due: str
    amount: Decimal
    currency: str
    account: str
    service_period: str
    booked: bool
    kind: str = "AP"  # AP | AR

    @classmethod
    def from_dict(cls, d: dict) -> "Invoice":
        return cls(
            id=d["id"],
            vendor=d["vendor"],
            date=d["date"],
            due=d.get("due", d["date"]),
            amount=_dec(d["amount"]),
            currency=d.get("currency", "USD"),
            account=d["account"],
            service_period=d.get("service_period", ""),
            booked=bool(d.get("booked", True)),
            kind=d.get("kind", "AP"),
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["amount"] = _money_str(self.amount)
        return d


@dataclass
class Asset:
    """A fixed asset for straight-line depreciation."""

    id: str
    description: str
    cost: Decimal
    salvage: Decimal
    life_months: int
    in_service: str
    account: str

    @classmethod
    def from_dict(cls, d: dict) -> "Asset":
        return cls(
            id=d["id"],
            description=d["description"],
            cost=_dec(d["cost"]),
            salvage=_dec(d.get("salvage", "0")),
            life_months=int(d["life_months"]),
            in_service=d["in_service"],
            account=d["account"],
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["cost"] = _money_str(self.cost)
        d["salvage"] = _money_str(self.salvage)
        return d


@dataclass
class Payout:
    """A Dodo Payments processor payout record."""

    payout_id: str
    amount: Decimal
    fee: Decimal
    currency: str
    status: str
    created_at: str
    payout_document_url: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Payout":
        return cls(
            payout_id=d["payout_id"],
            amount=_dec(d["amount"]),
            fee=_dec(d.get("fee", "0")),
            currency=d.get("currency", "USD"),
            status=d.get("status", "success"),
            created_at=d["created_at"],
            payout_document_url=d.get("payout_document_url", ""),
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["amount"] = _money_str(self.amount)
        d["fee"] = _money_str(self.fee)
        return d


@dataclass
class Candidate:
    """A proposed match for a statement line, produced deterministically."""

    id: str
    kind: str  # exact | rule | payout | split | partial | fx | duplicate | none
    score: Decimal
    account: str
    postings: list = field(default_factory=list)
    evidence: list = field(default_factory=list)
    narration: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Candidate":
        return cls(
            id=d["id"],
            kind=d["kind"],
            score=_dec(d["score"]),
            account=d.get("account", ""),
            postings=list(d.get("postings", [])),
            evidence=list(d.get("evidence", [])),
            narration=d.get("narration", ""),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "score": _money_str(self.score),
            "account": self.account,
            "postings": self.postings,
            "evidence": self.evidence,
            "narration": self.narration,
        }


@dataclass
class Decision:
    """A worker's judgment on one statement line."""

    line: int
    choice: str  # a candidate id or the literal "exception"
    rationale: str
    confidence: Decimal

    @classmethod
    def from_dict(cls, d: dict) -> "Decision":
        return cls(
            line=int(d["line"]),
            choice=d["choice"],
            rationale=d.get("rationale", ""),
            confidence=_dec(d.get("confidence", "0")),
        )

    def to_dict(self) -> dict:
        return {
            "line": self.line,
            "choice": self.choice,
            "rationale": self.rationale,
            "confidence": _money_str(self.confidence),
        }


@dataclass
class Exception:
    """An unresolved item routed to the controller."""

    id: str
    task: str
    source: str
    issue: str
    proposed_entry: dict
    confidence: Decimal
    decided_by: str = "closeops-decide"
    trace: str = ""
    status: str = "open"  # open | approved | rejected
    reviewer_note: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Exception":
        return cls(
            id=d["id"],
            task=d["task"],
            source=d.get("source", ""),
            issue=d.get("issue", ""),
            proposed_entry=dict(d.get("proposed_entry", {})),
            confidence=_dec(d.get("confidence", "0")),
            decided_by=d.get("decided_by", "closeops-decide"),
            trace=d.get("trace", ""),
            status=d.get("status", "open"),
            reviewer_note=d.get("reviewer_note", ""),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task": self.task,
            "source": self.source,
            "issue": self.issue,
            "proposed_entry": self.proposed_entry,
            "confidence": _money_str(self.confidence),
            "decided_by": self.decided_by,
            "trace": self.trace,
            "status": self.status,
            "reviewer_note": self.reviewer_note,
        }


@dataclass
class ControlResult:
    """The outcome of one accounting control (C1..C10)."""

    code: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict:
        return {"code": self.code, "passed": self.passed, "detail": self.detail}
