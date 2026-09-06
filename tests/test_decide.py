"""Tests for closeops decide: packet renderer + decisions validator.

No API key required: the packet renders from a fixture candidates.json and the
validator checks a hand-written decisions.json. Neatlogs is exercised separately
in test_trace.py and is skipped when NEATLOGS_API_KEY is unset.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from closeops import decide

FIX = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.fixture
def candidates():
    return _load("candidates-bank-rec.json")


@pytest.fixture
def decisions():
    return _load("decisions-bank-rec.json")


# --------------------------------------------------------------------------- #
# packet renderer
# --------------------------------------------------------------------------- #

def test_packet_renders_for_real_candidates(candidates):
    packet = decide.render_packet(candidates)
    assert isinstance(packet, str) and packet.strip()
    # contract, chart of accounts and rules sections are present
    low = packet.lower()
    assert "contract" in low
    assert "0.9" in packet  # the auto-post threshold is stated
    assert "chart of accounts" in low
    # every line and its candidate ids + evidence appear
    for line in candidates["lines"]:
        assert f"{line['line']}" in packet
        for cand in line["candidates"]:
            assert cand["id"] in packet
            for ev in cand["evidence"]:
                assert ev in packet


def test_packet_line_blocks_stay_within_20_lines(candidates):
    """Each statement line is rendered as a compact chunk of at most 20 lines."""
    packet = decide.render_packet(candidates)
    blocks = decide.packet_line_blocks(packet)
    assert len(blocks) == len(candidates["lines"])
    for block in blocks:
        assert len(block.splitlines()) <= 20


# --------------------------------------------------------------------------- #
# validator — happy path
# --------------------------------------------------------------------------- #

def test_fixture_decisions_pass_validate(candidates, decisions):
    assert decide.validate_decisions(candidates, decisions) == []


# --------------------------------------------------------------------------- #
# validator — planted violations
# --------------------------------------------------------------------------- #

def _set_choice(decisions, line, choice):
    d = copy.deepcopy(decisions)
    for dec in d["decisions"]:
        if dec["line"] == line:
            dec["choice"] = choice
    return d


def test_rejects_autopost_below_threshold(candidates, decisions):
    # L41 split scores 0.70; choosing it as an auto-post violates the contract.
    bad = _set_choice(decisions, 41, "L41-split")
    violations = decide.validate_decisions(candidates, bad)
    assert violations
    assert any("41" in v and "0.9" in v for v in violations)


def test_rejects_unknown_candidate_id(candidates, decisions):
    bad = _set_choice(decisions, 11, "L11-nope")
    violations = decide.validate_decisions(candidates, bad)
    assert violations
    assert any("L11-nope" in v for v in violations)


def test_rejects_missing_line(candidates, decisions):
    bad = copy.deepcopy(decisions)
    bad["decisions"] = [d for d in bad["decisions"] if d["line"] != 23]
    violations = decide.validate_decisions(candidates, bad)
    assert violations
    assert any("23" in v for v in violations)


def test_rejects_suspense_autopost(candidates, decisions):
    # L68 "none" candidate posts to Equity:Suspense; it can never auto-post.
    bad = _set_choice(decisions, 68, "L68-none")
    violations = decide.validate_decisions(candidates, bad)
    assert violations
    assert any("suspense" in v.lower() for v in violations)


def test_rejects_invented_amounts(candidates, decisions):
    # A decision that carries its own postings must match the chosen candidate's.
    bad = copy.deepcopy(decisions)
    for dec in bad["decisions"]:
        if dec["line"] == 11:
            dec["postings"] = [
                {"account": "Liabilities:AP", "amount": "9999.00"},
                {"account": "Assets:Bank:Operating", "amount": "-9999.00"},
            ]
    violations = decide.validate_decisions(candidates, bad)
    assert violations
    assert any("11" in v and ("amount" in v.lower() or "posting" in v.lower())
               for v in violations)


def test_rejects_missing_rationale(candidates, decisions):
    bad = copy.deepcopy(decisions)
    for dec in bad["decisions"]:
        if dec["line"] == 17:
            dec["rationale"] = "   "
    violations = decide.validate_decisions(candidates, bad)
    assert violations
    assert any("17" in v and "rationale" in v.lower() for v in violations)


def test_rejects_decision_for_unknown_line(candidates, decisions):
    bad = copy.deepcopy(decisions)
    bad["decisions"].append(
        {"line": 999, "choice": "exception", "confidence": "0.5", "rationale": "x"})
    violations = decide.validate_decisions(candidates, bad)
    assert violations
    assert any("999" in v for v in violations)


def test_demotion_of_high_score_candidate_is_allowed(candidates, decisions):
    # L98 has a 0.95 exact candidate; choosing "exception" instead is a valid demotion.
    demoted = _set_choice(decisions, 98, "exception")
    assert decide.validate_decisions(candidates, demoted) == []


# --------------------------------------------------------------------------- #
# apply gate
# --------------------------------------------------------------------------- #

def test_apply_refuses_unvalidated_decisions(candidates, decisions):
    bad = _set_choice(decisions, 41, "L41-split")  # a contract violation
    with pytest.raises(decide.DecisionsInvalid):
        decide.require_validated(candidates, bad)


def test_apply_accepts_validated_decisions(candidates, decisions):
    # No exception raised when decisions are clean.
    decide.require_validated(candidates, decisions)


# --------------------------------------------------------------------------- #
# provenance
# --------------------------------------------------------------------------- #

def test_stamp_provenance_records_worker_session_and_time(decisions):
    stamped = decide.stamp_provenance(
        decisions, session_id="closeops-6", timestamp="2026-09-06T12:00:00Z",
        trace="neatlogs:abc123")
    assert stamped["decided_by"] == "worker"
    assert stamped["session_id"] == "closeops-6"
    assert stamped["timestamp"] == "2026-09-06T12:00:00Z"
    assert stamped["trace"] == "neatlogs:abc123"
    # original is not mutated
    assert "decided_by" not in decisions
