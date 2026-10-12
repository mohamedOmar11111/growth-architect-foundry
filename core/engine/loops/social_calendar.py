"""growth_engine.loops.social_calendar — turns finished content briefs into
a scheduled, platform-allocated calendar entry.

Deliberately does NOT read raw signals/ directly — content_engine.py
already consumes content-idea signals and would race this loop for the
same files (both call read_signals(unprocessed_only=True) and both would
try to mark_signal_linked; whichever runs first claims it, silently
starving the other). Pipeline instead: ad-intel/meta-ads -> signals ->
content-engine -> drafts in 02_Content/ -> social-calendar -> a scheduled
calendar entry. content-engine decides WHAT to write about; this loop
decides WHEN/WHERE (platform + day), using
01_Context_Vault/Agents/marketing/marketing-social-media-strategist.md's
decision framework as a deterministic ruleset, not an LLM call — same
"loops are deterministic automation, judgment stays with an
agent/operator" rule every other loop in this kernel follows.

Idempotency: since the input here is a brief FILE, not a signals.py-schema
signal, there's no `linked-task` frontmatter field to flip. Marks a brief
processed by appending a footer line to the brief file itself and checking
for that marker before reprocessing — same "modify in place to record
state" pattern signals.py's mark_signal_linked() already uses, applied to
a different file type.
"""

from __future__ import annotations

import datetime
import re

from tenant import TenantContext
from tasks import write_task
from utils import append_log

PLATFORMS = ("twitter", "linkedin", "instagram", "tiktok", "reddit")
SCHEDULED_MARKER = "<!-- scheduled-by-social-calendar -->"
CALENDAR_LOOKBACK_DAYS = 14


def _strategy_directives(strategy_md: str) -> tuple[set[str], set[str]]:
    """Extracts AVOID/PREFER platform directives from STRATEGY.md via plain
    text search — deliberately simple, not an LLM call. Matches the
    "AVOID: <what> — <reason>" / "PREFER: <what> — <reason>" format
    STRATEGY.md's own directive convention already uses."""
    avoid: set[str] = set()
    prefer: set[str] = set()
    for line in strategy_md.splitlines():
        lower = line.lower()
        for platform in PLATFORMS:
            if platform not in lower:
                continue
            if "avoid" in lower:
                avoid.add(platform)
            elif "prefer" in lower:
                prefer.add(platform)
    return avoid, prefer


def _platform_frequency(calendar_path) -> dict[str, int]:
    """Counts how many times each platform appears in the calendar's
    existing rows from the last CALENDAR_LOOKBACK_DAYS — used to pick the
    least-recently-used eligible platform so one platform doesn't get
    starved while another gets spammed, same cadence-balance goal
    marketing-social-media-strategist.md's Decision Framework describes."""
    counts = {p: 0 for p in PLATFORMS}
    if not calendar_path.exists():
        return counts
    cutoff = datetime.date.today() - datetime.timedelta(days=CALENDAR_LOOKBACK_DAYS)
    for line in calendar_path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(\w+)\s*\|", line)
        if not match:
            continue
        try:
            row_date = datetime.date.fromisoformat(match.group(1))
        except ValueError:
            continue
        platform = match.group(2).lower()
        if row_date >= cutoff and platform in counts:
            counts[platform] += 1
    return counts


def _pick_platform(avoid: set[str], prefer: set[str], frequency: dict[str, int]) -> str:
    eligible = [p for p in PLATFORMS if p not in avoid]
    if not eligible:
        # Every platform is under an AVOID directive — falls back to the
        # least-restricted option rather than crashing, but this is a
        # genuinely unusual tenant config worth a human double-checking.
        eligible = list(PLATFORMS)
    preferred_eligible = [p for p in eligible if p in prefer]
    pool = preferred_eligible or eligible
    return min(pool, key=lambda p: frequency.get(p, 0))


