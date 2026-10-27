"""growth_engine.commands.report — the client readout, decision-first.

Deliberately NOT a data dump: the verdict and the decisions needed come
first, evidence after. A report a client can't act on is content, not
reporting.

Output contract:
  1. VERDICT — one line: what changed and what needs a decision
  2. The numbers — signals / tasks / content / spend for the period
  3. Decisions needed — open high-priority work, owner named
  4. Done this period — from log.md, the actual run history
  5. Next up — the cadence that's due

Languages: `en` (default) and `ar` — Arabic is written in MSA with platform
and industry terms kept in English (ROAS, CPA, CTR, Pixel), the way a MENA
media buyer actually talks. `--period week` (default) or `month`.
"""

from __future__ import annotations

import datetime
import sys

from tenant import TenantContext
from utils import append_log
from commands.state import collect_snapshot, operator_name, resolve_target_cpa
from commands import perf, perf_text

PERIOD_DAYS = {"week": 7, "month": 30}

STRINGS = {
    "en": {
        "title": "{tenant} — {period} Report — {date}",
        "verdict": "**VERDICT:** {decisions} decision(s) waiting on you this "
                   "{period}, {open_tasks} open task(s), {signals} signal(s) "
                   "still unprocessed. Last engine run: {last_run}.",
        "numbers": "## The Numbers ({days} days)",
        "table_head": "| Metric | Count |",
        "m_signals_written": "Signals written",
        "m_signals_processed": "Signals processed",
        "m_tasks_opened": "Tasks opened",
        "m_tasks_closed": "Tasks closed",
        "m_briefs_drafted": "Content briefs drafted",
        "m_engine_runs": "Engine runs logged",
        "m_ad_spend": "Ad spend (captured report)",
        "decisions": "## Decisions Needed",
        "no_decisions": "Nothing is waiting on a decision — the queue is clean.",
        "done": "## Done This Period",
        "no_done": "No engine runs logged in this period.",
        "next_up": "## Next Up",
        "footer": "*Generated deterministically from this tenant's kernel state — "
                  "counts come from files on disk. Spend figures come from the last "
                  "captured ad-intel report and may not cover the full period.*",
        "owner": "owner",
        "period_label": {"week": "week", "month": "month"},
        "default_operator": "the operator",
        "last_run_never": "never",
        "last_run_days": "{n} day(s) ago",
        "next_up_line": "{operator}: review the decisions above before the next "
                        "cadence run.",
        "pending_ad": "ad-intel (no captured report yet)",
        "pending_social": "social-calendar (briefs exist, no calendar)",
    },
    "ar": {
        "title": "{tenant} — تقرير {period} — {date}",
        "verdict": "**الخلاصة:** {decisions} قرار(قرارات) بانتظارك هذا {period}، "
                   "{open_tasks} مهمة مفتوحة، {signals} إشارة(إشارات) لم تُعالج بعد. "
                   "آخر تشغيل للمحرك: {last_run}.",
        "numbers": "## الأرقام ({days} يوم)",
        "table_head": "| المؤشر | العدد |",
        "m_signals_written": "إشارات جديدة",
        "m_signals_processed": "إشارات تمت معالجتها",
        "m_tasks_opened": "مهام جديدة",
        "m_tasks_closed": "مهام مغلقة",
        "m_briefs_drafted": "موجزات محتوى",
        "m_engine_runs": "عمليات تشغيل للمحرك",
        "m_ad_spend": "إنفاق إعلاني (من تقرير محفوظ)",
        "decisions": "## قرارات مطلوبة",
        "no_decisions": "لا يوجد ما ينتظر قراراً — الطابور نظيف.",
        "done": "## ما تم إنجازه خلال الفترة",
        "no_done": "لا يوجد تشغيل مسجل خلال هذه الفترة.",
        "next_up": "## الخطوة التالية",
        "footer": "*أُنشئ هذا التقرير آلياً من حالة المحرك — الأرقام مأخوذة من ملفات "
                  "على القرص. أرقام الإنفاق من آخر تقرير ad-intel محفوظ وقد لا تغطي "
                  "الفترة كاملة.*",
        "owner": "المسؤول",
        "period_label": {"week": "الأسبوع", "month": "الشهر"},
        "default_operator": "المشغّل",
        "last_run_never": "لم يُشغَّل بعد",
        "last_run_days": "منذ {n} يوم",
        "next_up_line": "{operator}: راجع القرارات أعلاه قبل دورة التشغيل القادمة.",
        "pending_ad": "ad-intel (لا يوجد تقرير محفوظ بعد)",
        "pending_social": "social-calendar (توجد موجزات لكن لا يوجد تقويم)",
    },
}


def _count_in_period(items: list[dict], date_key: str, cutoff: datetime.date) -> int:
    count = 0
    for item in items:
        raw = item.get(date_key)
        try:
            when = datetime.datetime.strptime(str(raw), "%Y-%m-%d")
        except (TypeError, ValueError):
            continue
        if when.date() >= cutoff:
            count += 1
    return count


