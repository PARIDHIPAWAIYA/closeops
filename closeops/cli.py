"""closeops command-line interface.

Wave 1 (controls-ci) ships: check, report, status.
prepare / decide / apply / baseline / rerun are added by the Wave 2 workers.

Runnable as `closeops <cmd>` (entry point) or `python -m closeops.cli <cmd>`.
"""
from __future__ import annotations

import json
import sys

import click

from . import controls, report


@click.group()
def main():
    """Month-end close that runs as reviewed pull requests."""


@main.command()
@click.option("--json", "as_json", is_flag=True, help="Emit results as JSON.")
@click.option("--repo", default=".", help="Repository root.")
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
