"""bank-rec tests: one per trap T1-T15, plus the decision contract, demotion,
bean-check, reconciling output, baseline funnel and rerun learning.

Apply mutates the ledger and exceptions, so every apply-based test runs against a
throwaway copy of the repo's data/ and ledger/ trees in tmp_path.
"""
from __future__ import annotations

import json
import shutil
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from closeops import baseline, controls
from closeops.tasks import bank_rec

REPO = Path(__file__).resolve().parents[1]
MAT = Decimal("10000.00")


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def candidates(repo):
    """Candidates for a first close, from the pre-close sandbox in ``repo``.

    Derived from the same sandbox the tests act on, so candidate ids and line
    numbers always agree with what ``apply`` will see.
    """
    return bank_rec.prepare(str(repo), write=False)


def _reset_to_pre_close(root):
    """Put a sandbox copy back into a first-close state.

    The live repo carries a completed September close (posted entries and the
    rules learned from it). These tests describe the close as it runs the first
    time, so blank the period files and the learned rules in the copy.
    """
    (root / "data" / "rules" / "learned.yaml").write_text(
        "# Learned rules appended by `closeops rerun`. Empty for tests." + chr(10) + "[]" + chr(10),
        encoding="utf-8")
    period = root / "ledger" / "2026-09"
    if period.is_dir():
        for f in period.glob("*.beancount"):
            f.write_text(";; written by the close" + chr(10), encoding="utf-8")


@pytest.fixture
def repo(tmp_path):
    """A throwaway repo copy with data/ and ledger/; prepare already run.

    Learned rules are reset to empty so these tests describe a first close and do
    not depend on what earlier real closes taught the live repo.
    """
    for sub in ("data", "ledger"):
        shutil.copytree(REPO / sub, tmp_path / sub)
    (tmp_path / "exceptions").mkdir()
    _reset_to_pre_close(tmp_path)
    bank_rec.prepare(str(tmp_path))
    return tmp_path


def line_by(candidates, **kw):
    """First candidates line matching every field in kw (desc uses 'in')."""
    for ln in candidates["lines"]:
        if "desc" in kw and kw["desc"] not in ln["description"]:
            continue
        if "amount" in kw and ln["amount"] != kw["amount"]:
            continue
        if "ref" in kw and ln["reference"] != kw["ref"]:
            continue
        return ln
    raise AssertionError(f"no line matches {kw}")


def kinds(ln):
    return [c["kind"] for c in ln["candidates"]]


def top(ln):
    return ln["candidates"][0]


def is_auto(ln):
    has_dup = any(c["kind"] == "duplicate" for c in ln["candidates"])
    return not has_dup and bank_rec.classify(top(ln), MAT, "Equity:Suspense")


# --------------------------------------------------------------------------- #
# traps T1-T15
# --------------------------------------------------------------------------- #

def test_t1_exact_ap(candidates):
    ln = line_by(candidates, desc="ACME CORP PAYMENT")
    t = top(ln)
    assert t["kind"] == "exact"
    assert Decimal(t["score"]) >= Decimal("0.95")
    assert "AP-0001" in t["evidence"]
    assert is_auto(ln)


def test_t2_exact_ar(candidates):
    ln = line_by(candidates, desc="DEPOSIT NORTHSTAR")
    t = top(ln)
    assert t["kind"] == "exact"
    assert any(e.startswith("AR-") for e in t["evidence"])
    assert is_auto(ln)


def test_t3_rule_recurring(candidates):
    ln = line_by(candidates, desc="WEWORK MEMBERSHIP")
    t = top(ln)
    assert t["kind"] == "rule"
    assert t["account"] == "Expenses:Rent"
    assert is_auto(ln)


def test_t4_bank_fee_and_interest(candidates):
    fee = line_by(candidates, desc="SERVICE FEE")
    assert top(fee)["account"] == "Expenses:BankFees" and is_auto(fee)
    interest = line_by(candidates, desc="INTEREST PAID")
    assert top(interest)["account"] == "Income:Interest" and is_auto(interest)


def test_t5_split(candidates):
    ln = line_by(candidates, desc="SPLITCO 1 PAYMENT")
    t = top(ln)
    assert t["kind"] == "split"
    assert Decimal(t["score"]) == Decimal("0.70")
    assert sum(1 for p in t["postings"] if p["account"] == "Liabilities:AP") >= 2
    assert not is_auto(ln)  # < 0.9 -> exception


def test_t6_partial(candidates):
    ln = line_by(candidates, desc="PARTIAL 1 PAYMENT")
    t = top(ln)
    assert t["kind"] == "partial"
    assert Decimal(t["score"]) == Decimal("0.65")
    assert "remainder" in t["narration"].lower()
    assert not is_auto(ln)


