"""growth_engine.commands.content — content pipeline visibility.

Two verbs:
  pipeline — overview of briefs, tasks, calendar, and signal→content flow
  calendar — upcoming publish schedule (or lack thereof)

Reads the same files the content-engine and social-calendar loops write to,
so the operator always sees the real pipeline state.
"""

from __future__ import annotations

import sys

from tenant import TenantContext
from utils import append_log
from commands.state import collect_snapshot


def _format_pipeline(snap: dict, tenant: TenantContext) -> str:
    content = snap["content"]
    signals_in = len([s for s in snap["signals"] if s.get("type") == "content-idea"])
    unprocessed_in = len([s for s in snap["unprocessed"] if s.get("type") == "content-idea"])
    tasks = [t for t in snap["tasks"] if t.get("domain") == "content-engine"]

    lines = [
        "## Content Pipeline",
        f"| Stage | Count |",
        f"|---|---|",
        f"| Content-idea signals (total) | {signals_in} |",
        f"| Unprocessed content-idea signals | {unprocessed_in} |",
        f"| Content-engine tasks | {len(tasks)} |",
        f"| Draft briefs | {content['briefs']} |",
        f"| Calendar exists | {'yes' if content['calendar'] else 'no'} |",
    ]

    if content["briefs"] and not content["calendar"]:
        lines += ["", "**Gap:** briefs exist but no calendar — run "
                    "`foundry content calendar` or the social-calendar loop."]
    if unprocessed_in > 0 and content["briefs"] == 0:
        lines += ["", "**Gap:** content-idea signals waiting but no briefs drafted yet "
                    "— run `content-engine` loop."]
    if not any([signals_in, content["briefs"], content["calendar"]]):
        lines += ["", "Pipeline is empty — run ad-intel against a live account first."]

    return "\n".join(lines)


def _format_calendar(snap: dict, tenant: TenantContext) -> str:
    cal_path = tenant.root / "02_Content" / "calendar" / "content_calendar.md"
    if not cal_path.exists():
        return ("## Content Calendar\nNo calendar exists yet. Run the "
                "`social-calendar` loop after content-engine has drafted briefs.")
    text = cal_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    return "## Content Calendar\n" + "\n".join(lines[:50]) + (
        f"\n\n... ({len(lines)} total lines)" if len(lines) > 50 else ""
    )


def run(tenant: TenantContext, opts: dict | None = None) -> int:
    opts = opts or {}
    verb = opts.get("verb", "pipeline")
    snap = collect_snapshot(tenant)
    now = snap["now"]

    if verb == "pipeline":
        body = _format_pipeline(snap, tenant)
    elif verb == "calendar":
        body = _format_calendar(snap, tenant)
    else:
        print(f"ERROR: unknown content verb '{verb}'", file=sys.stderr)
        return 1

    header = f"# {tenant.name} — Content: {verb} — {now.strftime('%Y-%m-%d %H:%M')}"
    full = header + "\n\n" + body

    report_path = tenant.reports_dir / f"{now.strftime('%Y-%m-%d-%H')}-content-{verb}.md"
    report_path.write_text(full, encoding="utf-8")
    print(full)
    print(f"\n[{tenant.name}] content {verb}: report written -> {report_path}")
    append_log(tenant.name, f"content-{verb}", f"Content {verb} from kernel state", report_path)
    return 0