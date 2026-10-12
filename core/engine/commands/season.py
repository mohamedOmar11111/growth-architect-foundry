"""growth_engine.commands.season — seasonal planning.

One verb:
  plan — season-aware content and budget plan based on upcoming dates

The MENA calendar has clear high-stakes periods: Ramadan, Eid al-Fitr,
Eid al-Adha, White Friday (the regional Black Friday equivalent), Saudi
National Day, UAE National Day. This command checks the current date
against upcoming seasonal windows and recommends preparation timelines
with concrete actions — not generic "prepare early" advice.
"""

from __future__ import annotations

import datetime

from tenant import TenantContext
from utils import append_log
from commands.state import collect_snapshot


# Approximate dates for upcoming MENA seasons — last verified 2026-10.
# Recurrence varies by lunar calendar; always label as approximate.
SEASONS_2026_2027 = [
    ("White Friday", datetime.date(2026, 11, 27), 21,
     "GCC peak shopping — budget 2x, creative 3 weeks early, Arabic-first."),
    ("Saudi National Day", datetime.date(2026, 9, 23), 14,
     "KSA-specific — patriotic creative, localized offers, 2-week run."),
    ("UAE National Day", datetime.date(2026, 12, 2), 14,
     "UAE-specific — same pattern as Saudi National Day."),
    ("Ramadan 2027 (approx)", datetime.date(2027, 2, 18), 30,
     "Biggest MENA window — shift to evening/night scheduling, Arabic dialect "
     "copy, food/gifting angles. Budget +30-50%. Creative 4 weeks early."),
    ("Eid al-Fitr 2027 (approx)", datetime.date(2027, 3, 20), 14,
     "Post-Ramadan gifting spike — urgency creative, delivery cut-off dates."),
    ("Eid al-Adha 2027 (approx)", datetime.date(2027, 5, 27), 14,
     "Gifting + family — similar to Eid al-Fitr but shorter window."),
]


def run(tenant: TenantContext, opts: dict | None = None) -> int:
    snap = collect_snapshot(tenant)
    now = snap["now"]
    today = now.date()

    upcoming = [(name, start, lead, advice) for name, start, lead, advice in SEASONS_2026_2027
                if start > today]
    active = [(name, start, lead, advice) for name, start, lead, advice in SEASONS_2026_2027
              if start <= today <= start + datetime.timedelta(days=7)]

    lines = [
        f"# {tenant.name} — Seasonal Plan — {now.strftime('%Y-%m-%d')}",
        "",
    ]

    if active:
        lines += ["## 🔴 ACTIVE NOW", ""]
        for name, start, lead, advice in active:
            lines += [f"### {name}", f"Date: {start} (today)", advice, ""]

    if upcoming:
        lines += ["## Upcoming Seasons", ""]
        for name, start, lead, advice in upcoming:
            days_until = (start - today).days
            prep_start = start - datetime.timedelta(days=lead)
            prep_status = "PREP WINDOW OPEN" if today >= prep_start else f"prep starts {prep_start}"
            lines += [
                f"### {name}",
                f"- **Date:** {start} ({days_until} days away)",
                f"- **Lead time:** {lead} days — {prep_status}",
                f"- **Action:** {advice}",
                "",
            ]
            if today >= prep_start and days_until > 0:
                lines.append(f"⚠️ **Start now:** {days_until} days left — creative and budget should be ready.")
                lines.append("")
    else:
        lines += ["No upcoming seasons in the calendar. Update SEASONS_2026_2027 "
                  "in season.py with accurate dates."]

    lines += ["", "---",
              "*Dates are approximate (lunar calendar shifts ~10 days/year). "
              "Verify before committing budget. Last verified: 2026-10.*"]

    report_path = tenant.reports_dir / f"{now.strftime('%Y-%m-%d-%H')}-season-plan.md"
    full = "\n".join(lines)
    report_path.write_text(full, encoding="utf-8")
    print(full)
    print(f"\n[{tenant.name}] season plan: report written -> {report_path}")
    append_log(tenant.name, "season-plan", "Seasonal plan from kernel state", report_path)
    return 0