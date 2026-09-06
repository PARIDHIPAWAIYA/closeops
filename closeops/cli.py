"""closeops command-line interface.

Wave 1 (controls-ci) ships: check, report, status.
prepare / decide / apply / baseline / rerun are added by the Wave 2 workers.

Runnable as `closeops <cmd>` (entry point) or `python -m closeops.cli <cmd>`.
"""
from __future__ import annotations

import json
import sys

import click

from . import controls, decide as decide_mod, report, trace
from .tasks import accruals as accruals_task
from .tasks import depreciation as depreciation_task

# Task registry for prepare/apply. Wave 2 workers append their tasks here;
# keep entries alphabetical so additions merge without conflict.
TASKS = {
    "accruals": accruals_task,
    "depreciation": depreciation_task,
}


def _task_module(task):
    mod = TASKS.get(task)
    if mod is None:
        known = ", ".join(sorted(TASKS))
        raise click.ClickException(f"unknown task {task!r}; known tasks: {known}")
    return mod


@click.group()
def main():
    """Month-end close that runs as reviewed pull requests."""
    # Neatlogs tracing: a no-op unless NEATLOGS_API_KEY is set (zero spend, no key
    # needed in CI). Wired here so every subcommand shows up in one close session.
    trace.init()


@main.command()
@click.argument("task")
@click.option("--repo", default=".", help="Repository root.")
def prepare(task, repo):
    """Compute deterministic candidates for TASK into work/<task>/."""
    mod = _task_module(task)
    mod.prepare(repo)
    click.echo(f"Prepared {task}: wrote work/{task}/candidates.json")


@main.command()
@click.argument("task")
@click.option("--repo", default=".", help="Repository root.")
def apply(task, repo):
    """Render TASK entries into ledger/2026-09/ and run bean-check."""
    mod = _task_module(task)
    result = mod.apply(repo)
    booked = result.get("booked", [])
    click.echo(f"Applied {task}: {len(booked)} entry(ies) booked")
    if result.get("exceptions"):
        click.echo(f"  {result.get('open_exceptions', 0)} open exception(s)")
    if result.get("flagged"):
        click.echo(f"  flagged (no entry): {', '.join(result['flagged'])}")
    if not result.get("bean_check_ok", True):
        click.echo("bean-check FAILED:")
        click.echo(result.get("bean_check_output", ""))
        sys.exit(1)


@main.command()
@click.option("--json", "as_json", is_flag=True, help="Emit results as JSON.")
@click.option("--repo", default=".", help="Repository root.")
@trace.workflow_span("check", "close")
def check(as_json, repo):
    """Run the ten accounting controls; exit non-zero if any fail."""
    results = controls.run_all(repo)
    if as_json:
        click.echo(json.dumps([r.as_dict() for r in results], indent=2))
    else:
        click.echo(controls.render_table(results))
    if any(not r.passed for r in results):
        sys.exit(1)


@main.command(name="report")
@click.option("--repo", default=".", help="Repository root.")
def report_cmd(repo):
    """Write close-report.md and metrics.json."""
    _, metrics = report.generate(repo)
    passed = metrics["controls"]["passed"]
    total = metrics["controls"]["total"]
    click.echo(f"Wrote close-report.md and metrics.json ({passed}/{total} controls passed).")


@main.command()
@click.argument("task")
@click.option("--packet", "as_packet", is_flag=True,
              help="Render work/<task>/packet.md for the worker.")
@click.option("--validate", "as_validate", is_flag=True,
              help="Validate work/<task>/decisions.json against the contract.")
@click.option("--repo", default=".", help="Repository root.")
def decide(task, as_packet, as_validate, repo):
    """Render the decision packet or validate the worker's decisions."""
    if as_packet == as_validate:
        raise click.UsageError("pass exactly one of --packet or --validate")

    @trace.workflow_span("decide", task)
    def _run():
        return _decide(task, as_packet, repo)

    _run()


def _decide(task, as_packet, repo):
    if as_packet:
        candidates = decide_mod.load_json(decide_mod.candidates_path(task, repo))
        company = controls.load_company(_company_path(repo))
        rules = _load_rules(repo)
        packet = decide_mod.render_packet(candidates, company=company, rules=rules)
        out_path = decide_mod.packet_path(task, repo)
        decide_mod.write_text(out_path, packet)
        n = len(candidates.get("lines", []))
        click.echo(f"Wrote {out_path} ({n} line(s)).")
        return

    # --validate
    candidates = decide_mod.load_json(decide_mod.candidates_path(task, repo))
    decisions = decide_mod.load_json(decide_mod.decisions_path(task, repo))
    company = controls.load_company(_company_path(repo))
    suspense = company.get("suspense_account") or decide_mod.DEFAULT_SUSPENSE
    violations = decide_mod.validate_decisions(candidates, decisions, suspense)
    if violations:
        click.echo(f"{len(violations)} violation(s):")
        for v in violations:
            click.echo(f"  - {v}")
        sys.exit(1)
    stamped = decide_mod.stamp_provenance(decisions)
    decide_mod.write_text(
        decide_mod.decisions_path(task, repo),
        json.dumps(stamped, indent=2) + "\n")
    click.echo(f"decisions.json valid: {len(candidates.get('lines', []))} line(s), "
               f"decided_by={stamped['decided_by']} session={stamped['session_id']}.")


def _company_path(repo):
    from pathlib import Path
    return Path(repo) / "data" / "company.json"


def _load_rules(repo):
    from pathlib import Path
    from . import rules as rules_mod
    root = Path(repo)
    matching = root / "data" / "rules" / "matching.yaml"
    learned = root / "data" / "rules" / "learned.yaml"
    try:
        return rules_mod.load_rules(matching, learned)
    except Exception:
        return []


@main.command()
@click.option("--repo", default=".", help="Repository root.")
def status(repo):
    """Print a one-screen summary of controls and exceptions."""
    results = controls.run_all(repo)
    passed = sum(1 for r in results if r.passed)
    click.echo(f"Controls: {passed}/{len(results)} passed")
    for r in results:
        mark = "PASS" if r.passed else "FAIL"
        click.echo(f"  {r.id:<4} {mark}  {r.name}")
    if passed != len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
