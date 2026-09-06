#!/usr/bin/env python
"""Fetch Dodo Payments payout/payment/refund data for the close.

Default is ``--fixture``: deterministic, seeded test data written to
``data/dodo/``. ``--live`` uses the ``dodopayments`` SDK against test mode
(no money moves) and requires ``DODO_PAYMENTS_API_KEY``. The README states which
source produced the committed fixtures.

The fixtures are the single source of truth for the Dodo numbers: ``gen_data``
imports :func:`build_fixtures` so the ledger's payment/refund entries match the
payout records exactly (so control C10 can balance).
"""
from __future__ import annotations

import argparse
import json
import os
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DODO_DIR = ROOT / "data" / "dodo"


def build_fixtures(seed: int = 42) -> dict:
    """Return the seeded Dodo dataset for period 2026-09.

    Invariant: sum(payments) - sum(refunds) == sum(payout gross), where
    gross = amount(net) + fee, so the processor-clearing account nets out.
    """
    payments = [
        {"payment_id": "pay_001", "total_amount": "1500.00", "currency": "USD",
         "created_at": "2026-09-02", "customer": "Acme Analytics"},
        {"payment_id": "pay_002", "total_amount": "2500.00", "currency": "USD",
         "created_at": "2026-09-04", "customer": "Bright Labs"},
        {"payment_id": "pay_003", "total_amount": "1800.00", "currency": "USD",
         "created_at": "2026-09-06", "customer": "Cobalt Systems"},
        {"payment_id": "pay_004", "total_amount": "2200.00", "currency": "USD",
         "created_at": "2026-09-09", "customer": "Delta Works"},
        {"payment_id": "pay_005", "total_amount": "1200.00", "currency": "USD",
         "created_at": "2026-09-12", "customer": "Echo Retail"},
        {"payment_id": "pay_006", "total_amount": "3100.00", "currency": "USD",
         "created_at": "2026-09-15", "customer": "Foxtrot Media"},
        {"payment_id": "pay_007", "total_amount": "1900.00", "currency": "USD",
         "created_at": "2026-09-20", "customer": "Gamma Health"},
        {"payment_id": "pay_008", "total_amount": "1800.00", "currency": "USD",
         "created_at": "2026-09-23", "customer": "Helix Studio"},
    ]
    refunds = [
        {"refund_id": "ref_001", "payment_id": "pay_003", "amount": "600.00",
         "currency": "USD", "created_at": "2026-09-10"},
        {"refund_id": "ref_002", "payment_id": "pay_005", "amount": "400.00",
         "currency": "USD", "created_at": "2026-09-14"},
    ]
    # payout amount is the NET wired to the bank; fee is reported separately.
    # gross = amount + fee. po_2 intentionally omits the fee (fee "0.00") so the
    # bank-rec worker must infer it -> exception (trap T14, second payout).
    payouts = [
        {"payout_id": "po_001", "amount": "9700.00", "fee": "300.00",
         "currency": "USD", "status": "success", "created_at": "2026-09-18",
         "payout_document_url": "https://test.dodopayments.com/payouts/po_001"},
        {"payout_id": "po_002", "amount": "4850.00", "fee": "0.00",
         "currency": "USD", "status": "success", "created_at": "2026-09-25",
         "payout_document_url": "https://test.dodopayments.com/payouts/po_002"},
    ]
    return {"payments": payments, "refunds": refunds, "payouts": payouts}


def fetch_live() -> dict:
    """Fetch September records from Dodo test mode via the SDK."""
    from dodopayments import DodoPayments  # imported lazily; optional dependency

    client = DodoPayments(
        bearer_token=os.environ["DODO_PAYMENTS_API_KEY"], environment="test_mode"
    )

    def in_sep(created_at: str) -> bool:
        return str(created_at).startswith("2026-09")

    payments, refunds, payouts = [], [], []
    for p in client.payments.list():
        if in_sep(getattr(p, "created_at", "")):
            payments.append(
                {
                    "payment_id": p.payment_id,
                    "total_amount": str(p.total_amount),
                    "currency": p.currency,
                    "created_at": str(p.created_at),
                    "customer": getattr(p, "customer", ""),
                }
            )
    for r in client.refunds.list():
        if in_sep(getattr(r, "created_at", "")):
            refunds.append(
                {
                    "refund_id": r.refund_id,
                    "payment_id": r.payment_id,
                    "amount": str(r.amount),
                    "currency": getattr(r, "currency", "USD"),
                    "created_at": str(getattr(r, "created_at", "")),
                }
            )
    for po in client.payouts.list():
        if in_sep(getattr(po, "created_at", "")):
            payouts.append(
                {
                    "payout_id": po.payout_id,
                    "amount": str(po.amount),
                    "fee": str(getattr(po, "fee", "0")),
                    "currency": po.currency,
                    "status": getattr(po, "status", "success"),
                    "created_at": str(po.created_at),
                    "payout_document_url": getattr(po, "payout_document_url", ""),
                }
            )
    return {"payments": payments, "refunds": refunds, "payouts": payouts}


def write_fixtures(data: dict, out_dir: Path = DODO_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in ("payouts", "payments", "refunds"):
        # newline="\n" keeps LF on Windows so re-fetching produces no spurious diffs.
        (out_dir / f"{name}.json").write_text(
            json.dumps(data[name], indent=2) + "\n", encoding="utf-8", newline="\n"
        )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fetch Dodo Payments close data")
    ap.add_argument("--fixture", action="store_true", help="write seeded fixtures (default)")
    ap.add_argument("--live", action="store_true", help="fetch from Dodo test-mode API")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)

    if args.live:
        data = fetch_live()
        source = "live (test_mode)"
    else:
        data = build_fixtures(args.seed)
        source = "fixture"
    write_fixtures(data)

    reported_gross = sum(Decimal(p["amount"]) + Decimal(p["fee"]) for p in data["payouts"])
    net_in = sum(Decimal(p["total_amount"]) for p in data["payments"]) - sum(
        Decimal(r["amount"]) for r in data["refunds"]
    )
    missing_fee = net_in - reported_gross  # payout(s) with fee absent from the record
    print(f"dodo: {source} -> {len(data['payouts'])} payouts, "
          f"{len(data['payments'])} payments, {len(data['refunds'])} refunds")
    print(f"dodo: payments-refunds={net_in}  reported payout gross={reported_gross}")
    if missing_fee:
        print(f"dodo: {missing_fee} of fees absent from payout records "
              f"(trap T14 -> bank-rec exception)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
