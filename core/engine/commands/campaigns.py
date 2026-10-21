"""growth_engine.commands.campaigns — campaign visibility from captured reports.

Three verbs, all read-only over the latest ad-intel report (if one exists):
  list    — every campaign with status and key metrics
  status  — flagged: live vs paused vs zero-spend
  compare — side-by-side performance table

If no report exists yet the output says so explicitly rather than inventing
numbers — same rule as diagnose and audit.
"""

from __future__ import annotations

import csv
from pathlib import Path
import sys
from typing import Any

from tenant import TenantContext
from utils import append_log, sanitize_text
from commands.state import collect_snapshot, _to_number


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


def _cmd_import(tenant: TenantContext, opts: dict, now) -> int:
    file_raw = opts.get("file")
    if not file_raw:
        print("ERROR: --file <path.csv> is required for `campaigns import`.", file=sys.stderr)
        return 2
    csv_path = Path(file_raw)
    if not csv_path.exists() or not csv_path.is_file():
        print(f"ERROR: CSV file not found: {csv_path}", file=sys.stderr)
        return 2

    rows: list[dict[str, Any]] = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            norm = {str(k).strip().lower(): str(v).strip() for k, v in raw.items() if k}
            name = sanitize_text(
                norm.get("campaign") or norm.get("campaign name") or norm.get("name") or ""
            )
            if not name or name.lower() in ("total", "account total"):
                continue
            status = sanitize_text(
                norm.get("status") or norm.get("campaign status") or norm.get("delivery") or "ENABLED"
            ).upper()
            budget = _to_number(norm.get("budget") or norm.get("daily budget") or "0") or 0.0
            cost = _to_number(
                norm.get("spend") or norm.get("cost") or norm.get("amount spent") or "0"
            ) or 0.0
            impr = int(_to_number(norm.get("impressions") or norm.get("impr.") or "0") or 0)
            clicks = int(_to_number(norm.get("clicks") or "0") or 0)
            conv = _to_number(
                norm.get("conversions") or norm.get("results") or norm.get("purchases") or "0"
            ) or 0.0
            ctr = (clicks / impr * 100.0) if impr > 0 else 0.0
            cpa = (cost / conv) if conv > 0 else None
            rows.append({
                "name": name,
                "status": status,
                "budget": budget,
                "today_cost": 0.0,
                "impressions": impr,
                "clicks": clicks,
                "ctr": ctr,
                "cost": cost,
                "conversions": conv,
                "cpa": cpa,
            })

    if not rows:
        print(f"ERROR: no valid campaign rows found in {csv_path}.", file=sys.stderr)
        return 2

    lines = [
        f"# {tenant.name} — Imported Ad Report — {now.strftime('%Y-%m-%d %H:%M')}",
        "",
        f"Scope: imported from `{csv_path.name}` ({len(rows)} campaign(s)). Read-only.",
        "",
        "## Alerts",
        "None.",
        "",
        "## Campaign Summary (last 7 days)",
        "| Campaign | Status | Daily Budget | Today's Spend | Impr. | Clicks | "
        "CTR | Cost | Conversions | CPA |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        cpa_str = f"{r['cpa']:.2f}" if r["cpa"] is not None else "—"
        lines.append(
            f"| {r['name']} | {r['status']} | {r['budget']:.2f} | "
            f"{r['today_cost']:.2f} | {r['impressions']:,} | "
            f"{r['clicks']:,} | {r['ctr']:.2f}% | {r['cost']:.2f} | "
            f"{r['conversions']:.1f} | {cpa_str} |"
        )
    report = "\n".join(lines)
    report_path = tenant.reports_dir / f"{now.strftime('%Y-%m-%d-%H')}-ad-intel-report.md"
    report_path.write_text(report, encoding="utf-8")
    opts.setdefault("_extra", {})["_data"] = {
        "campaigns_imported": len(rows),
        "total_spend": sum(r["cost"] for r in rows),
        "total_conversions": sum(r["conversions"] for r in rows),
    }
    print(report)
    print(f"\n[{tenant.name}] campaigns import: report written -> {report_path}")
    append_log(tenant.name, "campaigns-import",
               f"Imported {len(rows)} campaign(s) from CSV into ad-intel report format",
               report_path)
    return 0


def run(tenant: TenantContext, opts: dict | None = None) -> int:
    opts = opts or {}
    verb = opts.get("verb", "list")
    snap = collect_snapshot(tenant)
    ad = snap["ad_report"]
    now = snap["now"]

    if verb == "import":
        return _cmd_import(tenant, opts, now)

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