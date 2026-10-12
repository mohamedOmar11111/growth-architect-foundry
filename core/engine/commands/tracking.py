"""growth_engine.commands.tracking — tracking and config readiness.

Two verbs:
  check  — credential readiness per integration, with placeholder detection
  events — optimization event audit (which platforms have real event data)

No live API calls — reads .env only. A placeholder .env.example reports as
unconfigured on purpose, so the first honest check is always a wake-up call.
"""

from __future__ import annotations

from tenant import TenantContext
from utils import append_log
from commands.state import collect_snapshot, config_status


def _format_check(snap: dict) -> str:
    cfg = snap["config"]
    lines = [
        "## Tracking Readiness",
        "| Integration | Keys configured | Status |",
        "|---|---|---|",
    ]
    for name, g in cfg["groups"].items():
        status = "READY" if g["ready"] else f"INCOMPLETE ({g['configured']}/{g['required']})"
        lines.append(f"| {name} | {g['configured']}/{g['required']} | {status} |")

    lines += [
        "",
        f"Operator name: {'set' if cfg['operator_set'] else 'not set (will default to \"the operator\")'}",
        f"Target CPA: {'set' if cfg['target_cpa'] else 'not set (advice without a target is content, not media buying)'}",
    ]

    ready_count = sum(1 for g in cfg["groups"].values() if g["ready"])
    total = len(cfg["groups"])
    if ready_count == total:
        lines += ["", "**All integrations configured.** Run ad-intel/meta-ads against live data."]
    elif ready_count == 0:
        lines += ["", "**No integrations configured.** Copy .env.example to .env and fill "
                    "real credentials. Until then, every loop that touches a live account "
                    "will fail loud — by design, not a bug."]
    else:
        incomplete = [n for n, g in cfg["groups"].items() if not g["ready"]]
        lines += ["", f"**Partial setup:** {', '.join(incomplete)} still need real keys."]

    return "\n".join(lines)


def _format_events(snap: dict) -> str:
    """Which platforms could track optimization events, based on configured credentials."""
    cfg = snap["config"]
    lines = [
        "## Optimization Events",
        "Each platform needs ~50 conversion events/week to exit learning. "
        "This check reports which platforms COULD track events (credentials ready), "
        "not whether events are actually firing — that requires live data.",
        "",
        "| Platform | Credentials | Event tracking possible |",
        "|---|---|---|",
    ]
    platform_events = {
        "google-ads": ("Google Ads (Pixel/CAPI)", True),
        "meta-ads": ("Meta (Pixel/Conversions API)", True),
    }
    for group, (label, has_events) in platform_events.items():
        g = cfg["groups"].get(group, {"ready": False})
        status = "YES — keys configured" if g.get("ready") else "NO — keys missing"
        lines.append(f"| {label} | {'✓' if g.get('ready') else '✗'} | {status} |")

    lines += [
        "",
        "**COD note:** for cash-on-delivery accounts, track the 'Delivered' event "
        "(not 'Purchase') — the platform conversion counts confirmations, but "
        "your real revenue is only delivered orders.",
    ]
    return "\n".join(lines)


def run(tenant: TenantContext, opts: dict | None = None) -> int:
    opts = opts or {}
    verb = opts.get("verb", "check")
    snap = collect_snapshot(tenant)
    now = snap["now"]

    if verb == "check":
        body = _format_check(snap)
    elif verb == "events":
        body = _format_events(snap)
    else:
        print(f"ERROR: unknown tracking verb '{verb}'", file=sys.stderr)
        return 1

    header = f"# {tenant.name} — Tracking: {verb} — {now.strftime('%Y-%m-%d %H:%M')}"
    full = header + "\n\n" + body

    report_path = tenant.reports_dir / f"{now.strftime('%Y-%m-%d-%H')}-tracking-{verb}.md"
    report_path.write_text(full, encoding="utf-8")
    print(full)
    print(f"\n[{tenant.name}] tracking {verb}: report written -> {report_path}")
    append_log(tenant.name, f"tracking-{verb}", f"Tracking {verb} from kernel state", report_path)
    return 0