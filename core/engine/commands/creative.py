"""growth_engine.commands.creative — creative angle and hook ideas from kernel state.

Two verbs:
  hooks  — concrete hook ideas drawn from winning signals
  angles — angle matrix: what's working × where to expand

Reads content-idea signals (which ad-intel writes when a campaign is above
threshold) and the STRATEGY.md voice rules to produce angles grounded in
real performance data, not theory.
"""

from __future__ import annotations

import sys

from tenant import TenantContext
from utils import append_log
from commands.state import collect_snapshot


def _format_hooks(snap: dict, tenant: TenantContext) -> str:
    content_signals = [s for s in snap["signals"] if s.get("type") == "content-idea"]
    if not content_signals:
        return ("## Hooks & Angles\nNo winning signals yet. Run ad-intel against a "
                "live account — hooks are drawn from campaigns that are already "
                "converting, not from theory.")

    lines = [
        "## Hooks from Winning Signals",
        "",
        "Each hook below is drawn from a real campaign that passed the "
        "content-opportunity threshold (CTR > 5% on 20+ clicks). "
        "Expand each into a blog angle, social carousel, or landing-page section.",
        "",
    ]
    for i, sig in enumerate(content_signals, 1):
        summary = ""
        for line in str(sig.get("_body", "")).splitlines():
            if line.startswith("## Summary"):
                continue
            if "## " in line and summary:
                break
            if line.strip():
                summary = line.strip()
                break

        lines += [
            f"### Hook {i}",
            f"**Source signal:** `{sig['_path'].name}`",
            f"**Angle:** {summary}",
            "",
            "**Expand as:**",
            "- Blog post: ingredient education angle targeting the same search intent",
            "- Social carousel: 'X vs Y' comparison format",
            "- Landing section: clinical/ingredient-specific value prop",
            "",
        ]

    strategy_voice = tenant.strategy_md.split("## Voice")[1].split("##")[0].strip() if "## Voice" in tenant.strategy_md else ""
    if strategy_voice:
        lines += ["## Voice Reminder", strategy_voice, ""]
    return "\n".join(lines)


def _format_angles(snap: dict, tenant: TenantContext) -> str:
    content_signals = [s for s in snap["signals"] if s.get("type") == "content-idea"]
    lines = [
        "## Angle Matrix",
        "| # | Campaign | CTR | Clicks | Angle | Content format |",
        "|---|---|---|---|---|---|",
    ]
    if content_signals:
        for i, sig in enumerate(content_signals, 1):
            summary = ""
            for line in str(sig.get("_body", "")).splitlines():
                if line.strip() and "## Summary" not in line:
                    summary = line.strip()[:80]
                    break
            lines.append(f"| {i} | {sig['_path'].name[:40]} | — | — | {summary} | blog / social / landing |")
    else:
        lines.append("| — | No winning signals | — | — | — | — |")

    lines += [
        "",
        "**Next step:** pick one angle, create a content brief, and test it. "
        "A list of 10 angles is a way to learn nothing — one angle, one test.",
    ]
    return "\n".join(lines)


def run(tenant: TenantContext, opts: dict | None = None) -> int:
    opts = opts or {}
    verb = opts.get("verb", "hooks")
    snap = collect_snapshot(tenant)
    now = snap["now"]

    if verb == "hooks":
        body = _format_hooks(snap, tenant)
    elif verb == "angles":
        body = _format_angles(snap, tenant)
    else:
        print(f"ERROR: unknown creative verb '{verb}'", file=sys.stderr)
        return 1

    header = f"# {tenant.name} — Creative: {verb} — {now.strftime('%Y-%m-%d %H:%M')}"
    full = header + "\n\n" + body

    report_path = tenant.reports_dir / f"{now.strftime('%Y-%m-%d-%H')}-creative-{verb}.md"
    report_path.write_text(full, encoding="utf-8")
    print(full)
    print(f"\n[{tenant.name}] creative {verb}: report written -> {report_path}")
    append_log(tenant.name, f"creative-{verb}", f"Creative {verb} from kernel state", report_path)
    return 0