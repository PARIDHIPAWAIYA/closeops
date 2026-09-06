"""Matching-rule loading (load only).

Learning (appending approved exceptions to ``learned.yaml``) is a Wave 2 task and
is intentionally *not* implemented here. This module only reads the seed rules and
any already-learned rules and exposes a matcher for recurring bank lines.
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
