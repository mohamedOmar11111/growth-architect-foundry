"""growth_engine.commands.forecast — budget and performance projections.

One verb:
  project — forward-looking budget projections based on current data

All projections are estimates with stated assumptions (core rule 9). This
command reads the latest ad-intel report and extrapolates trends — never
guarantees, always labeled.
"""

from __future__ import annotations

from tenant import TenantContext
from utils import append_log
from commands.state import collect_snapshot


def run(tenant: TenantContext, opts: dict | None = None) -> int:
    snap = collect_snapshot(tenant)
    now = snap["now"]
    ad = snap["ad_report"]

    if ad is None:
        output = (
            f"# {tenant.name} — Forecast — {now.strftime('%Y-%m-%d %H:%M')}\n\n"
            "No ad-intel report captured yet — projections require real spend data.\n\n"
            "**Next step:** run `foundry campaigns list --client " + tenant.name + "` "
            "once ad-intel has pulled live data."
        )
        print(output)
        return 0

    totals = ad["totals"]
    rows = ad["rows"]
    total_spend = totals["cost"]
    total_conv = totals["conversions"]
    cpa = totals["cpa"]

    # Weekly extrapolation from 7-day captured data
    weekly_spend = total_spend
    weekly_conv = total_conv
    monthly_spend = weekly_spend * 4.33  # ~30/7
    monthly_conv = weekly_conv * 4.33

    target_cpa = snap["config"]["target_cpa"]

    lines = [
        f"# {tenant.name} — Forecast — {now.strftime('%Y-%m-%d %H:%M')}",
        "",
        "**These are extrapolations from the last 7 days of captured data, "
        "not guarantees.** Actual results will differ — seasonality, creative "
        "fatigue, budget changes, and market shifts all move numbers. Use these "
        "as a baseline to reason from, not a target to hit.",
        "",
        "## Current Trajectory (from captured report)",
        f"- **Weekly spend:** {weekly_spend:,.2f}",
        f"- **Weekly conversions:** {weekly_conv:,.0f}",
        f"- **Observed CPA:** {cpa:.2f}" if cpa else "- **Observed CPA:** n/a (no conversions)",
        f"- **Campaigns active:** {len(rows)}",
        "",
        "## Monthly Projection (if current pace holds)",
        f"- **Monthly spend:** ~{monthly_spend:,.2f}",
        f"- **Monthly conversions:** ~{monthly_conv:,.0f}",
        f"- **Monthly CPA:** ~{cpa:.2f}" if cpa else "- **Monthly CPA:** n/a",
    ]

    if target_cpa:
        target_cpa_f = float(target_cpa)
        lines += [
            "",
            "## vs Target CPA",
            f"- **Target CPA:** {target_cpa_f:.2f}",
            f"- **Observed CPA:** {cpa:.2f}" if cpa else "- **Observed CPA:** n/a",
        ]
        if cpa:
            ratio = cpa / target_cpa_f
            if ratio <= 1.0:
                lines.append(f"- **Status:** ✅ CPA is at target ({ratio:.2f}x) — room to scale.")
            elif ratio <= 1.2:
                lines.append(f"- **Status:** ⚠️ CPA is {ratio:.2f}x target — within tolerance but watch it.")
            else:
                lines.append(f"- **Status:** 🔴 CPA is {ratio:.2f}x target — cut waste before scaling.")

    lines += [
        "",
        "## Honest Limits",
        "- Projections assume no budget changes, no creative fatigue, no seasonality.",
        "- 7 days is a short window — confidence grows with 30+ days of data.",
        "- Every number here is an estimate. Verify with `calc.py` before committing budget.",
    ]

    report_path = tenant.reports_dir / f"{now.strftime('%Y-%m-%d-%H')}-forecast.md"
    full = "\n".join(lines)
    report_path.write_text(full, encoding="utf-8")
    print(full)
    print(f"\n[{tenant.name}] forecast: report written -> {report_path}")
    append_log(tenant.name, "forecast", "Budget forecast from captured data", report_path)
    return 0