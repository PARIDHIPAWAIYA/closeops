"""Tests for closeops.report — close-report.md and metrics.json."""
from __future__ import annotations

from closeops import report
from closeops.controls import ControlResult


def _results(all_pass=True):
    names = {
        1: "Ledger parses and balances", 2: "Trial balance nets to zero",
        3: "Period lock", 4: "Non-empty source", 5: "Materiality approved",
        6: "No duplicates", 7: "Bank reconciles", 8: "Suspense is zero",
        9: "No open exceptions", 10: "Dodo balance",
    }
    out = []
    for i in range(1, 11):
        passed = all_pass or i != 9
        out.append(ControlResult(f"C{i}", names[i], passed,
                                 "" if passed else "1 open exception"))
    return out


def test_control_table_lists_all_ten():
    md = report.control_table(_results())
    for i in range(1, 11):
        assert f"C{i}" in md


def test_control_table_marks_failure():
    md = report.control_table(_results(all_pass=False))
    assert "❌" in md
    assert "✅" in md


def test_build_metrics_counts_controls():
    m = report.build_metrics(_results(all_pass=False), exceptions=[])
    assert m["controls"]["total"] == 10
    assert m["controls"]["passed"] == 9
    assert m["controls"]["failed"] == 1


def test_build_report_has_sections():
    md = report.build_report(_results(), company={"name": "Northwind Labs Inc.",
                                                  "period": "2026-09"})
    assert "Northwind Labs Inc." in md
    assert "Controls" in md
    assert "C1" in md


def test_exceptions_table_collapses_when_long():
    exceptions = [{"id": f"BR-{i:03d}", "task": "bank-rec",
                   "issue": "x", "confidence": 0.7, "status": "open"}
                  for i in range(8)]
    md = report.exceptions_table(exceptions)
    assert "<details>" in md
    assert "BR-000" in md


def test_exceptions_table_short_not_collapsed():
    exceptions = [{"id": "BR-001", "task": "bank-rec", "issue": "x",
                   "confidence": 0.7, "status": "approved"}]
    md = report.exceptions_table(exceptions)
    assert "<details>" not in md
    assert "BR-001" in md


def test_reconciling_block_renders_items():
    reconciling = {"outstanding_cheques": [{"ref": "1042", "amount": "1500.00"}],
                   "deposits_in_transit": [{"ref": "DEP-1", "amount": "500.00"}]}
    md = report.reconciling_block(reconciling)
    assert "1042" in md
    assert "500.00" in md


def test_generate_writes_files(tmp_path):
    md, metrics = report.generate(tmp_path)
    assert (tmp_path / "close-report.md").exists()
    assert (tmp_path / "metrics.json").exists()
    assert "controls" in metrics
