"""growth_engine.commands.ops — engine operations health.

Two verbs:
  status  — overall kernel health: tenant count, run count, loops seen, last run
  cadence — loop schedule compliance: which loops are overdue

This is the "is my engine actually running?" check. If ops status shows
zero runs, nothing else in the system can produce useful output.
"""

from __future__ import annotations

from pathlib import Path

from tenant import TenantContext, CLIENTS_ROOT
from utils import append_log, LOG_PATH
from commands.state import collect_snapshot, read_log_entries


def _all_tenants() -> list[str]:
    return sorted(p.name for p in CLIENTS_ROOT.iterdir() if p.is_dir() and (p / ".env").exists())


def _format_status(snap: dict) -> str:
    tenant = snap["tenant"]
    entries = snap["log_entries"]
    loops_seen = {e["loop"] for e in entries}
    last_entry = max((e["when"] for e in entries), default=None)

    lines = [
        "## Engine Status",
        f"- **Tenant:** {tenant.name}",
        f"- **Tenant folder:** {tenant.root}",
        f"- **Total runs logged:** {len(entries)}",
        f"- **Distinct loops seen:** {', '.join(sorted(loops_seen)) if loops_seen else 'none'}",
        f"- **Last run:** {last_entry.strftime('%Y-%m-%d %H:%M') if last_entry else 'never'}",
        f"- **Config ready:** {'yes' if all(g['ready'] for g in snap['config']['groups'].values()) else 'no'}",
    ]

    all_tenants = _all_tenants()
    lines += [f"- **All tenants ({len(all_tenants)}):** {', '.join(all_tenants) if all_tenants else 'none configured'}"]

    if not entries:
        lines += ["", "**This kernel has never fired.** Run a loop: "
                    "`foundry campaigns list --client " + tenant.name + "`"]
    return "\n".join(lines)


LOOP_CADENCE = {
    "ad-intel": 6,          # every 6 hours
    "meta-ads": 6,
    "content-engine": 72,   # every 3 days
    "social-calendar": 72,
    "creative-brief": 72,
    "lead-qualify": 24,     # every 24h
}


def _format_cadence(snap: dict) -> str:
    entries = snap["log_entries"]
    now = snap["now"]
    last_by_loop: dict[str, int] = {}
    for e in entries:
        age_hours = (now - e["when"]).total_seconds() / 3600
        current = last_by_loop.get(e["loop"])
        if current is None or age_hours < current:
            last_by_loop[e["loop"]] = age_hours

    lines = [
        "## Loop Cadence Compliance",
        "| Loop | Expected cadence | Last run (hours ago) | Status |",
        "|---|---|---|---|",
    ]
    for loop, expected_hours in sorted(LOOP_CADENCE.items()):
        last = last_by_loop.get(loop)
        if last is None:
            status = "NEVER RUN"
            last_str = "—"
        elif last > expected_hours * 1.5:
            status = "OVERDUE"
            last_str = f"{last:.0f}"
        else:
            status = "OK"
            last_str = f"{last:.0f}"
        lines.append(f"| {loop} | every {expected_hours}h | {last_str} | {status} |")

    overdue = [loop for loop, hours in LOOP_CADENCE.items()
               if last_by_loop.get(loop) is not None and last_by_loop[loop] > hours * 1.5]
    never = [loop for loop in LOOP_CADENCE if loop not in last_by_loop]

    if overdue:
        lines += ["", f"**Overdue:** {', '.join(overdue)} — schedule these loops."]
    if never:
        lines += ["", f"**Never run:** {', '.join(never)} — run them at least once to establish baseline."]
    if not overdue and not never and last_by_loop:
        lines += ["", "**All loops on schedule.** Nothing to fix."]
    if not last_by_loop:
        lines += ["", "**No loops have run yet.** Schedule run_loop.py or foundry and the log fills itself."]
    return "\n".join(lines)


def run(tenant: TenantContext, opts: dict | None = None) -> int:
    opts = opts or {}
    verb = opts.get("verb", "status")
    snap = collect_snapshot(tenant)
    now = snap["now"]

    if verb == "status":
        body = _format_status(snap)
    elif verb == "cadence":
        body = _format_cadence(snap)
    else:
        print(f"ERROR: unknown ops verb '{verb}'", file=sys.stderr)
        return 1

    header = f"# {tenant.name} — Ops: {verb} — {now.strftime('%Y-%m-%d %H:%M')}"
    full = header + "\n\n" + body

    report_path = tenant.reports_dir / f"{now.strftime('%Y-%m-%d-%H')}-ops-{verb}.md"
    report_path.write_text(full, encoding="utf-8")
    print(full)
    print(f"\n[{tenant.name}] ops {verb}: report written -> {report_path}")
    append_log(tenant.name, f"ops-{verb}", f"Ops {verb} from kernel state", report_path)
    return 0