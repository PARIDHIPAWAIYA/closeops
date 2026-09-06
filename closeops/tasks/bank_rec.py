"""bank-rec task: prepare deterministic candidates, apply decisions.

`prepare` reads the bank statement, the ledger's open items (AP/AR by ``invoice:``
meta), the Dodo payouts and the matching rules, then writes
``work/bank-rec/candidates.json`` — every statement line with its ranked
candidate matches and evidence ids (plan §6.1).

`apply` reads those candidates plus a worker-written ``decisions.json`` and the
existing ``exceptions/bank-rec.yaml`` (for controller approvals), enforces the
decision contract (plan §6) independently of `decide`, and renders:
  * ``ledger/2026-09/bank-rec.beancount`` — auto-posts + approved exceptions,
  * ``exceptions/bank-rec.yaml`` — items needing a human, with proposed entries,
  * ``exceptions/bank-rec-reconciling.json`` — outstanding cheques / deposits in
    transit for control C7.

Money is always :class:`decimal.Decimal`; never a float.
"""
from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path
from typing import Optional

import yaml

from .. import controls, ledger, rules

TASK = "bank-rec"
PERIOD = "2026-09"
PERIOD_END = "2026-09-30"

CENT = Decimal("0.01")
AUTO_THRESHOLD = Decimal("0.9")
FX_PCT = Decimal("0.01")   # 1% FX/rounding tolerance
FX_ABS = Decimal("5")      # or $5, whichever is larger


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #

