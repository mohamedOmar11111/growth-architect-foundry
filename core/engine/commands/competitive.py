"""growth_engine.commands.competitive — competitive positioning.

One verb:
  audit — competitive positioning based on strategy directives

Reads STRATEGY.md's AVOID/PREFER directives and any competitor-intel signals.
No live API calls — this is a positioning exercise grounded in the tenant's
own strategy, not an Ad Library scrape.
"""

from __future__ import annotations

from tenant import TenantContext
from utils import append_log
from commands.state import collect_snapshot


def _extract_avoid_prefer(strategy_md: str) -> tuple[list[str], list[str]]:
    avoid, prefer = [], []
    in_active = False
    for line in strategy_md.splitlines():
        if "Active Directives" in line or "## " in line:
            in_active = "Active Directives" in line
        if in_active:
            stripped = line.strip()
            if stripped.startswith("- AVOID:"):
                avoid.append(stripped[len("- AVOID:"):].strip())
            elif stripped.startswith("- PREFER:"):
                prefer.append(stripped[len("- PREFER:"):].strip())
    return avoid, prefer


def run(tenant: TenantContext, opts: dict | None = None) -> int:
    snap = collect_snapshot(tenant)
    now = snap["now"]
    avoid, prefer = _extract_avoid_prefer(tenant.strategy_md)
    competitor_signals = [s for s in snap["signals"] if s.get("type") == "competitor-intel"]

    lines = [
        f"# {tenant.name} — Competitive Audit — {now.strftime('%Y-%m-%d %H:%M')}",
        "",
        "This audit is grounded in this tenant's own STRATEGY.md directives "
        "and any competitor-intel signals captured by the kernel. It is not "
        "an Ad Library scrape — for that, use the `competitors` command in "
        "the mena-ads skill.",
        "",
        "## What This Tenant Avoids (competitive whitespace)",
    ]
    if avoid:
        for item in avoid:
            lines.append(f"- {item}")
    else:
        lines.append("- No AVOID directives found in STRATEGY.md")

    lines += ["", "## What This Tenant Prefers (competitive positioning)"]
    if prefer:
        for item in prefer:
            lines.append(f"- {item}")
    else:
        lines.append("- No PREFER directives found in STRATEGY.md")

    lines += ["", "## Competitor Intel Signals"]
    if competitor_signals:
        for sig in competitor_signals:
            lines.append(f"- `{sig['_path'].name}`: {str(sig.get('_body', '')).splitlines()[0][:100]}")
    else:
        lines.append("- No competitor-intel signals captured yet. Run ad-intel or "
                    "meta-ads and feed competitor data into signals/.")

    lines += ["", "## Next Step",
              "Combine the AVOID/PREFER directives with real ad data from "
              "ad-intel to identify gaps: what competitors are doing that "
              "this tenant deliberately avoids (opportunity or weakness?), "
              "and what this tenant prefers that competitors aren't doing (moat or niche?)."]

    report_path = tenant.reports_dir / f"{now.strftime('%Y-%m-%d-%H')}-competitive-audit.md"
    full = "\n".join(lines)
    report_path.write_text(full, encoding="utf-8")
    print(full)
    print(f"\n[{tenant.name}] competitive audit: report written -> {report_path}")
    append_log(tenant.name, "competitive-audit", "Competitive audit from strategy directives", report_path)
    return 0