def build_report_data(snap: dict, days: int) -> dict:
    cutoff = (snap["now"] - datetime.timedelta(days=days)).date()
    entries = [e for e in snap["log_entries"] if e["when"].date() >= cutoff]
    opened = _count_in_period(snap["tasks"], "date", cutoff)

    closed = 0
    for task in snap["done_tasks"]:
        try:
            when = datetime.datetime.strptime(str(task.get("date")), "%Y-%m-%d")
        except (TypeError, ValueError):
            continue
        if when.date() >= cutoff:
            closed += 1

    content_dir = snap["tenant"].root / "02_Content"
    briefs = 0
    if content_dir.exists():
        for path in content_dir.glob("*brief*.md"):
            if datetime.datetime.fromtimestamp(path.stat().st_mtime).date() >= cutoff:
                briefs += 1

    decisions = []
    for sig in snap["high_unprocessed"]:
        body_lines = str(sig.get("_body") or "").splitlines()
        decisions.append({
            "what": body_lines[0][:120] if body_lines else sig["_path"].name,
            "owner": sig.get("source", "operator"),
            "ref": sig["_path"].name,
        })
    for task in snap["open_tasks"]:
        if task.get("priority") == "high":
            body_lines = str(task.get("_body") or "").splitlines()
            decisions.append({
                "what": f"Task: {task.get('domain', 'manual')} — "
                        f"{body_lines[0][:100] if body_lines else task['_path'].name}",
                "owner": str(task.get("owner", "operator")),
                "ref": task["_path"].name,
            })

    linked = [s for s in snap["signals"] if s.get("linked-task", "none") != "none"]
    ad = snap["ad_report"]
    return {
        "entries": entries,
        "signals_written": _count_in_period(snap["signals"], "date", cutoff),
        "signals_processed": _count_in_period(linked, "date", cutoff),
        "tasks_opened": opened,
        "tasks_closed": closed,
        "briefs": briefs,
        "engine_runs": len(entries),
        "ad_spend": ad["totals"]["cost"] if ad else None,
        "decisions": decisions,
    }


def format_report(tenant: TenantContext, snap: dict, data: dict,
                  lang: str, period: str, days: int) -> str:
    s = STRINGS[lang]
    operator = operator_name(tenant) or s["default_operator"]
    period_label = s["period_label"][period]
    last_entry = max((e["when"] for e in snap["log_entries"]), default=None)
    last_run = (
        s["last_run_days"].format(n=(snap["now"] - last_entry).days)
        if last_entry else s["last_run_never"]
    )

    lines = [
        s["title"].format(tenant=tenant.name, period=period_label,
                          date=snap["now"].strftime("%Y-%m-%d")),
        "",
        s["verdict"].format(
            decisions=len(data["decisions"]), period=period_label,
            open_tasks=len(snap["open_tasks"]), signals=len(snap["unprocessed"]),
            last_run=last_run,
        ),
        "",
        s["numbers"].format(days=days),
        s["table_head"],
        "|---|---|",
    ]
    rows = [
        ("m_signals_written", data["signals_written"]),
        ("m_signals_processed", data["signals_processed"]),
        ("m_tasks_opened", data["tasks_opened"]),
        ("m_tasks_closed", data["tasks_closed"]),
        ("m_briefs_drafted", data["briefs"]),
        ("m_engine_runs", data["engine_runs"]),
    ]
    for key, value in rows:
        lines.append(f"| {s[key]} | {value} |")
    spend = data["ad_spend"]
    lines.append(f"| {s['m_ad_spend']} | {spend:.2f} |" if spend is not None
                 else f"| {s['m_ad_spend']} | — |")

    lines += ["", s["decisions"]]
    if data["decisions"]:
        for d in data["decisions"][:8]:
            lines.append(f"- {d['what']} — {s['owner']}: {d['owner']} (`{d['ref']}`)")
    else:
        lines.append(s["no_decisions"])

    lines += ["", s["done"]]
    if data["entries"]:
        for e in data["entries"]:
            lines.append(f"- {e['when'].strftime('%Y-%m-%d %H:%M')} · {e['loop']}")
    else:
        lines.append(s["no_done"])

    lines += ["", s["next_up"],
              "- " + s["next_up_line"].format(operator=operator)]
    pending_loops = []
    if not snap["ad_report"]:
        pending_loops.append(s["pending_ad"])
    if snap["content"]["briefs"] and not snap["content"]["calendar"]:
        pending_loops.append(s["pending_social"])
    for loop in pending_loops:
        lines.append(f"- {loop}")

    lines += ["", "---", s["footer"]]
    return "\n".join(lines)


