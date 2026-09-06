"""close-report.md + metrics.json (plan section 8).

The report has: header, control table, metrics/funnel block, per-task entries,
exceptions table, and reconciling items. Long tables are wrapped in <details>
so the PR comment stays readable.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Sequence

import yaml
from beancount import loader
from beancount.core import data

from . import controls
from .controls import ControlResult

COLLAPSE_THRESHOLD = 5  # tables longer than this collapse into <details>


# --------------------------------------------------------------------------- #
# sections
# --------------------------------------------------------------------------- #

def control_table(results: Sequence[ControlResult]) -> str:
    lines = ["| # | Control | Result | Detail |",
             "|---|---------|--------|--------|"]
    for r in results:
        mark = "✅" if r.passed else "❌"
        detail = (r.detail or "").replace("|", "\\|")
        lines.append(f"| {r.id} | {r.name} | {mark} | {detail} |")
    passed = sum(1 for r in results if r.passed)
    lines.append("")
    lines.append(f"**{passed}/{len(results)} controls passed.**")
    return "\n".join(lines)


def metrics_block(metrics: dict) -> str:
    funnel = (metrics or {}).get("funnel", {})
    lines = []
    ctl = metrics.get("controls", {})
    lines.append(f"- Controls: {ctl.get('passed', 0)}/{ctl.get('total', 0)} passed")
    exc = metrics.get("exceptions", {})
    if exc:
        lines.append(f"- Exceptions: {exc.get('open', 0)} open, "
                     f"{exc.get('approved', 0)} approved, "
                     f"{exc.get('rejected', 0)} rejected")
    if funnel:
        lines.append("")
        lines.append("| Tier | Auto-rate |")
        lines.append("|------|-----------|")
        labels = [("exact_baseline", "Exact baseline"),
                  ("rules_only", "Rules only"),
                  ("agent", "Agent"),
                  ("after_review", "After review")]
        for key, label in labels:
            if key in funnel:
                lines.append(f"| {label} | {funnel[key]} |")
        run1 = metrics.get("run1", {})
        run2 = metrics.get("run2", {})
        if run1 or run2:
            lines.append("")
            lines.append(f"- Run 1 auto-rate: {run1.get('auto_rate', 'n/a')} · "
                         f"Run 2 auto-rate: {run2.get('auto_rate', 'n/a')}")
    return "\n".join(lines)


def _wrap_details(summary: str, body: str, collapse: bool) -> str:
    if not collapse:
        return body
    return f"<details>\n<summary>{summary}</summary>\n\n{body}\n</details>"


def exceptions_table(exceptions: Sequence[dict]) -> str:
    if not exceptions:
        return "_No exceptions._"
    header = ["| ID | Task | Issue | Confidence | Status |",
              "|----|------|-------|-----------|--------|"]
    rows = []
    for e in exceptions:
        issue = str(e.get("issue", "")).replace("|", "\\|")
        if len(issue) > 80:
            issue = issue[:77] + "..."
        rows.append(f"| {e.get('id', '?')} | {e.get('task', '')} | {issue} | "
                    f"{e.get('confidence', '')} | {e.get('status', '')} |")
    body = "\n".join(header + rows)
    collapse = len(exceptions) > COLLAPSE_THRESHOLD
    return _wrap_details(f"Exceptions ({len(exceptions)})", body, collapse)


def reconciling_block(reconciling: dict) -> str:
    if not reconciling:
        return "_No reconciling items._"
    lines = []
    for key, label in (("outstanding_cheques", "Outstanding cheques"),
                       ("deposits_in_transit", "Deposits in transit")):
        items = reconciling.get(key) or []
        if not items:
            continue
        lines.append(f"**{label}**")
        for item in items:
            if isinstance(item, dict):
                ref = item.get("ref", item.get("reference", ""))
                amt = item.get("amount", "")
                lines.append(f"- {ref} {amt}".rstrip())
            else:
                lines.append(f"- {item}")
    return "\n".join(lines) if lines else "_No reconciling items._"


def entries_block(entries_by_task: dict) -> str:
    if not entries_by_task:
        return "_No entries._"
    parts = []
    for task, count in entries_by_task.items():
        parts.append(f"- **{task}**: {count} entries")
    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# assembly
# --------------------------------------------------------------------------- #

def build_metrics(results: Sequence[ControlResult], exceptions: Sequence[dict],
                  existing: dict | None = None) -> dict:
    metrics = dict(existing or {})
    passed = sum(1 for r in results if r.passed)
    metrics["controls"] = {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": [r.as_dict() for r in results],
    }
    status_counts = {"open": 0, "approved": 0, "rejected": 0}
    for e in exceptions or []:
        s = e.get("status")
        if s in status_counts:
            status_counts[s] += 1
    status_counts["total"] = len(exceptions or [])
    metrics["exceptions"] = status_counts
    metrics.setdefault("funnel", {})
    return metrics


def build_report(results: Sequence[ControlResult], *, company: dict | None = None,
                 exceptions: Sequence[dict] | None = None,
                 reconciling: dict | None = None,
                 entries_by_task: dict | None = None,
                 metrics: dict | None = None) -> str:
    company = company or {}
    name = company.get("name", "Northwind Labs")
    period = company.get("period", "2026-09")
    passed = sum(1 for r in results if r.passed)
    overall = "PASS ✅" if passed == len(results) else "FAIL ❌"

    metrics = metrics or build_metrics(results, exceptions or [])

    parts = [
        f"# Close report — {name} ({period})",
        f"**Controls: {passed}/{len(results)} — {overall}**",
        "",
        "## Controls",
        control_table(results),
        "",
        "## " + "Metrics",
        metrics_block(metrics),
        "",
        "## Entries",
        entries_block(entries_by_task or {}),
        "",
        "## Exceptions",
        exceptions_table(exceptions or []),
        "",
        "## Reconciling items",
        reconciling_block(reconciling or {}),
        "",
    ]
    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# repo wiring
# --------------------------------------------------------------------------- #

def _load_exceptions(exceptions_dir: Path) -> list:
    out = []
    if exceptions_dir.exists():
        for path in sorted(exceptions_dir.glob("*.yaml")):
            try:
                items = yaml.safe_load(path.read_text(encoding="utf-8")) or []
            except yaml.YAMLError:
                items = []
            for item in items:
                if isinstance(item, dict):
                    out.append(item)
    return out


def _entries_by_task(ledger_path: Path) -> dict:
    counts: dict = {}
    if not ledger_path.exists():
        return counts
    entries, _, _ = loader.load_file(str(ledger_path))
    for e in entries:
        if not isinstance(e, data.Transaction):
            continue
        task = (e.meta or {}).get("task")
        if task:
            counts[task] = counts.get(task, 0) + 1
    return counts


def generate(repo_root=".") -> tuple[str, dict]:
    """Run controls, build close-report.md + metrics.json, write both, and return
    (markdown, metrics)."""
    root = Path(repo_root)
    results = controls.run_all(root)
    company = controls.load_company(root / "data" / "company.json")
    exceptions = _load_exceptions(root / "exceptions")
    reconciling = controls._load_json(
        root / "exceptions" / "bank-rec-reconciling.json", {})
    entries_by_task = _entries_by_task(root / "ledger" / "main.beancount")

    existing = controls._load_json(root / "metrics.json", {})
    metrics = build_metrics(results, exceptions,
                            existing={"funnel": existing.get("funnel", {}),
                                      "run1": existing.get("run1", {}),
                                      "run2": existing.get("run2", {})})

    md = build_report(results, company=company, exceptions=exceptions,
                      reconciling=reconciling, entries_by_task=entries_by_task,
                      metrics=metrics)

    (root / "close-report.md").write_text(md, encoding="utf-8")
    (root / "metrics.json").write_text(
        json.dumps(metrics, indent=2, default=str), encoding="utf-8")
    return md, metrics