def _dec(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def load_bank_lines(csv_path) -> list[dict]:
    """Parse the bank CSV into signed-Decimal line dicts (with a stable lineno)."""
    path = Path(csv_path)
    lines: list[dict] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        next(reader, None)  # header
        for i, row in enumerate(reader):
            if not row:
                continue
            date, desc, amount, balance, reference = (row + ["", "", "", "", ""])[:5]
            lines.append({
                "lineno": i + 2,  # 1-based incl. header row
                "date": date,
                "description": desc,
                "amount": _dec(amount),
                "reference": reference,
            })
    return lines


def _is_bank_rec_entry(entry) -> bool:
    """True for a transaction rendered by this task (so prepare can ignore its own
    postings and stay idempotent even after apply has populated the ledger)."""
    meta = getattr(entry, "meta", None) or {}
    if meta.get("task") == TASK:
        return True
    fname = str(meta.get("filename", "")).replace("\\", "/")
    return fname.endswith("2026-09/bank-rec.beancount")


def _open_items(entries, account) -> list[dict]:
    live = [e for e in entries if not _is_bank_rec_entry(e)]
    items = ledger.open_items(live, account, as_of=PERIOD_END)
    for it in items:
        it["remaining"] = _dec(it["remaining"])
    return items


# --------------------------------------------------------------------------- #
# candidate construction
# --------------------------------------------------------------------------- #

def _cand(cid, kind, score, postings, evidence, narration, account="") -> dict:
    return {
        "id": cid,
        "kind": kind,
        "score": f"{_dec(score):.2f}",
        "account": account,
        "narration": narration,
        "postings": postings,
        "evidence": list(evidence),
    }


def _posting(account, amount, meta=None) -> dict:
    p = {"account": account, "amount": f"{_dec(amount):.2f}"}
    if meta:
        p["meta"] = dict(meta)
    return p


def _token_hit(payee: str, desc: str) -> bool:
    payee = (payee or "").strip().upper()
    return bool(payee) and payee in (desc or "").upper()


def _subset_summing(items: list[dict], target: Decimal, lo: int, hi: int):
    """Smallest-index subset (size lo..hi) of items whose remaining sums to target."""
    n = len(items)
    for size in range(lo, min(hi, n) + 1):
        # index combinations, deterministic order
        import itertools
        for combo in itertools.combinations(range(n), size):
            total = sum((items[i]["remaining"] for i in combo), Decimal("0"))
            if total == target:
                return [items[i] for i in combo]
    return None


def build_candidates(line: dict, open_ap, open_ar, payouts, rule_list,
                     company: dict, seen_keys: set) -> list[dict]:
    """Rank deterministic candidates for one bank line (plan §6.1)."""
    amt = _dec(line["amount"])
    mag = abs(amt)
    desc = line["description"]
    tag = f"L{line['lineno']}"
    src = f"data/bank/sep-2026.csv#L{line['lineno']}"
    bank = company["bank_account"]
    suspense = company["suspense_account"]
    dodo = company["dodo_account"]
    cands: list[dict] = []

    # -- exact: open AP (payments) or AR (deposits) of equal magnitude --------
    # Same-amount matches are only emitted when at least one such open item
    # shares a counterparty token with the description. That keeps genuine
    # matches (and T15's same-amount ties) while dropping coincidental
    # amount collisions with unrelated bills (e.g. WEWORK 4100 vs a 4100 bill).
    if amt < 0:
        same = [it for it in open_ap if it["remaining"] == mag]
        if any(_token_hit(it.get("payee"), desc) for it in same):
            for it in same:
                score = Decimal("0.95") + (Decimal("0.03") if _token_hit(it.get("payee"), desc) else Decimal("0"))
                cands.append(_cand(
                    f"{tag}-exact-{it['invoice']}", "exact", score,
                    [_posting("Liabilities:AP", mag, {"invoice": it["invoice"]}),
                     _posting(bank, amt)],
                    [it["invoice"], src],
                    f"{desc} - pays {it['invoice']}", "Liabilities:AP"))
    elif amt > 0:
        # AR is an asset: open_items returns a negative "remaining"; compare on
        # its absolute value.
        same = [it for it in open_ar if abs(it["remaining"]) == mag]
        if any(_token_hit(it.get("payee"), desc) for it in same):
            for it in same:
                score = Decimal("0.95") + (Decimal("0.03") if _token_hit(it.get("payee"), desc) else Decimal("0"))
                cands.append(_cand(
                    f"{tag}-exact-{it['invoice']}", "exact", score,
                    [_posting(bank, amt),
                     _posting("Assets:AR", -mag, {"invoice": it["invoice"]})],
                    [it["invoice"], src],
                    f"{desc} - collects {it['invoice']}", "Assets:AR"))

    # -- rule: recurring payee (matching + learned) --------------------------
    rule = rules.match(desc, rule_list)
    if rule is not None:
        if amt < 0:
            postings = [_posting(rule.account, mag), _posting(bank, amt)]
        else:
            postings = [_posting(bank, amt), _posting(rule.account, -mag)]
        cands.append(_cand(
            f"{tag}-rule", "rule", rule.confidence, postings,
            [f"rule:{rule.match}", src],
            f"{desc} - rule {rule.match}", rule.account))

    # -- payout: Dodo processor payout (net = gross - refunds - fee) ----------
    if "DODO PAYOUT" in desc.upper() and amt > 0:
        po = _find_payout(payouts, line["reference"], mag)
        if po is not None:
            fee = _dec(po.get("fee", "0"))
            net = mag
            if fee > 0:
                score = Decimal("0.95")
                postings = [_posting(bank, net),
                            _posting("Expenses:PaymentProcessing", fee),
                            _posting(dodo, -(net + fee))]
                narr = f"Dodo payout {po['payout_id']} (net {net} + fee {fee})"
            else:
                score = Decimal("0.80")  # fee absent from the record (trap T14)
                postings = [_posting(bank, net), _posting(dodo, -net)]
                narr = f"Dodo payout {po['payout_id']} (fee missing)"
            cands.append(_cand(
                f"{tag}-payout-{po['payout_id']}", "payout", score, postings,
                [po["payout_id"], src], narr, dodo))

    # -- named-bill matches: split / fx / partial (payments) -----------------
    if amt < 0:
        named = [it for it in open_ap if _token_hit(it.get("payee"), desc)]
        # split: 2-3 named bills summing to the payment
        subset = _subset_summing(named, mag, 2, 3)
        if subset:
            postings = [_posting("Liabilities:AP", it["remaining"],
                                 {"invoice": it["invoice"]}) for it in subset]
            postings.append(_posting(bank, amt))
            cands.append(_cand(
                f"{tag}-split", "split", Decimal("0.70"), postings,
                [it["invoice"] for it in subset] + [src],
                f"{desc} - split across {len(subset)} bills", "Liabilities:AP"))
        # fx / partial against a single named bill
        for it in named:
            rem = it["remaining"]
            diff = abs(mag - rem)
            if diff == 0:
                continue  # that's an exact match, already handled
            if diff <= max(rem * FX_PCT, FX_ABS):
                postings = [_posting("Liabilities:AP", rem, {"invoice": it["invoice"]}),
                            _posting("Expenses:FX", mag - rem),
                            _posting(bank, amt)]
                cands.append(_cand(
                    f"{tag}-fx-{it['invoice']}", "fx", Decimal("0.80"), postings,
                    [it["invoice"], src],
                    f"{desc} - {it['invoice']} + FX/rounding", "Liabilities:AP"))
                break
            if mag < rem:
                postings = [_posting("Liabilities:AP", mag, {"invoice": it["invoice"]}),
                            _posting(bank, amt)]
                cands.append(_cand(
                    f"{tag}-partial-{it['invoice']}", "partial", Decimal("0.65"),
                    postings, [it["invoice"], src],
                    f"{desc} - partial on {it['invoice']} "
                    f"(remainder {rem - mag} open)", "Liabilities:AP"))
                break

    # -- duplicate flag: same (date, amount, description) seen earlier --------
    if (line["date"], amt, desc) in seen_keys:
        # propose the best real account we can, but flag low so it can't auto-post
        if rule is not None:
            acct = rule.account
        else:
            acct = suspense
        if amt < 0:
            postings = [_posting(acct, mag), _posting(bank, amt)]
        else:
            postings = [_posting(bank, amt), _posting(acct, -mag)]
        cands.append(_cand(
            f"{tag}-duplicate", "duplicate", Decimal("0.40"), postings,
            [src], f"{desc} - possible duplicate charge", acct))

    # -- none: nothing matched -> Suspense (never auto-posts) -----------------
    if not any(c["kind"] not in ("duplicate",) for c in cands):
        if amt < 0:
            postings = [_posting(suspense, mag), _posting(bank, amt)]
        else:
            postings = [_posting(bank, amt), _posting(suspense, -mag)]
        cands.append(_cand(
            f"{tag}-none", "none", Decimal("0.20"), postings,
            [src], f"{desc} - unknown, route to Suspense", suspense))

    cands.sort(key=lambda c: Decimal(c["score"]), reverse=True)
    return cands


def _find_payout(payouts, reference, mag) -> Optional[dict]:
    for po in payouts:
        if reference and po.get("payout_id") == reference:
            return po
    for po in payouts:
        if _dec(po.get("amount", "0")) == mag:
            return po
    return None


# --------------------------------------------------------------------------- #
# prepare
# --------------------------------------------------------------------------- #

def prepare(repo_root=".", rule_list=None, write=True) -> dict:
    """Build candidates for every bank line; write work/bank-rec/candidates.json.

    ``rule_list`` overrides the loaded rules (used by `rerun` to compare a
    seed-only run against one with learned rules). ``write=False`` skips the file.
    """
    root = Path(repo_root)
    company = _company(root)

    entries, _, _ = ledger.load_ledger(root / "ledger" / "main.beancount")
    open_ap = _open_items(entries, "Liabilities:AP")
    open_ar = _open_items(entries, "Assets:AR")
    payouts = _load_json(root / "data" / "dodo" / "payouts.json", [])
    if rule_list is None:
        rule_list = rules.load_rules(root / "data" / "rules" / "matching.yaml",
                                     root / "data" / "rules" / "learned.yaml")

    bank_lines = load_bank_lines(root / "data" / "bank" / "sep-2026.csv")
    seen_keys: set = set()
    out_lines = []
    for line in bank_lines:
        cands = build_candidates(line, open_ap, open_ar, payouts, rule_list,
                                 company, seen_keys)
        seen_keys.add((line["date"], line["amount"], line["description"]))
        out_lines.append({
            "line": line["lineno"],
            "date": line["date"],
            "description": line["description"],
            "amount": f"{line['amount']:.2f}",
            "reference": line["reference"],
            "source": f"data/bank/sep-2026.csv#L{line['lineno']}",
            "candidates": cands,
        })

    result = {"task": TASK, "period": PERIOD, "lines": out_lines}
    if write:
        out_path = root / "work" / "bank-rec" / "candidates.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


# --------------------------------------------------------------------------- #
# decision contract (enforced independently of `decide`)
# --------------------------------------------------------------------------- #

def _max_posting_mag(cand: dict) -> Decimal:
    return max((abs(_dec(p["amount"])) for p in cand["postings"]), default=Decimal("0"))


def _posts_to(cand: dict, account: str) -> bool:
    return any(p["account"] == account for p in cand["postings"])


def classify(cand: dict, materiality: Decimal, suspense: str) -> bool:
    """True iff this candidate may auto-post under the contract (plan §6).

    Auto-post only when score >= 0.9, never to Suspense, and never a posting at
    or above materiality (those need a controller's approved-by, so they route
    to an exception first)."""
    if cand is None:
        return False
    if Decimal(cand["score"]) < AUTO_THRESHOLD:
        return False
    if cand["kind"] == "none" or _posts_to(cand, suspense):
        return False
    if _max_posting_mag(cand) >= materiality:
        return False
    return True


def reference_decisions(candidates: dict, materiality: Decimal) -> dict:
    """Deterministic reference decider used for metrics (agent tier), the rerun
    comparison and tests. NOT the runtime judge — the AO worker writes the real
    ``decisions.json``; this just picks the top candidate and demotes anything
    the contract forbids from auto-posting (low score, Suspense, duplicate,
    material)."""
    decisions = []
    for ln in candidates["lines"]:
        cands = ln["candidates"]
        top = cands[0] if cands else None
        has_dup = any(c["kind"] == "duplicate" for c in cands)
        # a duplicate flag or a non-auto top -> exception; else auto-post
        auto = top is not None and not has_dup and classify(top, materiality,
                                                            "Equity:Suspense")
        if auto:
            decisions.append({"line": ln["line"], "choice": top["id"],
                              "rationale": f"auto: {top['kind']} {top['score']}",
                              "confidence": top["score"]})
        else:
            reason = "possible duplicate" if has_dup else (
                "needs review" if top else "no candidate")
            decisions.append({"line": ln["line"], "choice": "exception",
                              "rationale": reason,
                              "confidence": top["score"] if top else "0.20"})
    return {"task": TASK, "period": PERIOD, "decided_by": "reference",
            "decisions": decisions}


# --------------------------------------------------------------------------- #
# apply
# --------------------------------------------------------------------------- #

def apply(repo_root=".", decisions=None, run_bean_check=True) -> dict:
    """Render the ledger + exceptions from decisions, enforcing the contract."""
    root = Path(repo_root)
    company = _company(root)
    materiality = _dec(company["materiality"])
    suspense = company["suspense_account"]

    candidates = _load_json(root / "work" / "bank-rec" / "candidates.json", None)
    if candidates is None:
        raise FileNotFoundError(
            "work/bank-rec/candidates.json missing — run `closeops prepare bank-rec`")
    if decisions is None:
        decisions = _load_json(root / "work" / "bank-rec" / "decisions.json", None)
    if decisions is None:
        raise FileNotFoundError(
            "decisions.json missing — run `closeops decide bank-rec` and write it")

    cand_by_id = {}
    line_by_no = {}
    for ln in candidates["lines"]:
        line_by_no[ln["line"]] = ln
        for c in ln["candidates"]:
            cand_by_id[c["id"]] = c
    dec_by_line = {int(d["line"]): d for d in decisions["decisions"]}

    # contract check: every line covered, every choice valid
    missing = [ln["line"] for ln in candidates["lines"] if ln["line"] not in dec_by_line]
    if missing:
        raise ValueError(f"decisions missing for lines: {missing[:10]}")

    prior = _load_prior_exceptions(root)

    # Provenance: decide-llm's --validate stamps top-level trace / decided_by /
    # session_id / timestamp on decisions.json. Copy them onto every entry and
    # exception so each judgment is attributable; fall back to constants.
    prov = {
        "trace": decisions.get("trace") or _trace_id(),
        "decided_by": decisions.get("decided_by") or "worker",
        "session_id": decisions.get("session_id"),
        "timestamp": decisions.get("timestamp"),
    }
    auto_posts: list[dict] = []
    exceptions: list[dict] = []
    exc_seq = 0

    for ln in candidates["lines"]:
        dec = dec_by_line[ln["line"]]
        choice = dec["choice"]
        chosen = cand_by_id.get(choice) if choice != "exception" else None
        top = ln["candidates"][0] if ln["candidates"] else None

        may_auto = choice != "exception" and classify(chosen, materiality, suspense)
        if may_auto:
            auto_posts.append(_entry_from_candidate(ln, chosen, company, prov,
                                                    approved_by=None))
            continue

        # exception: proposed_entry is the chosen candidate, else the top one
        proposed = chosen if chosen is not None else top
        exc_seq += 1
        exc = _build_exception(ln, proposed, dec, exc_seq, prov, prior, materiality)
        exceptions.append(exc)
        if exc["status"] == "approved" and exc.get("proposed_entry", {}).get("postings"):
            auto_posts.append(_entry_from_exception(ln, exc, dec))

    _write_beancount(root, auto_posts)
    _write_exceptions(root, exceptions)
    reconciling = _write_reconciling(root)

    ok, out = (True, "")
    if run_bean_check:
        ok, out = ledger.bean_check(root / "ledger" / "main.beancount")

    return {
        "booked": auto_posts,
        "auto_posts": len(auto_posts),
        "exceptions": len(exceptions),
        "open_exceptions": sum(1 for e in exceptions if e["status"] == "open"),
        "approved": sum(1 for e in exceptions if e["status"] == "approved"),
        "rejected": sum(1 for e in exceptions if e["status"] == "rejected"),
        "reconciling": reconciling,
        "bean_check_ok": ok,
        "bean_check_output": out,
    }


def _entry_from_candidate(ln, cand, company, prov, approved_by) -> dict:
    meta = {
        "source": ln["source"],
        "task": TASK,
        "confidence": str(cand["score"]),
        "decided_by": prov["decided_by"],
        "trace": prov["trace"],
    }
    if approved_by:
        meta["approved-by"] = approved_by
    return {
        "date": ln["date"],
        "payee": ln["description"],
        "narration": cand.get("narration", ln["description"]),
        "meta": meta,
        "postings": cand["postings"],
    }


def _entry_from_exception(ln, exc, dec) -> dict:
    """Render an approved exception's proposed entry (as edited by the controller)
    with an ``approved-by`` meta so control C5 accepts material items."""
    pe = exc["proposed_entry"]
    meta = {
        "source": ln["source"],
        "task": TASK,
        "confidence": str(exc.get("confidence", "")),
        "decided_by": exc.get("decided_by", dec.get("decided_by", "worker")),
        "trace": exc.get("trace", ""),
        "approved-by": exc.get("approved_by") or "controller",
    }
    return {
        "date": pe.get("date", ln["date"]),
        "payee": ln["description"],
        "narration": pe.get("narration", ln["description"]),
        "meta": meta,
        "postings": pe["postings"],
    }


def _build_exception(ln, proposed, dec, seq, prov, prior, materiality) -> dict:
    exc_id = f"BR-{seq:03d}"
    proposed_entry = {}
    if proposed is not None:
        proposed_entry = {
            "date": ln["date"],
            "narration": proposed.get("narration", ln["description"]),
            "postings": proposed["postings"],
        }
    # A line demoted for being a possible duplicate is a "duplicate" exception even
    # though its proposed entry is the best real candidate — so it reads correctly
    # and is never learned from. Its confidence reflects the duplicate suspicion.
    dup = next((c for c in ln["candidates"] if c["kind"] == "duplicate"), None)
    if dup is not None:
        kind = "duplicate"
        confidence = str(dup["score"])
    else:
        kind = proposed["kind"] if proposed else "none"
        confidence = str(proposed["score"]) if proposed else "0.20"
    is_material = proposed is not None and _max_posting_mag(proposed) >= materiality
    exc = {
        "id": exc_id,
        "task": TASK,
        "source": ln["source"],
        "description": ln["description"],
        "kind": kind,
        "issue": _issue_text(ln, kind, is_material),
        "proposed_entry": proposed_entry,
        "confidence": confidence,
        "decided_by": prov["decided_by"],
        "trace": prov["trace"],
        "status": "open",
        "reviewer_note": "",
    }
    if prov.get("session_id"):
        exc["session_id"] = prov["session_id"]
    if prov.get("timestamp"):
        exc["timestamp"] = prov["timestamp"]
    # carry controller review from a previous run, matched by source line
    was = prior.get(ln["source"])
    if was:
        exc["status"] = was.get("status", "open")
        exc["reviewer_note"] = was.get("reviewer_note", "")
        if was.get("approved_by"):
            exc["approved_by"] = was["approved_by"]
        if was.get("trace"):
            exc["trace"] = was["trace"]
        # the controller may have edited the proposed entry (e.g. reclassifying
        # a Suspense line to a real account); keep their version.
        if was.get("proposed_entry"):
            exc["proposed_entry"] = was["proposed_entry"]
    return exc


def _issue_text(ln, kind, is_material=False) -> str:
    if is_material and kind in ("exact", "rule"):
        base = "material amount - needs controller approval"
    elif kind in ("exact", "rule"):
        base = "ambiguous or conflicting match - demoted for review"
    else:
        base = {
            "split": "matches only as a split across multiple bills",
            "partial": "partial payment, remainder stays open",
            "fx": "amount differs from the bill within FX/rounding tolerance",
            "duplicate": "possible duplicate charge",
            "none": "unknown counterparty, no confident match",
            "payout": "processor payout with fee missing from the record",
        }.get(kind, "needs controller review")
    return f"Line {ln['line']} ({ln['amount']} '{ln['description']}') - {base}"


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #

def _write_beancount(root: Path, entries: list[dict]) -> None:
    parts = [";; ledger/2026-09/bank-rec.beancount",
             ";; Generated by `closeops apply bank-rec`. Do not edit by hand.", ""]
    # deterministic order: by (date, description)
    for e in sorted(entries, key=lambda x: (x["date"], x["payee"], x["narration"])):
        parts.append(f'{e["date"]} * "{_esc(e["payee"])}" "{_esc(e["narration"])}"')
        for k, v in e["meta"].items():
            parts.append(f'  {k}: "{_esc(str(v))}"')
        for p in e["postings"]:
            meta = p.get("meta") or {}
            parts.append(f'  {p["account"]}  {_dec(p["amount"]):.2f} USD')
            for mk, mv in meta.items():
                parts.append(f'    {mk}: "{_esc(str(mv))}"')
        parts.append("")
    out = root / "ledger" / "2026-09" / "bank-rec.beancount"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts) + "\n", encoding="utf-8")