def format_whatsapp_report(tenant: TenantContext, snap: dict, data: dict,
                           lang: str, period: str, days: int) -> str:
    s = STRINGS[lang]
    period_label = s["period_label"][period]
    date_str = snap["now"].strftime("%Y-%m-%d")
    spend = data["ad_spend"]
    spend_str = f"{spend:,.2f}" if spend is not None else "—"

    if lang == "ar":
        lines = [
            f"*ملخص الأداء — {tenant.name}* ({period_label} · {date_str})",
            "",
            f"📌 *الخلاصة:* {len(data['decisions'])} قرارات بانتظار الاعتماد | "
            f"{len(snap['open_tasks'])} مهام مفتوحة | {len(snap['unprocessed'])} إشارات جديدة",
            "",
            f"*الأرقام ({days} يوم):*",
            f"• الإنفاق الإعلاني: {spend_str}",
            f"• إشارات تمت معالجتها: {data['signals_processed']}/{data['signals_written']}",
            f"• مهام أُنجزت: {data['tasks_closed']}/{data['tasks_opened']}",
            f"• موجزات محتوى: {data['briefs']}",
            "",
            "*قرارات تحتاج موافقتك (رد بـ OK للاعتماد):*",
        ]
        if data["decisions"]:
            for i, d in enumerate(data["decisions"][:5], 1):
                lines.append(f"{i}. {d['what']}")
        else:
            lines.append("• لا توجد قرارات معلقة حالياً.")
    else:
        lines = [
            f"*{tenant.name} — {period_label.title()} Executive Digest* ({date_str})",
            "",
            f"📌 *VERDICT:* {len(data['decisions'])} decision(s) waiting on you | "
            f"{len(snap['open_tasks'])} open task(s) | {len(snap['unprocessed'])} unprocessed signal(s)",
            "",
            f"*The Numbers ({days}d):*",
            f"• Ad Spend: {spend_str}",
            f"• Signals Processed: {data['signals_processed']}/{data['signals_written']}",
            f"• Tasks Closed: {data['tasks_closed']}/{data['tasks_opened']}",
            f"• Content Briefs: {data['briefs']}",
            "",
            "*Decisions Needed (Reply OK to approve):*",
        ]
        if data["decisions"]:
            for i, d in enumerate(data["decisions"][:5], 1):
                lines.append(f"{i}. {d['what']}")
        else:
            lines.append("• Queue is clean — no pending decisions.")
    return "\n".join(lines)


def _run_csv(tenant: TenantContext, opts: dict, snap: dict, lang: str, fmt: str) -> int:
    """CSV mode: a client-facing performance readout from the imported export, not the operator queue."""
    ad = snap["ad_report"]
    analysis = perf.analyse_report(ad, resolve_target_cpa(tenant, opts))
    date = snap["now"].strftime("%Y-%m-%d")
    if fmt == "whatsapp":
        report, suffix = perf_text.format_whatsapp(tenant.name, date, analysis, ad["currency"], lang), f"-report-{lang}-whatsapp.txt"
    else:
        report, suffix = perf_text.format_report(tenant.name, date, analysis, ad["currency"], lang, ad["conversions_basis"]), f"-report-{lang}.md"
    report_path = tenant.reports_dir / f"{snap['now'].strftime('%Y-%m-%d-%H')}{suffix}"
    report_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n[{tenant.name}] report: written -> {report_path} — DRAFT, needs operator review before it goes to the client.")
    append_log(tenant.name, "report", f"CSV performance report generated ({lang})", report_path)
    return 0


def run(tenant: TenantContext, opts: dict | None = None) -> int:
    opts = opts or {}
    lang = str(opts.get("lang") or "en").lower()
    if lang not in STRINGS:
        print(f"ERROR: unsupported --lang '{lang}' — use 'en' or 'ar'.")
        return 1
    period = str(opts.get("period") or "week").lower()
    days = PERIOD_DAYS.get(period)
    if days is None:
        print(f"ERROR: unsupported --period '{period}' — use 'week' or 'month'.")
        return 1
    fmt = str(opts.get("format") or "markdown").lower()
    if fmt not in ("markdown", "md", "whatsapp"):
        print(f"ERROR: unsupported --format '{fmt}' — use 'markdown' or 'whatsapp'.", file=sys.stderr)
        return 2

    snap = collect_snapshot(tenant)
    if snap["csv_mode"]:
        return _run_csv(tenant, opts, snap, lang, fmt)
    data = build_report_data(snap, days)
    if fmt == "whatsapp":
        report = format_whatsapp_report(tenant, snap, data, lang, period, days)
        suffix = f"-report-{period}-{lang}-whatsapp.txt"
    else:
        report = format_report(tenant, snap, data, lang, period, days)
        suffix = f"-report-{period}-{lang}.md"

    report_path = tenant.reports_dir / f"{snap['now'].strftime('%Y-%m-%d-%H')}{suffix}"
    report_path.write_text(report, encoding="utf-8")

    print(report)
    print(f"\n[{tenant.name}] report: written -> {report_path} — "
          "DRAFT, needs operator review before it goes to the client.")
    append_log(tenant.name, "report",
               f"{period} report generated ({lang}) with "
               f"{len(data['decisions'])} decision(s) pending",
               report_path)
    return 0
