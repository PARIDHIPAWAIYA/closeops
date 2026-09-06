"""Matching-rule loading, matching and learning.

Reads the seed rules (``data/rules/matching.yaml``) and any already-learned rules
(``data/rules/learned.yaml``), exposes a matcher for recurring bank lines, and
(Wave 2) learns new rules from controller-approved exceptions so a second close
auto-posts more than the first.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class Rule:
    match: str
    account: str
    confidence: Decimal
    learned: bool = False

    @property
    def pattern(self) -> "re.Pattern":
        return re.compile(self.match, re.IGNORECASE)


def _load_file(path: Path, learned: bool) -> list[Rule]:
    if not path or not Path(path).exists():
        return []
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    rules: list[Rule] = []
    for item in raw or []:
        rules.append(Rule(
            match=item["match"],
            account=item["account"],
            confidence=Decimal(str(item.get("confidence", "0.9"))),
            learned=learned,
        ))
    return rules


def load_rules(matching_path, learned_path=None) -> list[Rule]:
    """Load seed rules then learned rules (learned take precedence on ties)."""
    rules = _load_file(Path(matching_path), learned=False)
    if learned_path:
        rules += _load_file(Path(learned_path), learned=True)
    return rules


def match(description: str, rules: list[Rule]) -> Optional[Rule]:
    """Return the first (learned-preferred) rule whose pattern hits, else None."""
    for rule in sorted(rules, key=lambda r: (not r.learned,)):
        if rule.pattern.search(description or ""):
            return rule
    return None


# --------------------------------------------------------------------------- #
# learning from approved exceptions (Wave 2)
# --------------------------------------------------------------------------- #

# Bank-statement filler words that never make a useful match token.
_GENERIC_TOKENS = {
    "PAYMENT", "SUBSCRIPTION", "MEMBERSHIP", "PAYOUT", "DEPOSIT", "VIDEO",
    "WITHDRAWAL", "USAGE", "POS", "ATM", "EUR", "USD", "THE", "AND", "OF",
    "INC", "LLC", "LLP", "CORP", "CO", "LTD", "BIZ",
}

_LEARNABLE_PREFIXES = ("Expenses:", "Income:")

# Only unknown-payee and plain recurring-payee exceptions generalise to a rule.
# fx/split/partial/payout/duplicate/exact are one-off structural matches — a rule
# from them would auto-post an entire payment (or payout) to the wrong account.
_LEARNABLE_KINDS = {"none", "rule"}


def learn_token(description: str) -> Optional[str]:
    """Pick a distinctive uppercase token from a bank description to key a rule."""
    words = re.findall(r"[A-Za-z]{2,}", (description or "").upper())
    for w in words:
        if w not in _GENERIC_TOKENS:
            return w
    return words[0] if words else None


def _learnable_account(proposed_entry: dict) -> Optional[str]:
    for p in (proposed_entry or {}).get("postings", []):
        acct = p.get("account", "")
        if acct.startswith(_LEARNABLE_PREFIXES):
            return acct
    return None


def learn_from_exceptions(exceptions, existing: Optional[list] = None,
                          existing_rules: Optional[list] = None,
                          materiality=None, confidence="0.90") -> list[dict]:
    """Derive learned rules from *approved* exceptions, safely.

    A rule is learned only when the approved exception:
      * is ``status: approved`` and of a learnable kind (unknown-payee ``none`` or
        recurring ``rule``) — never fx/split/partial/payout/duplicate/exact,
      * has exactly two postings (the bank account plus one real expense/income
        account — the reclassified target),
      * is below materiality (material items must stay exceptions), and
      * is not already covered by an existing rule.

    Returns the merged learned-rule dicts (existing + new, de-duplicated).
    """
    merged = list(existing or [])
    seen = {(r["match"], r["account"]) for r in merged}
    mat = Decimal(str(materiality)) if materiality is not None else None
    for exc in exceptions or []:
        if not isinstance(exc, dict) or exc.get("status") != "approved":
            continue
        if exc.get("kind") not in _LEARNABLE_KINDS:
            continue
        proposed = exc.get("proposed_entry", {}) or {}
        postings = proposed.get("postings", [])
        if len(postings) != 2:
            continue
        if mat is not None and any(
                abs(Decimal(str(p.get("amount", "0")))) >= mat for p in postings):
            continue
        account = _learnable_account(proposed)
        if not account:
            continue
        desc = exc.get("description") or _desc_from_issue(exc.get("issue", ""))
        if existing_rules and match(desc, existing_rules) is not None:
            continue  # an existing rule already handles this description
        token = learn_token(desc)
        if not token:
            continue
        key = (token, account)
        if key in seen:
            continue
        seen.add(key)
        merged.append({"match": token, "account": account,
                       "confidence": float(confidence),
                       "learned_from": exc.get("id", "")})
    return merged


def _desc_from_issue(issue: str) -> str:
    m = re.search(r"'([^']+)'", issue or "")
    return m.group(1) if m else ""


def save_learned(path, learned_rules: list[dict]) -> None:
    """Write learned rules back to learned.yaml (empty list stays ``[]``)."""
    path = Path(path)
    if not learned_rules:
        path.write_text("# Learned rules (appended by `closeops rerun`).\n[]\n",
                        encoding="utf-8")
        return
    header = "# Learned rules (appended by `closeops rerun`).\n"
    path.write_text(header + yaml.safe_dump(learned_rules, sort_keys=False),
                    encoding="utf-8")


def load_learned_raw(path) -> list[dict]:
    """Load learned.yaml as raw dicts (for merging), tolerating an empty file."""
    path = Path(path)
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [dict(r) for r in (raw or []) if isinstance(r, dict)]
