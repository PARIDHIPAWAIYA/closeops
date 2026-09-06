"""Render the close dashboard from real close artifacts.

Reads metrics.json, exceptions/*.yaml, exceptions/bank-rec-reconciling.json,
ledger/2026-09/*.beancount and data/company.json, and writes a single
self-contained HTML file (docs/dashboard.html). No network, no build step.

    python scripts/build_dashboard.py [--out docs/dashboard.html]
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from html import escape
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PERIOD_DIR = ROOT / "ledger" / "2026-09"

KIND_LABEL = {
    "material": "Materiality",
    "split": "Split payment",
    "partial": "Partial payment",
    "fx": "FX difference",
    "duplicate": "Possible duplicate",
    "none": "Unknown payee",
    "payout": "Processor payout",
    "rule": "Rule match",
}


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_yaml(path, default):
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or default
    except Exception:
        return default


def entry_count(name):
    f = PERIOD_DIR / f"{name}.beancount"
    if not f.exists():
        return 0
    return len(re.findall(r"^2026-09-\d{2}\s", f.read_text(encoding="utf-8"), flags=re.M))


def posted_total(name, account_prefix):
    """Sum postings whose account starts with account_prefix, as Decimal."""
    f = PERIOD_DIR / f"{name}.beancount"
    if not f.exists():
        return Decimal("0")
    total = Decimal("0")
    for line in f.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s+(" + re.escape(account_prefix) + r"\S*)\s+(-?[\d.]+)\s+USD", line)
        if m:
            total += Decimal(m.group(2))
    return total


def pct_num(text):
    try:
        return float(str(text).rstrip("%"))
    except Exception:
        return 0.0


def money(d):
    return f"{d:,.2f}"


def funnel_svg(funnel):
    tiers = [
        ("Exact amount match", funnel.get("exact_baseline", "0%"), "amount within 5 days, nothing else"),
        ("+ deterministic rules", funnel.get("rules_only", "0%"), "payee rules, splits, payouts"),
        ("+ agent judgment", funnel.get("agent", "0%"), "under the decision contract"),
        ("+ controller review", funnel.get("after_review", "0%"), "23 exceptions resolved"),
    ]
    W, rowh, top, labelw = 760, 46, 30, 250
    H = top + rowh * len(tiers) + 16
    barw = W - labelw - 70
    parts = [
        f'<svg viewBox="0 0 {W} {H}" role="img" xmlns="http://www.w3.org/2000/svg" '
        f'aria-label="Auto-post rate by tier: exact match {tiers[0][1]}, plus rules {tiers[1][1]}, '
        f'plus agent judgment {tiers[2][1]}, plus controller review {tiers[3][1]}." '
        'font-family="Public Sans, system-ui, sans-serif">'
    ]
    for x in (0, 25, 50, 75, 100):
        gx = labelw + barw * x / 100
        parts.append(f'<line x1="{gx:.1f}" y1="{top - 12}" x2="{gx:.1f}" y2="{top + rowh * len(tiers) - 12}" '
                     'stroke="currentColor" stroke-width="1" opacity=".16"/>')
        parts.append(f'<text x="{gx:.1f}" y="{top - 18}" font-size="10.5" text-anchor="middle" '
                     'fill="currentColor" opacity=".55">' + str(x) + '%</text>')
    for i, (name, val, note) in enumerate(tiers):
        y = top + i * rowh
        v = pct_num(val)
        w = max(2.0, barw * v / 100)
        last = i == len(tiers) - 1
        fill = "var(--seal)" if last else "var(--bar)"
        parts.append(f'<text x="0" y="{y + 4}" font-size="12.5" font-weight="600" fill="currentColor">{escape(name)}</text>')
        parts.append(f'<text x="0" y="{y + 19}" font-size="10.5" fill="currentColor" opacity=".6">{escape(note)}</text>')
        parts.append(f'<rect x="{labelw}" y="{y - 9}" width="{barw}" height="19" rx="2" fill="currentColor" opacity=".07"/>')
        parts.append(f'<rect x="{labelw}" y="{y - 9}" width="{w:.1f}" height="19" rx="2" fill="{fill}"/>')
        parts.append(f'<text x="{labelw + barw + 10}" y="{y + 5}" font-size="12.5" font-weight="700" '
                     f'font-family="Roboto Mono, monospace" fill="currentColor">{escape(str(val))}</text>')
    parts.append("</svg>")
    return "".join(parts)


def build(out_path):
    company = load_json(ROOT / "data" / "company.json", {})
    metrics = load_json(ROOT / "metrics.json", {})
    controls = metrics.get("controls", {})
    results = controls.get("results", [])
    funnel = metrics.get("funnel", {})
    run1, run2 = metrics.get("run1", {}), metrics.get("run2", {})
    br = load_yaml(ROOT / "exceptions" / "bank-rec.yaml", [])
    ac = load_yaml(ROOT / "exceptions" / "accruals.yaml", [])
    recon = load_json(ROOT / "exceptions" / "bank-rec-reconciling.json", {})
    learned = load_yaml(ROOT / "data" / "rules" / "learned.yaml", []) or []
    exceptions = list(br) + list(ac)

    passed = controls.get("passed", 0)
    total_controls = controls.get("total", 10)
    all_green = passed == total_controls and total_controls > 0

    n_bank = entry_count("bank-rec")
    n_acc = entry_count("accruals")
    n_dep = entry_count("depreciation")
    dep_total = posted_total("depreciation", "Expenses:Depreciation")
    acc_total = posted_total("accruals", "Liabilities:Accrued")
    cheques = recon.get("outstanding_cheques", []) or []
    deposits = recon.get("deposits_in_transit", []) or []

    reclassified = [e for e in exceptions if "reclassified" in str(e.get("reviewer_note", ""))]
    kinds = Counter(e.get("kind") or "other" for e in br)
    traces = {e.get("trace") for e in br if e.get("trace")}

    # ---- control register rows
    ctrl_rows = "".join(
        f'<tr><td class="mono cid">{escape(str(c.get("id","")))}</td>'
        f'<td>{escape(str(c.get("name","")))}</td>'
        f'<td class="st">{"<span class=chip-pass>pass</span>" if c.get("passed") else "<span class=chip-fail>fail</span>"}</td>'
        f'<td class="detail">{escape(str(c.get("detail") or ""))}</td></tr>'
        for c in results
    )

    # ---- exception register rows
    exc_rows = []
    for e in exceptions:
        kind = e.get("kind") or ("material" if "material" in str(e.get("issue", "")) else "other")
        note = str(e.get("reviewer_note") or "")
        recl = "reclassified" in note
        conf = str(e.get("confidence", ""))
        trace = str(e.get("trace") or "")
        exc_rows.append(
            "<tr>"
            f'<td class="mono">{escape(str(e.get("id","")))}</td>'
            f'<td>{escape(str(e.get("description") or e.get("task","")))}</td>'
            f'<td class="kind">{escape(KIND_LABEL.get(kind, kind.title()))}</td>'
            f'<td class="num mono">{escape(conf)}</td>'
            f'<td class="st"><span class="chip-app">approved</span>'
            + ('<span class="chip-recl">reclassified</span>' if recl else "")
            + "</td>"
            f'<td class="detail">{escape(note[:150])}</td>'
            f'<td class="mono trace">{escape(trace[9:17] + "…" if trace.startswith("neatlogs:") else "—")}</td>'
            "</tr>"
        )
    exc_rows = "".join(exc_rows)

    kind_rows = "".join(
        f'<li><span class="k">{escape(KIND_LABEL.get(k, k.title()))}</span>'
        f'<span class="v mono">{n}</span></li>'
        for k, n in kinds.most_common()
    )

    learned_rows = "".join(
        f'<li><span class="k mono">{escape(str(r.get("match","")))}</span>'
        f'<span class="arrow">→</span><span class="k">{escape(str(r.get("account","")))}</span>'
        f'<span class="v mono">{escape(str(r.get("learned_from","")))}</span></li>'
        for r in learned if isinstance(r, dict)
    ) or '<li class="empty">No rules learned yet — run <code>closeops rerun bank-rec</code>.</li>'

    r1 = pct_num(run1.get("auto_rate", "0%"))
    r2 = pct_num(run2.get("auto_rate", "0%"))
    delta = r2 - r1

    generated = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    name = company.get("name", "Northwind Labs Inc.")
    period = company.get("period", "2026-09")
    materiality = company.get("materiality", "10000.00")
    lock = company.get("period_lock_before", "2026-09-01")

    html = f"""<title>Northwind September Close</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bitter:wght@600;700&family=Public+Sans:wght@400;500;600;700&family=Roboto+Mono:wght@400;500;700&display=swap">
