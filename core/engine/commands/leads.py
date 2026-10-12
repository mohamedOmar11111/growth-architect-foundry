"""growth_engine.commands.leads — lead scoring visibility.

One verb:
  score — breakdown of lead tasks by Budget/Intent/Authority score

Reads lead-qualify tasks from the tasks/ folder. If no lead tasks exist
yet, says so explicitly.
"""

from __future__ import annotations

from tenant import TenantContext
from utils import append_log
from commands.state import collect_snapshot


def run(tenant: TenantContext, opts: dict | None = None) -> int:
    snap = collect_snapshot(tenant)
    now = snap["now"]
    lead_tasks = [t for t in snap["tasks"] if t.get("domain") == "lead-qualify"]

    if not lead_tasks:
        output = (
            f"# {tenant.name} — Leads — {now.strftime('%Y-%m-%d %H:%M')}\n\n"
            "No lead-qualify tasks yet. Run the `lead-qualify` loop against a "
            "root bus with incoming leads, or import leads into the signals/ folder."
        )
        print(output)
        return 0

    lines = [
        f"# {tenant.name} — Leads: Score — {now.strftime('%Y-%m-%d %H:%M')}",
        "",
        f"**Total lead tasks:** {len(lead_tasks)}",
        f"**Open:** {len([t for t in lead_tasks if t.get('status') == 'open'])}",
        f"**Done:** {len([t for t in lead_tasks if t.get('status') == 'done'])}",
        "",
        "## Lead Tasks",
        "| Date | Status | Priority | Summary |",
        "|---|---|---|---|",
    ]
    for t in lead_tasks[:20]:
        body_lines = str(t.get("_body") or "").splitlines()
        summary = body_lines[0][:80] if body_lines else t["_path"].name
        lines.append(
            f"| {t.get('date', '—')} | {t.get('status', '—')} | "
            f"{t.get('priority', '—')} | {summary} |"
        )

    if len(lead_tasks) > 20:
        lines.append(f"\n... and {len(lead_tasks) - 20} more")

    report_path = tenant.reports_dir / f"{now.strftime('%Y-%m-%d-%H')}-leads-score.md"
    full = "\n".join(lines)
    report_path.write_text(full, encoding="utf-8")
    print(full)
    print(f"\n[{tenant.name}] leads score: report written -> {report_path}")
    append_log(tenant.name, "leads-score", f"Leads score: {len(lead_tasks)} task(s)", report_path)
    return 0