def _esc(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def _write_exceptions(root: Path, exceptions: list[dict]) -> None:
    out = root / "exceptions"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "bank-rec.yaml"
    if not exceptions:
        path.write_text("[]\n", encoding="utf-8")
        return
    path.write_text(yaml.safe_dump(exceptions, sort_keys=False, allow_unicode=True),
                    encoding="utf-8")


def _write_reconciling(root: Path) -> dict:
    """Read the ledger's reconciling entries and write bank-rec-reconciling.json.

    Amounts are the signed contribution consumed by control C7
    (expected = statement + Σoutstanding − Σdeposits): an outstanding cheque uses
    its bank-posting delta (negative); a deposit in transit uses the negated
    delta so C7's ``− deposits`` re-adds it to the book balance.
    """
    entries, _, _ = ledger.load_ledger(root / "ledger" / "main.beancount")
    from beancount.core import data
    bank_acct = _company(root)["bank_account"]
    outstanding, deposits = [], []
    for e in entries:
        if not isinstance(e, data.Transaction):
            continue
        tag = (e.meta or {}).get("reconciling")
        if not tag:
            continue
        bank_amt = Decimal("0")
        for p in e.postings:
            if p.account == bank_acct and p.units is not None:
                bank_amt += p.units.number
        item = {"reference": tag, "date": e.date.isoformat(),
                "payee": e.payee or "", "amount": f"{bank_amt:.2f}"}
        if str(tag).startswith("cheque"):
            outstanding.append(item)
        else:
            item["amount"] = f"{-bank_amt:.2f}"
            deposits.append(item)
    data_out = {"outstanding_cheques": outstanding, "deposits_in_transit": deposits}
    path = root / "exceptions" / "bank-rec-reconciling.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data_out, indent=2), encoding="utf-8")
    return data_out


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _company(root: Path) -> dict:
    c = controls.load_company(root / "data" / "company.json")
    return {
        "bank_account": c.get("bank_account", "Assets:Bank:Operating"),
        "suspense_account": c.get("suspense_account", "Equity:Suspense"),
        "dodo_account": c.get("processor_clearing", c.get("dodo_account",
                                                          "Assets:Dodo:Balance")),
        "materiality": c.get("materiality", "10000.00"),
        "period": c.get("period", PERIOD),
    }


def _load_json(path, default):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _load_prior_exceptions(root: Path) -> dict:
    path = root / "exceptions" / "bank-rec.yaml"
    if not path.exists():
        return {}
    try:
        items = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    except yaml.YAMLError:
        return {}
    out = {}
    for it in items:
        if isinstance(it, dict) and it.get("source"):
            out[it["source"]] = it
    return out


def _trace_id() -> str:
    try:  # pragma: no cover - only when neatlogs/otel is active
        from opentelemetry import trace as _t
        ctx = _t.get_current_span().get_span_context()
        if ctx and ctx.trace_id:
            return f"neatlogs:{format(ctx.trace_id, '032x')}"
    except Exception:
        pass
    return f"closeops:{TASK}:{PERIOD}"


# --------------------------------------------------------------------------- #
# rerun: learn from approved exceptions, show run 1 -> run 2 improvement
# --------------------------------------------------------------------------- #

def _auto_rate(candidates: dict, materiality: Decimal) -> dict:
    dec = reference_decisions(candidates, materiality)
    auto = sum(1 for d in dec["decisions"] if d["choice"] != "exception")
    total = len(dec["decisions"])
    pct = (Decimal(auto) / Decimal(total) * 100).quantize(Decimal("0.1")) if total else Decimal("0")
    return {"auto": auto, "total": total, "auto_rate": f"{pct}%"}


def rerun(repo_root=".") -> dict:
    """Learn rules from approved exceptions and report run 1 -> run 2 auto-rate.

    Run 1 uses only the seed rules; run 2 uses the seed rules plus everything
    learned from approved exceptions. New learned rules are appended to
    ``data/rules/learned.yaml`` and run 2's higher auto-rate is written to
    ``metrics.json``.
    """
    root = Path(repo_root)
    materiality = _dec(_company(root)["materiality"])
    matching_path = root / "data" / "rules" / "matching.yaml"
    learned_path = root / "data" / "rules" / "learned.yaml"

    # run 1: seed rules only
    seed_rules = rules.load_rules(matching_path, None)
    cands1 = prepare(repo_root, rule_list=seed_rules, write=False)
    run1 = _auto_rate(cands1, materiality)

    # learn from approved exceptions (safely: see rules.learn_from_exceptions)
    exceptions = _load_yaml(root / "exceptions" / "bank-rec.yaml")
    existing = rules.load_learned_raw(learned_path)
    existing_rules = rules.load_rules(matching_path, learned_path)
    merged = rules.learn_from_exceptions(
        exceptions, existing, existing_rules=existing_rules, materiality=materiality)
    learned_added = len(merged) - len(existing)
    rules.save_learned(learned_path, merged)

    # run 2: seed + learned
    full_rules = rules.load_rules(matching_path, learned_path)
    cands2 = prepare(repo_root, rule_list=full_rules, write=True)
    run2 = _auto_rate(cands2, materiality)

    _merge_metrics(root, {"run1": run1, "run2": run2})
    return {"run1": run1, "run2": run2, "learned_added": learned_added,
            "learned_rules": merged}


def _load_yaml(path) -> list:
    p = Path(path)
    if not p.exists():
        return []
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or []
    except yaml.YAMLError:
        return []


def _merge_metrics(root: Path, patch: dict) -> None:
    path = root / "metrics.json"
    existing = _load_json(path, {}) or {}
    existing.update(patch)
    path.write_text(json.dumps(existing, indent=2, default=str), encoding="utf-8")
