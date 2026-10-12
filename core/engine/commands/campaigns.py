"""growth_engine.commands.campaigns — campaign visibility from captured reports.

Three verbs, all read-only over the latest ad-intel report (if one exists):
  list    — every campaign with status and key metrics
  status  — flagged: live vs paused vs zero-spend
  compare — side-by-side performance table

If no report exists yet the output says so explicitly rather than inventing
numbers — same rule as diagnose and audit.
"""

from __future__ import annotations

import sys

from typing import Any

from tenant import TenantContext
from utils import append_log
from commands.state import collect_snapshot


def _format_list(rows: list[dict[str, Any]]) -> str:
    lines = [
        "## Campaign List",
        "| Campaign | Status | Budget | Spend | Impr. | Clicks | CTR | Conversions | CPA |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        cpa = f"{r['cpa']:.2f}" if r["cpa"] is not None else "—"
        budget = f"{r['daily_budget']:.2f}" if r["daily_budget"] is not None else "—"
        lines.append(
            f"| {r['name']} | {r['status']} | {budget} | "
            f"{r['cost']:.2f} | {r['impressions']:,.0f} | {r['clicks']:,.0f} | "
            f"{r['ctr']:.2f}% | {r['conversions']:.0f} | {cpa} |"
        )
    return "\n".join(lines)


def _format_status(rows: list[dict[str, Any]]) -> str:
    buckets: dict[str, list[str]] = {"live": [], "paused": [], "zero-spend": [], "low-spend": []}
    for r in rows:
        name = r["name"]
        if r["status"] == "PAUSED":
            buckets["paused"].append(name)
        elif r["cost"] == 0:
            buckets["zero-spend"].append(name)
        elif r["daily_budget"] and r["today_spend"] and r["today_spend"] / r["daily_budget"] > 0.7:
            buckets["live"].append(name)
        else:
            buckets["low-spend"].append(name)
    lines = ["## Campaign Status"]
    for label, items in buckets.items():
        if items:
            lines.append(f"\n**{label.upper()}** ({len(items)})")
            lines.extend(f"- {n}" for n in items)
    if not any(buckets.values()):
        lines.append("No campaigns in any captured report.")
    return "\n".join(lines)


def _format_compare(rows: list[dict[str, Any]]) -> str:
    if len(rows) < 2:
        return "## Compare\nNeed at least 2 campaigns to compare — only " + \
               (f"{len(rows)} found." if rows else "none found.")
    best_ctr = max(rows, key=lambda r: r["ctr"] or 0)
    best_cpa = min((r for r in rows if r["cpa"] is not None), key=lambda r: r["cpa"], default=None)
    lines = [
        "## Side-by-Side Comparison",
        "| Campaign | CTR | CPA | Conv. | Cost | Verdict |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        cpa = f"{r['cpa']:.2f}" if r["cpa"] is not None else "—"
        verdict = ""
        if r == best_ctr:
            verdict += "best CTR "
        if r == best_cpa:
            verdict += "best CPA"
        lines.append(f"| {r['name']} | {r['ctr']:.2f}% | {cpa} | {r['conversions']:.0f} | {r['cost']:.2f} | {verdict.strip() or '—'} |")
    return "\n".join(lines)


def run(tenant: TenantContext, opts: dict | None = None) -> int:
    opts = opts or {}
    verb = opts.get("verb", "list")
    snap = collect_snapshot(tenant)
    ad = snap["ad_report"]
    now = snap["now"]

    if ad is None:
        print(f"[{tenant.name}] campaigns {verb}: no ad-intel report captured yet. "
              "Run `foundry audit` to check config, then `foundry campaigns list` "
              "once ad-intel has pulled live data.")
        return 0

    rows = ad["rows"]
    if verb == "list":
        report = _format_list(rows)
    elif verb == "status":
        report = _format_status(rows)
    elif verb == "compare":
        report = _format_compare(rows)
    else:
        print(f"ERROR: unknown campaigns verb '{verb}'", file=sys.stderr)
        return 1

    header = f"# {tenant.name} — Campaigns: {verb} — {now.strftime('%Y-%m-%d %H:%M')}"
    full = header + "\n\n" + report

    report_path = tenant.reports_dir / f"{now.strftime('%Y-%m-%d-%H')}-campaigns-{verb}.md"
    report_path.write_text(full, encoding="utf-8")

    print(full)
    print(f"\n[{tenant.name}] campaigns {verb}: report written -> {report_path}")
    append_log(tenant.name, f"campaigns-{verb}", f"Campaigns {verb} from captured report", report_path)
    return 0