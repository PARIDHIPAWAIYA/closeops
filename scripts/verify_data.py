#!/usr/bin/env python
"""Verify the generated dataset and print trap counts (plan.md section 4).

Checks the dataset produced by gen_data.py:
  * per-trap and total bank-line outcome counts (auto / exception / reconciling)
  * the CSV closing balance equals data/bank/statement-balance.json
  * main.beancount passes bean-check and its trial balance nets to zero

Exit code is non-zero if any check fails, so CI can gate on it.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gen_data  # noqa: E402
from closeops import ledger  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# Expected targets from plan.md section 4.
TARGET_AUTO = 95
TARGET_EXCEPTIONS = 20
TARGET_RECONCILING = 4
TRAP_TARGETS = {
    "T1": ("auto", 53), "T2": ("auto", 15), "T3": ("auto", 16), "T4": ("auto", 6),
    "T5": ("exception", 5), "T6": ("exception", 4), "T7": ("exception", 3),
    "T8": ("mixed", 2), "T9": ("exception", 3), "T10": ("exception", 3),
    "T11": ("reconciling", 3), "T12": ("reconciling", 1), "T13": ("auto", 2),
    "T14": ("mixed", 2), "T15": ("mixed", 2),
}


def approx(actual: int, target: int, tol: int = 2) -> bool:
    return abs(actual - target) <= tol


def main() -> int:
    ds = gen_data.build_dataset(42)
    ok = True

    by_trap = defaultdict(lambda: {"auto": 0, "exception": 0})
    for ln in ds["bank_lines"]:
        by_trap[ln["trap"]][ln["outcome"]] += 1
    for item in ds["reconciling"]:
        by_trap[item["trap"]].setdefault("reconciling", 0)
        by_trap[item["trap"]]["reconciling"] = by_trap[item["trap"]].get("reconciling", 0) + 1

    auto = sum(1 for ln in ds["bank_lines"] if ln["outcome"] == "auto")
    exceptions = sum(1 for ln in ds["bank_lines"] if ln["outcome"] == "exception")
    reconciling = len(ds["reconciling"])

    print("Trap breakdown (plan.md section 4):")
    print(f"  {'trap':5} {'auto':>5} {'exc':>5} {'recon':>6}   target")
    for trap in sorted(TRAP_TARGETS, key=lambda t: int(t[1:])):
        c = by_trap.get(trap, {})
        kind, n = TRAP_TARGETS[trap]
        print(f"  {trap:5} {c.get('auto',0):>5} {c.get('exception',0):>5} "
              f"{c.get('reconciling',0):>6}   {kind} ~{n}")

    print()
    print(f"auto-posted : {auto:>3}   (target ~{TARGET_AUTO})")
    print(f"exceptions  : {exceptions:>3}   (target ~{TARGET_EXCEPTIONS})")
    print(f"reconciling : {reconciling:>3}   (target  {TARGET_RECONCILING})")

    if not approx(auto, TARGET_AUTO):
        print("FAIL: auto-posted count off target"); ok = False
    if not approx(exceptions, TARGET_EXCEPTIONS):
        print("FAIL: exception count off target"); ok = False
    if reconciling != TARGET_RECONCILING:
        print("FAIL: reconciling count off target"); ok = False

    # CSV closing == statement-balance.json
    csv_path = ROOT / "data" / "bank" / "sep-2026.csv"
    bal_path = ROOT / "data" / "bank" / "statement-balance.json"
    if csv_path.exists() and bal_path.exists():
        rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
        csv_closing = Decimal(rows[-1]["Balance"])
        json_closing = Decimal(json.loads(bal_path.read_text())["closing_balance"])
        print()
        print(f"CSV closing balance : {csv_closing}")
        print(f"statement-balance   : {json_closing}")
        if csv_closing != json_closing:
            print("FAIL: CSV closing != statement-balance.json"); ok = False
    else:
        print("NOTE: run gen_data.py first to write data/bank/*")

    # Ledger: bean-check + trial balance
    main_bc = ROOT / "ledger" / "main.beancount"
    if main_bc.exists():
        passed, out = ledger.bean_check(main_bc)
        entries, errors, _ = ledger.load_ledger(main_bc)
        net = ledger.trial_balance_net(entries, "2026-09-30")
        print()
        print(f"bean-check          : {'pass' if passed else 'FAIL'}")
        print(f"trial balance net   : {net}")
        if not passed:
            print(out); ok = False
        if net != Decimal("0"):
            print("FAIL: trial balance does not net to zero"); ok = False

    print()
    print("OK" if ok else "FAILURES DETECTED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