def _format_target(platform: str) -> str:
    return {
        "twitter": "thread",
        "linkedin": "document/carousel post",
        "instagram": "carousel or reel",
        "tiktok": "short-form video script",
        "reddit": "community discussion post (no hard promotion)",
    }.get(platform, "post")


PLATFORM_AGENT_FILE = {
    "twitter": "marketing-twitter-engager.md",
    "linkedin": "marketing-linkedin-strategist.md",
    "instagram": "marketing-instagram-curator.md",
    "tiktok": "marketing-tiktok-strategist.md",
    "reddit": "marketing-reddit-community-builder.md",
}


def _pending_briefs(tenant: TenantContext) -> list:
    content_dir = tenant.root / "02_Content"
    if not content_dir.is_dir():
        return []
    pending = []
    for path in sorted(content_dir.glob("*brief*.md")):
        if SCHEDULED_MARKER not in path.read_text(encoding="utf-8"):
            pending.append(path)
    return pending


def run(tenant: TenantContext) -> int:
    calendar_dir = tenant.root / "02_Content" / "calendar"
    calendar_dir.mkdir(parents=True, exist_ok=True)
    calendar_path = calendar_dir / "content_calendar.md"

    if not calendar_path.exists():
        calendar_path.write_text(
            "# Content Calendar — scheduled by social-calendar, all DRAFT until approved\n\n"
            "| Date | Platform | Format | Source Brief | Status |\n"
            "|---|---|---|---|---|\n",
            encoding="utf-8",
        )

    avoid, prefer = _strategy_directives(tenant.strategy_md)
    briefs = _pending_briefs(tenant)

    scheduled = 0
    now = datetime.datetime.now()
    for i, brief_path in enumerate(briefs):
        frequency = _platform_frequency(calendar_path)
        platform = _pick_platform(avoid, prefer, frequency)
        format_target = _format_target(platform)
        # Space entries a day apart within this run rather than stacking
        # every brief on today — a naive "schedule everything for today"
        # would defeat the whole cadence-balancing point of this loop.
        schedule_date = (now.date() + datetime.timedelta(days=i)).isoformat()

        with open(calendar_path, "a", encoding="utf-8") as f:
            f.write(f"| {schedule_date} | {platform} | {format_target} | "
                    f"{brief_path.name} | DRAFT |\n")

        brief_path.write_text(
            brief_path.read_text(encoding="utf-8") +
            f"\n{SCHEDULED_MARKER}\n> Scheduled for {platform} ({format_target}) "
            f"on {schedule_date} — see 02_Content/calendar/content_calendar.md\n",
            encoding="utf-8",
        )

        write_task(
            tenant,
            domain="social-calendar",
            priority="medium",
            task_summary=f"Approve and execute {platform} {format_target} for {schedule_date}",
            context=(
                f"Auto-scheduled by social-calendar from brief `{brief_path.name}`. "
                f"Platform allocation: {platform} (picked via cadence-balance + "
                "tenant STRATEGY.md directives, not manually chosen). Actual copy/"
                f"script still needs writing — see "
                f"01_Context_Vault/Agents/marketing/{PLATFORM_AGENT_FILE[platform]} "
                "for that platform's actual writing rules."
            ),
            acceptance_criteria=[
                "Operator has reviewed the platform/date allocation",
                "Actual copy/script drafted using the matching platform agent",
                "Approved for posting or discarded — this task does not post anything",
            ],
            linked_signal="none",
            slug=f"{platform}-{schedule_date}-{brief_path.stem[:30]}",
        )
        scheduled += 1
        print(f"[{tenant.name}] social-calendar: '{brief_path.name}' -> "
              f"{platform} ({format_target}) on {schedule_date}")

    print(f"[{tenant.name}] social-calendar: {scheduled} brief(s) scheduled, "
          f"{len(briefs) - scheduled} skipped")

    if scheduled:
        append_log(
            tenant.name, "social-calendar",
            f"Scheduled {scheduled} content brief(s) across platforms, all DRAFT pending approval",
            calendar_path,
        )

    return 0