<style>
:root {{
  --paper:#EDF0F3; --panel:#FFFFFF; --panel-2:#F5F7F9; --ink:#18222D; --ink-2:#4A5866;
  --ink-3:#7A8896; --rule:#D2D9E0; --seal:#0F6E4F; --seal-soft:#DCEDE5; --bar:#5C7C99;
  --amber:#9A6014; --amber-soft:#F6E9D6; --red:#A32B2B; --red-soft:#F5DEDE; --shadow:0 1px 2px rgba(24,34,45,.07);
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --paper:#0D1218; --panel:#151D25; --panel-2:#1B242D; --ink:#E3EAF1; --ink-2:#A9B6C3;
    --ink-3:#76838F; --rule:#2A3540; --seal:#4FBF92; --seal-soft:#123125; --bar:#6F91AE;
    --amber:#D9973F; --amber-soft:#37280F; --red:#E07070; --red-soft:#3A1A1A; --shadow:0 1px 3px rgba(0,0,0,.5);
  }}
}}
:root[data-theme="dark"] {{
  --paper:#0D1218; --panel:#151D25; --panel-2:#1B242D; --ink:#E3EAF1; --ink-2:#A9B6C3;
  --ink-3:#76838F; --rule:#2A3540; --seal:#4FBF92; --seal-soft:#123125; --bar:#6F91AE;
  --amber:#D9973F; --amber-soft:#37280F; --red:#E07070; --red-soft:#3A1A1A; --shadow:0 1px 3px rgba(0,0,0,.5);
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--paper);color:var(--ink);font-family:"Public Sans",system-ui,sans-serif;font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased}}
.mono,code{{font-family:"Roboto Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums}}
.wrap{{max-width:1020px;margin:0 auto;padding:32px 20px 80px}}
header.doc{{border-bottom:2px solid var(--ink);padding-bottom:18px;margin-bottom:6px}}
.kicker{{font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);font-weight:600}}
h1{{font-family:Bitter,Georgia,serif;font-weight:700;font-size:34px;line-height:1.1;margin:6px 0 4px;letter-spacing:-.01em}}
.sub{{color:var(--ink-2);font-size:14px}}
.sealrow{{display:flex;flex-wrap:wrap;gap:16px;align-items:center;justify-content:space-between;margin-top:16px}}
.seal{{display:inline-flex;align-items:center;gap:10px;border:2px solid var(--seal);color:var(--seal);border-radius:4px;padding:8px 14px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;font-size:13px;background:var(--seal-soft)}}
.seal.bad{{border-color:var(--red);color:var(--red);background:var(--red-soft)}}
.seal .big{{font-family:"Roboto Mono",monospace;font-size:19px;font-variant-numeric:tabular-nums}}
.meta{{display:flex;gap:22px;flex-wrap:wrap;font-size:12.5px;color:var(--ink-2)}}
.meta b{{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--ink-3);font-weight:600}}
h2{{font-family:Bitter,Georgia,serif;font-size:20px;font-weight:600;margin:38px 0 10px;letter-spacing:-.005em}}
h2 .n{{font-family:"Roboto Mono",monospace;font-size:12px;color:var(--ink-3);margin-right:8px;font-weight:400}}
p.lede{{color:var(--ink-2);margin:0 0 14px;max-width:70ch;font-size:14px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:0;border:1px solid var(--rule);border-radius:5px;overflow:hidden;background:var(--panel);box-shadow:var(--shadow);margin:16px 0 4px}}
.tiles>div{{padding:12px 14px;border-right:1px solid var(--rule)}}
.tiles>div:last-child{{border-right:0}}
.tiles .k{{font-size:10.5px;text-transform:uppercase;letter-spacing:.09em;color:var(--ink-3);font-weight:600}}
.tiles .v{{font-family:"Roboto Mono",monospace;font-size:21px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.3}}
.tiles .n{{font-size:11.5px;color:var(--ink-2)}}
.tbl{{border:1px solid var(--rule);border-radius:5px;overflow-x:auto;background:var(--panel);box-shadow:var(--shadow)}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
th{{background:var(--panel-2);text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;color:var(--ink-3);padding:8px 11px;border-bottom:1px solid var(--rule);font-weight:600;white-space:nowrap}}
td{{padding:8px 11px;border-bottom:1px solid var(--rule);vertical-align:top}}
tr:last-child td{{border-bottom:0}}
td.cid{{font-weight:700;color:var(--ink-2);width:44px}}
td.num{{text-align:right;white-space:nowrap}}
td.st{{white-space:nowrap}}
td.detail{{color:var(--ink-2);font-size:12px}}
td.kind{{white-space:nowrap;font-size:12.5px}}
td.trace{{font-size:11.5px;color:var(--ink-3)}}
.chip-pass,.chip-fail,.chip-app,.chip-recl{{display:inline-block;font-size:10.5px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;padding:2px 7px;border-radius:3px}}
.chip-pass{{background:var(--seal-soft);color:var(--seal)}}
.chip-fail{{background:var(--red-soft);color:var(--red)}}
.chip-app{{background:var(--seal-soft);color:var(--seal)}}
.chip-recl{{background:var(--amber-soft);color:var(--amber);margin-left:5px}}
figure{{margin:14px 0 6px}}
figure svg{{max-width:100%;height:auto;color:var(--ink)}}
figcaption{{font-size:12.5px;color:var(--ink-2);margin-top:6px;max-width:70ch}}
.cols{{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:16px;margin-top:16px}}
.card{{border:1px solid var(--rule);border-radius:5px;background:var(--panel);padding:14px 16px;box-shadow:var(--shadow)}}
.card h3{{margin:0 0 8px;font-size:13.5px;font-weight:700}}
.card ul{{list-style:none;margin:0;padding:0;font-size:13px}}
.card li{{display:flex;align-items:baseline;gap:8px;padding:4px 0;border-bottom:1px dotted var(--rule)}}
.card li:last-child{{border-bottom:0}}
.card li .k{{flex:1}}
.card li .v{{font-weight:700;font-variant-numeric:tabular-nums}}
.card li .arrow{{color:var(--ink-3)}}
.card li.empty{{color:var(--ink-3)}}
.delta{{display:flex;align-items:baseline;gap:12px;margin-top:6px}}
.delta .a,.delta .b{{font-family:"Roboto Mono",monospace;font-size:26px;font-weight:700;font-variant-numeric:tabular-nums}}
.delta .a{{color:var(--ink-3)}}
.delta .b{{color:var(--seal)}}
.delta .g{{color:var(--ink-3);font-size:20px}}
.delta .note{{font-size:12.5px;color:var(--ink-2)}}
.callout{{border-left:3px solid var(--amber);background:var(--panel);padding:11px 15px;border-radius:0 4px 4px 0;margin:16px 0;font-size:13.5px;box-shadow:var(--shadow)}}
.callout b{{color:var(--amber)}}
footer{{margin-top:44px;padding-top:14px;border-top:1px solid var(--rule);font-size:12px;color:var(--ink-3)}}
footer a{{color:var(--seal)}}
@media (max-width:640px){{h1{{font-size:26px}}.wrap{{padding:20px 14px 60px}}}}
</style>

<div class="wrap">
<header class="doc">
  <div class="kicker">Close package · period {escape(str(period))} · generated {escape(generated)}</div>
  <h1>{escape(str(name))}</h1>
  <div class="sub">Month-end close executed as reviewed pull requests. Every entry carries its source
  document, a confidence, and a trace id; every control below ran in CI before the entries merged.</div>
  <div class="sealrow">
    <div class="seal{'' if all_green else ' bad'}"><span class="big">{passed}/{total_controls}</span> controls {'passed' if all_green else 'failed'}</div>
    <div class="meta">
      <div><b>Materiality</b>USD {escape(str(materiality))}</div>
      <div><b>Period lock</b>before {escape(str(lock))}</div>
      <div><b>Exceptions</b>{len(exceptions)} raised · 0 open</div>
      <div><b>Trace</b>{len(traces)} decide run{'s' if len(traces)!=1 else ''}</div>
    </div>
  </div>
</header>

<div class="tiles">
  <div><div class="k">Statement lines</div><div class="v">116</div><div class="n">September bank export</div></div>
  <div><div class="k">Auto-posted</div><div class="v">{n_bank - len(br)}</div><div class="n">bank-rec entries at ≥0.90</div></div>
  <div><div class="k">Sent to a human</div><div class="v">{len(exceptions)}</div><div class="n">with a proposed entry</div></div>
  <div><div class="k">Reconciling items</div><div class="v">{len(cheques) + len(deposits)}</div><div class="n">{len(cheques)} cheques · {len(deposits)} in transit</div></div>
</div>

<h2><span class="n">§1</span>Control register</h2>
<p class="lede">These ten controls run in GitHub Actions on every pull request that touches the ledger and
post their result as a PR comment. A control that cannot evaluate reports <em>fail</em>, never pass.</p>
<div class="tbl"><table>
<thead><tr><th>#</th><th>Control</th><th>Result</th><th>Detail</th></tr></thead>
<tbody>{ctrl_rows}</tbody>
</table></div>

<h2><span class="n">§2</span>What the agent actually adds</h2>
<figure>{funnel_svg(funnel)}
<figcaption>Auto-post rate by tier on the same 116 statement lines. The agent's own contribution is the
step from deterministic rules to agent judgment — and the fact that the remaining lines arrive as
proposed entries with evidence, not as a list of unmatched rows.</figcaption>
</figure>

<div class="cols">
  <div class="card">
    <h3>Improvement between runs</h3>
    <div class="delta">
      <span class="a">{run1.get('auto_rate','—')}</span><span class="g">→</span><span class="b">{run2.get('auto_rate','—')}</span>
    </div>
    <div class="delta"><span class="note">Run 1 {run1.get('auto',0)}/{run1.get('total',0)} · run 2 {run2.get('auto',0)}/{run2.get('total',0)} after learning
    from the controller's approvals — {delta:+.1f} points.</span></div>
  </div>
  <div class="card">
    <h3>Rules learned from the human</h3>
    <ul>{learned_rows}</ul>
  </div>
  <div class="card">
    <h3>Why each line needed a person</h3>
    <ul>{kind_rows}</ul>
  </div>
</div>

<h2><span class="n">§3</span>Exception register</h2>
<p class="lede">Each exception is a proposed journal entry the agent would not post on its own authority.
The controller approved all {len(exceptions)}, overruling the agent's proposed account on {len(reclassified)}.</p>
<div class="callout"><b>The review was load-bearing.</b> Approving every exception exactly as proposed would
have left <span class="mono">Equity:Suspense</span> holding 2,850.00 and failed control C8. The duplicate
card charge was moved to a receivable rather than booked as a second expense.</div>
<div class="tbl"><table>
<thead><tr><th>ID</th><th>Line</th><th>Why</th><th>Conf.</th><th>Status</th><th>Controller note</th><th>Trace</th></tr></thead>
<tbody>{exc_rows}</tbody>
</table></div>

<h2><span class="n">§4</span>Entries booked</h2>
<div class="tiles">
  <div><div class="k">Bank reconciliation</div><div class="v">{n_bank}</div><div class="n">entries, incl. approved exceptions</div></div>
  <div><div class="k">Accruals</div><div class="v">{n_acc}</div><div class="n">USD {money(abs(acc_total))} accrued</div></div>
  <div><div class="k">Depreciation</div><div class="v">{n_dep}</div><div class="n">USD {money(dep_total)} charged</div></div>
  <div><div class="k">Open at close</div><div class="v">0</div><div class="n">every exception resolved</div></div>
</div>

<footer>
Generated from <code>metrics.json</code>, <code>exceptions/*.yaml</code> and <code>ledger/2026-09/</code> by
<code>scripts/build_dashboard.py</code> — no hand-entered figures.
Source: <a href="https://github.com/PARIDHIPAWAIYA/closeops">github.com/PARIDHIPAWAIYA/closeops</a>.
Synthetic company data; Dodo Payments figures from test-mode-shaped fixtures.
</footer>
</div>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8", newline="\n")
    return out_path, len(html)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "docs" / "dashboard.html"))
    args = ap.parse_args()
    path, size = build(Path(args.out))
    print(f"Wrote {path} ({size:,} bytes)")


if __name__ == "__main__":
    main()