def test_t7_fx(candidates):
    ln = line_by(candidates, desc="EUROVEND 1 EUR PAYMENT")
    t = top(ln)
    assert t["kind"] == "fx"
    assert Decimal(t["score"]) == Decimal("0.80")
    assert any(p["account"] == "Expenses:FX" for p in t["postings"])
    assert not is_auto(ln)


def test_t8_duplicate_demoted(candidates):
    zooms = [ln for ln in candidates["lines"] if ln["description"] == "ZOOM VIDEO"]
    assert len(zooms) == 2
    first, second = zooms
    assert "duplicate" not in kinds(first) and is_auto(first)
    assert "duplicate" in kinds(second)
    # a 0.90 rule candidate still exists, but the duplicate flag blocks auto-post
    assert any(c["kind"] == "rule" and Decimal(c["score"]) >= Decimal("0.9")
               for c in second["candidates"])
    assert not is_auto(second)


def test_t9_unknown_to_suspense(candidates):
    ln = line_by(candidates, desc="SHENZHEN")
    t = top(ln)
    assert t["kind"] == "none"
    assert Decimal(t["score"]) < Decimal("0.5")
    assert any(p["account"] == "Equity:Suspense" for p in t["postings"])
    assert not is_auto(ln)


def test_t10_discount_shortpay(candidates):
    ln = line_by(candidates, desc="DISCOUNT 1 PAYMENT")
    t = top(ln)
    # a 2% short-pay reads as a partial (remainder = the discount)
    assert t["kind"] == "partial"
    assert not is_auto(ln)


def test_t13_pays_august_bill(candidates):
    ln = line_by(candidates, desc="LEGAL EAGLE LLP PAYMENT")
    t = top(ln)
    assert t["kind"] == "exact"
    assert "AP-0074" in t["evidence"]  # the August bill
    assert is_auto(ln)


def test_t14_payout_first_auto_second_exception(candidates):
    payouts = [ln for ln in candidates["lines"] if ln["description"] == "DODO PAYOUT"]
    assert len(payouts) == 2
    first = line_by(candidates, ref="po_001")
    second = line_by(candidates, ref="po_002")
    tf = top(first)
    assert tf["kind"] == "payout" and Decimal(tf["score"]) == Decimal("0.95")
    assert any(p["account"] == "Expenses:PaymentProcessing" for p in tf["postings"])
    ts = top(second)
    assert ts["kind"] == "payout" and Decimal(ts["score"]) == Decimal("0.80")
    assert not is_auto(second)  # fee missing -> exception


def test_t15_same_amount_two_vendors(candidates):
    datadog = line_by(candidates, desc="DATADOG SUBSCRIPTION")
    aws = line_by(candidates, desc="AMZN AWS EC2 USAGE")
    # both have two tied exact candidates; the counterparty token breaks the tie
    for ln, want in ((datadog, "AP-0077"), (aws, "AP-0076")):
        exacts = [c for c in ln["candidates"] if c["kind"] == "exact"]
        assert len(exacts) == 2
        best = top(ln)
        assert Decimal(best["score"]) == Decimal("0.98")
        assert want in best["evidence"]


# --------------------------------------------------------------------------- #
# decision contract (enforced in apply, independent of decide)
# --------------------------------------------------------------------------- #

def _decide(candidates, overrides=None):
    """Reference decisions with optional per-line choice overrides ({line: choice})."""
    dec = bank_rec.reference_decisions(candidates, MAT)
    if overrides:
        for d in dec["decisions"]:
            if d["line"] in overrides:
                d["choice"] = overrides[d["line"]]
    return dec


def _booked_sources(summary):
    return {e["meta"]["source"] for e in summary["booked"]}


def test_below_threshold_never_auto_posts(repo, candidates):
    """Choosing a 0.70 split candidate must still route to an exception."""
    split = line_by(candidates, desc="SPLITCO 1 PAYMENT")
    chosen = top(split)["id"]
    dec = _decide(candidates, {split["line"]: chosen})
    summary = bank_rec.apply(str(repo), decisions=dec)
    assert split["source"] not in _booked_sources(summary)
    excs = yaml.safe_load((repo / "exceptions" / "bank-rec.yaml").read_text(encoding="utf-8"))
    assert any(e["source"] == split["source"] for e in excs)


def test_suspense_never_auto_posts(repo, candidates):
    unknown = line_by(candidates, desc="SHENZHEN")
    chosen = top(unknown)["id"]
    dec = _decide(candidates, {unknown["line"]: chosen})
    summary = bank_rec.apply(str(repo), decisions=dec)
    assert unknown["source"] not in _booked_sources(summary)


