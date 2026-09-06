"""closeops decide — the judgment step, zero paid API (plan section 7).

Two halves, both deterministic Python:

* ``render_packet`` turns the deterministic ``candidates.json`` (prepare output,
  plan 6.1) into a compact ``packet.md``: the decision contract, chart of
  accounts, matching rules, and every statement line with its ranked candidates
  and evidence ids, each line a chunk of at most 20 lines. An AO worker (Claude
  Code on the Team subscription — no API spend) reads it and writes
  ``decisions.json``.
* ``validate_decisions`` gates that ``decisions.json`` against the schema and the
  decision contract before ``apply`` may touch the ledger.

Money is always :class:`decimal.Decimal`; never a float.
"""
from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from . import trace as _trace

AUTO_POST_THRESHOLD = Decimal("0.9")
PACKET_CHUNK = 20  # each statement line renders as a chunk of at most this many lines
DEFAULT_SUSPENSE = "Equity:Suspense"


class DecisionsInvalid(Exception):
    """Raised by :func:`require_validated` when the decision contract is broken."""

    def __init__(self, violations):
        self.violations = list(violations)
        super().__init__(f"{len(self.violations)} decision violation(s)")


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #

def _dec(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        raise TypeError("money must not be a float: %r" % (value,))
    return Decimal(str(value))


def _decisions_list(decisions):
    """Accept either a bare list or an object with a ``decisions`` array."""
    if isinstance(decisions, dict):
        return list(decisions.get("decisions", []))
    return list(decisions or [])


def _norm_postings(postings):
    out = []
    for p in postings or []:
        out.append((p.get("account", ""), _dec(p.get("amount", "0"))))
    return sorted(out)


def _postings_equal(a, b) -> bool:
    try:
        return _norm_postings(a) == _norm_postings(b)
    except (InvalidOperation, TypeError):
        return False


def _posts_to(candidate, account) -> bool:
    if candidate.get("account") == account:
        return True
    return any(p.get("account") == account for p in candidate.get("postings", []))


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# packet renderer
# --------------------------------------------------------------------------- #

def _contract_section(task: str) -> list:
    return [
        "## Contract",
        f'Write `work/{task}/decisions.json`: one entry per line below, each',
        '`{line, choice, rationale, confidence}`. `choice` is a candidate id or the',
        'literal `"exception"`.',
        "",
        "- Auto-post ONLY when the chosen candidate's score >= 0.90.",
        '- Anything below 0.90 -> `"exception"` (the best candidate becomes the',
        "  proposed entry). Give a one-sentence rationale citing evidence ids.",
        '- You MAY demote a >= 0.90 candidate to `"exception"` (duplicate,',
        "  conflicting description).",
        "- Never auto-post to Equity:Suspense. Never invent amounts.",
        "",
    ]


def _accounts_section(candidates, accounts) -> list:
    names = list(accounts or candidates.get("accounts") or [])
    if not names:
        seen = []
        for ln in candidates.get("lines", []):
            for c in ln.get("candidates", []):
                for p in c.get("postings", []):
                    acct = p.get("account")
                    if acct and acct not in seen:
                        seen.append(acct)
        names = seen
    return ["## Chart of accounts", ", ".join(names) if names else "(none)", ""]


def _rule_row(rule) -> str:
    if isinstance(rule, dict):
        match = rule.get("match", "")
        account = rule.get("account", "")
        conf = rule.get("confidence", "")
    else:  # rules.Rule dataclass
        match = getattr(rule, "match", "")
        account = getattr(rule, "account", "")
        conf = getattr(rule, "confidence", "")
    return f"- {match} -> {account} ({conf})"


def _rules_section(rules) -> list:
    out = ["## Matching rules"]
    rows = [_rule_row(r) for r in (rules or [])]
    out += rows if rows else ["(none loaded)"]
    out += [""]
    return out


def _line_block(line) -> list:
    n = line["line"]
    head = (f'### Line {n}  {line.get("date", "")}  {line.get("amount", "")}  '
            f'"{line.get("description", "")}"')
    source = line.get("source", "")
    if source:
        head += f"  [{source}]"
    out = [head]
    for c in line.get("candidates", []):
        evidence = ", ".join(c.get("evidence") or []) or "-"
        account = c.get("account") or "-"
        out.append(
            f'- {c["id"]}  {c.get("kind", "")}  {c.get("score", "")}  '
            f'{account}  evidence: {evidence}')
    out.append('Choose: <id or "exception">')
    return out


def render_packet(candidates, company=None, rules=None, accounts=None) -> str:
    """Render ``candidates.json`` as a compact decision packet (markdown)."""
    task = candidates.get("task", "bank-rec")
    period = candidates.get("period", "2026-09")
    out = [f"# Decision packet — {task} ({period})", ""]
    if company and company.get("name"):
        out += [f"Company: {company['name']}  ·  Materiality: "
                f"{company.get('materiality', '')}", ""]
    out += _contract_section(task)
    out += _accounts_section(candidates, accounts)
    out += _rules_section(rules)
    out += ["## Lines", ""]
    for line in candidates.get("lines", []):
        block = _line_block(line)
        if len(block) > PACKET_CHUNK:  # keep every line a <=20-line chunk
            block = block[:PACKET_CHUNK - 1] + ['Choose: <id or "exception">']
        out += block
        out += [""]
    return "\n".join(out).rstrip() + "\n"


def packet_line_blocks(packet: str) -> list:
    """Split a rendered packet into its per-line ``### Line`` chunks."""
    blocks = []
    current = None
    for text in packet.splitlines():
        if text.startswith("### Line"):
            if current is not None:
                blocks.append("\n".join(current).rstrip())
            current = [text]
        elif current is not None:
            current.append(text)
    if current is not None:
        blocks.append("\n".join(current).rstrip())
    return blocks


# --------------------------------------------------------------------------- #
# validator
# --------------------------------------------------------------------------- #

def validate_decisions(candidates, decisions, suspense_account=DEFAULT_SUSPENSE) -> list:
    """Return a list of human-readable contract/schema violations ([] == valid).

    Schema: every line covered exactly once; each decision has ``choice``,
    ``rationale`` and ``confidence``; ``choice`` is a real candidate id or
    ``"exception"``. Contract: auto-post only when the chosen candidate scores
    >= 0.90 (demotions to ``"exception"`` are allowed); no Suspense auto-posts;
    no invented amounts (any decision postings must equal the candidate's).
    """
    violations = []
    cand_by_line = {}
    line_order = []
    for ln in candidates.get("lines", []):
        n = int(ln["line"])
        line_order.append(n)
        cand_by_line[n] = {c["id"]: c for c in ln.get("candidates", [])}

    seen = set()
    for d in _decisions_list(decisions):
        if "line" not in d:
            violations.append(f"decision missing 'line': {d!r}")
            continue
        try:
            n = int(d["line"])
        except (TypeError, ValueError):
            violations.append(f"decision has a non-integer line: {d.get('line')!r}")
            continue
        if n in seen:
            violations.append(f"line {n}: duplicate decision")
        seen.add(n)
        if n not in cand_by_line:
            violations.append(f"line {n}: decision for a line not in candidates.json")
            continue

        choice = d.get("choice")
        if not choice or not str(choice).strip():
            violations.append(f"line {n}: missing 'choice'")
            choice = None
        if not d.get("rationale") or not str(d.get("rationale")).strip():
            violations.append(f"line {n}: missing 'rationale'")
        conf = d.get("confidence")
        if conf is None or str(conf).strip() == "":
            violations.append(f"line {n}: missing 'confidence'")
        else:
            try:
                _dec(conf)
            except (InvalidOperation, TypeError):
                violations.append(f"line {n}: confidence is not a number: {conf!r}")

        if choice is None or choice == "exception":
            continue

        candidate = cand_by_line[n].get(choice)
        if candidate is None:
            violations.append(
                f"line {n}: choice '{choice}' is not a candidate id for this line")
            continue

        try:
            score = _dec(candidate.get("score", "0"))
        except (InvalidOperation, TypeError):
            score = Decimal("0")
        if score < AUTO_POST_THRESHOLD:
            violations.append(
                f"line {n}: auto-post of '{choice}' scores {score} < 0.9; "
                "must be an exception")
        if _posts_to(candidate, suspense_account):
            violations.append(
                f"line {n}: '{choice}' auto-posts to {suspense_account} (Suspense); "
                "not allowed")
        if d.get("postings") is not None and not _postings_equal(
                d["postings"], candidate.get("postings", [])):
            violations.append(
                f"line {n}: decision postings differ from candidate '{choice}' "
                "postings (invented amount)")

    for n in line_order:
        if n not in seen:
            violations.append(f"line {n}: no decision (every line must be covered)")

    return violations


def require_validated(candidates, decisions, suspense_account=DEFAULT_SUSPENSE) -> None:
    """Raise :class:`DecisionsInvalid` if the decisions break the contract.

    ``apply`` calls this so it refuses to run until ``decide --validate`` passes.
    """
    violations = validate_decisions(candidates, decisions, suspense_account)
    if violations:
        raise DecisionsInvalid(violations)


# --------------------------------------------------------------------------- #
# provenance
# --------------------------------------------------------------------------- #

def stamp_provenance(decisions, session_id=None, timestamp=None, trace=None) -> dict:
    """Return a copy of ``decisions`` stamped with who decided, when, and the trace.

    ``decided_by`` is always ``"worker"``; ``session_id`` defaults to the
    ``AO_SESSION_ID`` env var; ``trace`` defaults to the active Neatlogs trace id
    (or its workflow+timestamp fallback). The input is not mutated.
    """
    if isinstance(decisions, dict):
        out = copy.deepcopy(decisions)
    else:
        out = {"decisions": copy.deepcopy(list(decisions))}
    out["decided_by"] = "worker"
    out["session_id"] = (session_id if session_id is not None
                         else os.environ.get("AO_SESSION_ID"))
    out["timestamp"] = timestamp or _now_iso()
    out["trace"] = trace or _trace.current_trace_id()
    return out


# --------------------------------------------------------------------------- #
# repo paths / IO (used by the CLI)
# --------------------------------------------------------------------------- #

def candidates_path(task, repo="."):
    return Path(repo) / "work" / task / "candidates.json"


def decisions_path(task, repo="."):
    return Path(repo) / "work" / task / "decisions.json"


def packet_path(task, repo="."):
    return Path(repo) / "work" / task / "packet.md"


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
