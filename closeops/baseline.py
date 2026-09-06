"""Baseline auto-match tiers for the metrics funnel (plan §0.4, §4).

Four tiers show how much of the bank statement each level of automation posts
without a human:

  * **exact**   — only unambiguous exact open-item matches,
  * **rules**   — exact plus recurring-payee rule matches,
  * **agent**   — the deterministic reference decider (top candidate, with the
                  contract's demotions: low score, Suspense, duplicate, material),
  * **review**  — everything, once the controller has approved the exceptions.

All tiers apply the same safety contract (score >= 0.9, never Suspense, never a
posting at/above materiality, and no flagged duplicate) so the comparison is
honest: the agent's win over a naive rules bot is that it also proposes a fix for
every exception and holds material/ambiguous items for review, not just raw count.

Money is Decimal throughout.
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from . import controls
from .tasks import bank_rec


def _qualifies(cand: dict, materiality: Decimal, suspense: str) -> bool:
    return bank_rec.classify(cand, materiality, suspense)


def _exact_auto(line: dict, materiality: Decimal, suspense: str) -> bool:
    if any(c["kind"] == "duplicate" for c in line["candidates"]):
        return False  # a flagged duplicate is routed to review by the contract
    exacts = [c for c in line["candidates"] if c["kind"] == "exact"]
    # a single unambiguous exact match only (ties are left for the agent)
    return len(exacts) == 1 and _qualifies(exacts[0], materiality, suspense)


def _rule_auto(line: dict, materiality: Decimal, suspense: str) -> bool:
    if any(c["kind"] == "duplicate" for c in line["candidates"]):
        return False
    rules_c = [c for c in line["candidates"] if c["kind"] == "rule"]
    return any(_qualifies(c, materiality, suspense) for c in rules_c)


def compute_tiers(candidates: dict, materiality, decisions: dict | None = None) -> dict:
    """Return the four-tier funnel counts + rates for a candidates set."""
    materiality = Decimal(str(materiality))
    suspense = "Equity:Suspense"
    lines = candidates["lines"]
    total = len(lines)

    exact = sum(1 for ln in lines if _exact_auto(ln, materiality, suspense))
    rules_only = sum(1 for ln in lines
                     if _exact_auto(ln, materiality, suspense)
                     or _rule_auto(ln, materiality, suspense))

    if decisions is None:
        decisions = bank_rec.reference_decisions(candidates, materiality)
    agent = sum(1 for d in decisions["decisions"] if d["choice"] != "exception")

    def rate(n):
        pct = (Decimal(n) / Decimal(total) * 100).quantize(Decimal("0.1")) if total else Decimal("0")
        return {"auto": n, "total": total, "rate": f"{n}/{total} ({pct}%)",
                "auto_rate": f"{pct}%"}

    return {
        "exact_baseline": rate(exact),
        "rules_only": rate(rules_only),
        "agent": rate(agent),
        "after_review": rate(total),
    }


def run(repo_root=".") -> dict:
    """Compute the baseline funnel from a fresh `prepare`, write it into
    metrics.json (under ``funnel``, as auto-rate strings) and return the tiers."""
    root = Path(repo_root)
    company = controls.load_company(root / "data" / "company.json")
    materiality = company.get("materiality", "10000.00")

    candidates = bank_rec.prepare(repo_root)
    tiers = compute_tiers(candidates, materiality)

    funnel = {k: tiers[k]["auto_rate"] for k in
              ("exact_baseline", "rules_only", "agent", "after_review")}
    _merge_metrics(root, {"funnel": funnel})

    # also drop the detailed tiers next to the candidates for inspection
    out = root / "work" / "bank-rec" / "baseline.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(tiers, indent=2), encoding="utf-8")
    return tiers


def _merge_metrics(root: Path, patch: dict) -> dict:
    path = root / "metrics.json"
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(existing.get(key), dict):
            existing[key].update(value)
        else:
            existing[key] = value
    path.write_text(json.dumps(existing, indent=2, default=str), encoding="utf-8")
    return existing