def test_duplicate_demotion_honored(repo, candidates):
    """T8: even with a 0.90 candidate, an 'exception' choice must not auto-post."""
    second = [ln for ln in candidates["lines"] if ln["description"] == "ZOOM VIDEO"][1]
    dec = _decide(candidates, {second["line"]: "exception"})
    summary = bank_rec.apply(str(repo), decisions=dec)
    assert second["source"] not in _booked_sources(summary)


def test_t15_conflicting_description_demotion_honored(repo, candidates):
    """T15: demoting the ambiguous same-amount vendor line to an exception."""
    aws = line_by(candidates, desc="AMZN AWS EC2 USAGE")
    dec = _decide(candidates, {aws["line"]: "exception"})
    summary = bank_rec.apply(str(repo), decisions=dec)
    assert aws["source"] not in _booked_sources(summary)
    excs = yaml.safe_load((repo / "exceptions" / "bank-rec.yaml").read_text(encoding="utf-8"))
    assert any(e["source"] == aws["source"] for e in excs)


def test_material_line_needs_approval(repo, candidates):
    """A >= materiality auto-candidate (GUSTO 12,500) routes to an exception."""
    gusto = line_by(candidates, desc="GUSTO PAYROLL", amount="-12500.00")
    assert Decimal(top(gusto)["score"]) >= Decimal("0.9")  # would auto-post but for size
    dec = _decide(candidates)
    summary = bank_rec.apply(str(repo), decisions=dec)
    assert gusto["source"] not in _booked_sources(summary)


# --------------------------------------------------------------------------- #
# apply: bean-check, reconciling, coverage
# --------------------------------------------------------------------------- #

def test_apply_passes_bean_check(repo, candidates):
    dec = _decide(candidates)
    summary = bank_rec.apply(str(repo), decisions=dec)
    assert summary["bean_check_ok"], summary["bean_check_output"]
    assert summary["auto_posts"] == 94
    assert summary["open_exceptions"] == 22


def test_apply_requires_all_lines_covered(repo, candidates):
    dec = _decide(candidates)
    dec["decisions"] = dec["decisions"][:-1]  # drop one
    with pytest.raises(ValueError):
        bank_rec.apply(str(repo), decisions=dec)


def test_find_payout_amount_fallback_is_unambiguous():
    a = {"payout_id": "po_a", "amount": "4850.00", "fee": "0.00"}
    b = {"payout_id": "po_b", "amount": "4850.00", "fee": "50.00"}
    c = {"payout_id": "po_c", "amount": "9700.00", "fee": "300.00"}
    # explicit reference always wins
    assert bank_rec._find_payout([a, b, c], "po_b", Decimal("4850.00")) is b
    # no reference + a unique amount -> that payout
    assert bank_rec._find_payout([a, c], "", Decimal("9700.00")) is c
    # no reference + two payouts share the amount -> refuse to guess
    assert bank_rec._find_payout([a, b], "", Decimal("4850.00")) is None


def test_apply_rejects_unknown_choice_id(repo, candidates):
    dec = _decide(candidates)
    dec["decisions"][0]["choice"] = "L2-not-a-real-candidate"
    with pytest.raises(ValueError, match="unknown candidate"):
        bank_rec.apply(str(repo), decisions=dec)


def test_reconciling_written(repo, candidates):
    dec = _decide(candidates)
    bank_rec.apply(str(repo), decisions=dec)
    recon = json.loads((repo / "exceptions" / "bank-rec-reconciling.json").read_text())
    assert len(recon["outstanding_cheques"]) == 3
    assert len(recon["deposits_in_transit"]) == 1


# --------------------------------------------------------------------------- #
# controls C7 and C10 become satisfiable after approval
# --------------------------------------------------------------------------- #

def _approve_all(repo, reclassify_suspense_to="Expenses:Office"):
    path = repo / "exceptions" / "bank-rec.yaml"
    items = yaml.safe_load(path.read_text(encoding="utf-8"))
    for it in items:
        it["status"] = "approved"
        it["approved_by"] = "controller"
        for p in it["proposed_entry"].get("postings", []):
            if p["account"] == "Equity:Suspense":
                p["account"] = reclassify_suspense_to
    path.write_text(yaml.safe_dump(items, sort_keys=False, allow_unicode=True),
                    encoding="utf-8")


def test_all_controls_pass_after_approval(repo, candidates):
    dec = _decide(candidates)
    bank_rec.apply(str(repo), decisions=dec)      # first pass: exceptions open
    _approve_all(repo)
    bank_rec.apply(str(repo), decisions=dec)      # second pass: post approved
    results = controls.run_all(str(repo))
    failed = [r.id for r in results if not r.passed]
    assert not failed, {r.id: r.detail for r in results if not r.passed}


def test_c7_and_c10_specifically(repo, candidates):
    dec = _decide(candidates)
    bank_rec.apply(str(repo), decisions=dec)
    _approve_all(repo)
    bank_rec.apply(str(repo), decisions=dec)
    by_id = {r.id: r for r in controls.run_all(str(repo))}
    assert by_id["C7"].passed, by_id["C7"].detail
    assert by_id["C10"].passed, by_id["C10"].detail


# --------------------------------------------------------------------------- #
# baseline funnel + rerun learning
# --------------------------------------------------------------------------- #

def test_baseline_funnel_monotonic(candidates):
    tiers = baseline.compute_tiers(candidates, MAT)
    exact = tiers["exact_baseline"]["auto"]
    rules_only = tiers["rules_only"]["auto"]
    agent = tiers["agent"]["auto"]
    review = tiers["after_review"]["auto"]
    assert exact < rules_only <= agent < review == 116


def test_baseline_exact_tier_excludes_flagged_duplicate():
    """A line with a single qualifying exact candidate AND a duplicate flag must
    not count toward the exact tier (the contract routes duplicates to review)."""
    cand = {"lines": [{"line": 1, "candidates": [
        {"kind": "exact", "score": "0.98",
         "postings": [{"account": "Liabilities:AP", "amount": "100.00"},
                      {"account": "Assets:Bank:Operating", "amount": "-100.00"}]},
        {"kind": "duplicate", "score": "0.40",
         "postings": [{"account": "Expenses:Software", "amount": "100.00"},
                      {"account": "Assets:Bank:Operating", "amount": "-100.00"}]},
    ]}]}
    tiers = baseline.compute_tiers(cand, MAT,
                                   decisions={"decisions": [{"line": 1, "choice": "exception"}]})
    assert tiers["exact_baseline"]["auto"] == 0
    assert tiers["rules_only"]["auto"] == 0


def test_baseline_writes_metrics(repo):
    baseline.run(str(repo))
    metrics = json.loads((repo / "metrics.json").read_text())
    assert "funnel" in metrics
    assert "exact_baseline" in metrics["funnel"]


def test_rerun_does_not_learn_unsafe_rules(repo, candidates):
    """Approving everything must NOT learn fx/split/partial/payout rules, nor a
    rule for the material GUSTO line; the material line stays an exception in run 2."""
    dec = _decide(candidates)
    bank_rec.apply(str(repo), decisions=dec)
    _approve_all(repo)
    bank_rec.rerun(str(repo))

    learned = yaml.safe_load((repo / "data" / "rules" / "learned.yaml").read_text()) or []
    tokens = {r["match"] for r in learned}
    accounts = {r["account"] for r in learned}
    assert "GUSTO" not in tokens                        # material + seed rule exists
    assert "EUROVEND" not in tokens                     # fx exception, not learnable
    assert "Expenses:FX" not in accounts
    assert "Expenses:PaymentProcessing" not in accounts  # payout fee, not learnable

    cands2 = json.loads((repo / "work" / "bank-rec" / "candidates.json").read_text())
    gusto = line_by(cands2, desc="GUSTO PAYROLL", amount="-12500.00")
    assert not is_auto(gusto)   # material line must remain an exception in run 2


def test_rerun_learns_rule_and_raises_auto_rate(repo, candidates):
    # resolve the close, then approve the unknown-payee items reclassified to a
    # real account so a rule can be learned from them.
    dec = _decide(candidates)
    bank_rec.apply(str(repo), decisions=dec)
    path = repo / "exceptions" / "bank-rec.yaml"
    items = yaml.safe_load(path.read_text(encoding="utf-8"))
    for it in items:
        if "SHENZHEN" in it.get("description", ""):
            it["status"] = "approved"
            it["approved_by"] = "controller"
            for p in it["proposed_entry"]["postings"]:
                if p["account"] == "Equity:Suspense":
                    p["account"] = "Expenses:Office"
    path.write_text(yaml.safe_dump(items, sort_keys=False, allow_unicode=True),
                    encoding="utf-8")

    result = bank_rec.rerun(str(repo))
    assert result["learned_added"] >= 1
    assert Decimal(result["run2"]["auto_rate"].rstrip("%")) > \
        Decimal(result["run1"]["auto_rate"].rstrip("%"))
    learned = yaml.safe_load((repo / "data" / "rules" / "learned.yaml").read_text())
    assert any(r["match"] == "SHENZHEN" for r in learned)
