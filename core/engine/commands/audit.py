"""growth_engine.commands.audit — 0-100 account health score from real state.

Output contract (same shape every time, so an operator can diff two audits):
  1. VERDICT — one line: score, grade, the single weakest dimension
  2. Dimension table — subscore /100 + weight + one-line evidence
  3. TOP FIXES — ranked by weighted deficit, max 5, each actionable
  4. DO NOT TOUCH — dimensions scoring 85+, because protecting what works
     is half the job
  5. 30-DAY PLAN — do today / test this week / stop-or-reduce

Scoring is deterministic and explainable: every point lost is tied to a
named condition in this tenant's own files. A low score is never invented
to seem useful — an empty demo tenant legitimately scores mid-range, and
the notes say exactly why.
"""

from __future__ import annotations

import datetime

from tenant import TenantContext
from utils import append_log
from commands.state import collect_snapshot

REQUIRED_STRATEGY_SECTIONS = (
    "brand overview", "target audience", "voice", "active directives",
)

DIMENSION_WEIGHTS = {
    "Configuration": 0.25,
    "Signal hygiene": 0.20,
    "Task throughput": 0.20,
    "Loop activity": 0.15,
    "Content readiness": 0.20,
}

GRADE_BANDS = ((90, "A"), (80, "B"), (70, "C"), (60, "D"), (0, "F"))


def grade_for(score: float) -> str:
    for floor, letter in GRADE_BANDS:
        if score >= floor:
            return letter
    return "F"


def _score_configuration(snap: dict) -> tuple[float, str]:
    cfg = snap["config"]
    groups = cfg["groups"]
    total_required = sum(g["required"] for g in groups.values())
    total_configured = sum(g["configured"] for g in groups.values())

    score = (total_configured / total_required) * 70 if total_required else 0.0
    if cfg["operator_set"]:
        score += 15
    if cfg["target_cpa"]:
        score += 15

    ready = [name for name, g in groups.items() if g["ready"]]
    note = (
        f"{total_configured}/{total_required} ad credentials configured "
        f"({', '.join(ready) if ready else 'none ready'}); "
        f"operator={'set' if cfg['operator_set'] else 'unset'}, "
        f"target CPA={'set' if cfg['target_cpa'] else 'unset'}"
    )
    return min(score, 100.0), note


def _score_signal_hygiene(snap: dict) -> tuple[float, str]:
    if not snap["signals"]:
        return 50.0, "no signals written yet — nothing to process, nothing to judge"

    score = 100.0
    score -= min(len(snap["unprocessed"]) * 10, 50)
    score -= min(len(snap["high_unprocessed"]) * 15, 30)
    if snap["oldest_open_age_days"] > 7:
        score -= min((snap["oldest_open_age_days"] // 7) * 5, 20)
    return max(score, 0.0), (
        f"{len(snap['unprocessed'])} unprocessed signal(s) "
        f"({len(snap['high_unprocessed'])} high priority), "
        f"oldest open for {snap['oldest_open_age_days']} day(s)"
    )


def _score_task_throughput(snap: dict) -> tuple[float, str]:
    tasks = snap["tasks"]
    if not tasks:
        return 40.0, "no tasks written yet — no throughput to measure"

    closure_rate = len(snap["done_tasks"]) / len(tasks)
    score = closure_rate * 100 - len(snap["stuck_tasks"]) * 20
    return max(min(score, 100.0), 0.0), (
        f"{len(snap['done_tasks'])}/{len(tasks)} tasks done "
        f"({closure_rate * 100:.0f}% closure), {len(snap['stuck_tasks'])} stuck "
        "at max attempts"
    )


def _score_loop_activity(snap: dict) -> tuple[float, str]:
    entries = snap["log_entries"]
    if not entries:
        return 10.0, "no engine runs logged yet — kernel has never fired against this tenant"

    loops_seen = {e["loop"] for e in entries}
    score = min(len(loops_seen) / 6, 1.0) * 50

    age_days = (snap["now"] - max(e["when"] for e in entries)).days
    score += 50 if age_days <= 1 else 35 if age_days <= 7 else 15 if age_days <= 30 else 0
    return min(score, 100.0), (
        f"{len(entries)} run(s) across {len(loops_seen)} loop(s) "
        f"({', '.join(sorted(loops_seen))}), last run {age_days} day(s) ago"
    )


def _score_content_readiness(snap: dict) -> tuple[float, str]:
    headers = snap["strategy_headers"]
    present = [s for s in REQUIRED_STRATEGY_SECTIONS if s in headers]
    score = (len(present) / len(REQUIRED_STRATEGY_SECTIONS)) * 60

    content = snap["content"]
    if content["briefs"]:
        score += 20
    if content["calendar"]:
        score += 20
    return min(score, 100.0), (
        f"STRATEGY.md sections {len(present)}/{len(REQUIRED_STRATEGY_SECTIONS)}, "
        f"{content['briefs']} brief(s), calendar={'yes' if content['calendar'] else 'no'}"
    )


SCORERS = {
    "Configuration": _score_configuration,
    "Signal hygiene": _score_signal_hygiene,
    "Task throughput": _score_task_throughput,
    "Loop activity": _score_loop_activity,
    "Content readiness": _score_content_readiness,
}

FIX_TEXT = {
    "Configuration": (
        "Set real credentials in this tenant's .env (a copied .env.example "
        "reports as unconfigured on purpose) and set TARGET_CPA — without a "
        "target, media advice is content, not media buying."
    ),
    "Signal hygiene": (
        "Clear the signal backlog: link or discard each unprocessed signal, "
        "high priority first. An unprocessed signal is working state, not memory."
    ),
    "Task throughput": (
        "Drive open tasks to done or cancelled, and resolve anything stuck at "
        "max attempts — either fix the blocker or cancel the task explicitly."
    ),
    "Loop activity": (
        "Run the loops on their documented cadence (ad-intel/meta-ads every 6h, "
        "content-engine every 3 days) — schedule run_loop.py and the log fills itself."
    ),
    "Content readiness": (
        "Fill any missing STRATEGY.md sections (Brand Overview, Target Audience, "
        "Voice, Active Directives), then run content-engine and social-calendar so "
        "the pipeline actually produces briefs and a calendar."
    ),
}

HEALTHY_TEXT = {
    "Configuration": "Credentials and target are configured — leave them alone.",
    "Signal hygiene": "Backlog is clean — don't reintroduce signal debt.",
    "Task throughput": "Task closure is healthy — protect this cadence.",
    "Loop activity": "Loops are running on cadence — don't re-tune what's working.",
    "Content readiness": "Strategy and content pipeline are in place — don't rewrite the voice rules.",
}


def _weighted_deficit(subscore: float, dimension: str) -> float:
    return (100.0 - subscore) * DIMENSION_WEIGHTS[dimension]


def build_audit(snap: dict) -> dict:
    scores: dict[str, tuple[float, str]] = {
        name: scorer(snap) for name, scorer in SCORERS.items()
    }
    total = sum(s * DIMENSION_WEIGHTS[name] for name, (s, _) in scores.items())
    return {
        "total": total,
        "grade": grade_for(total),
        "scores": scores,
        "deficits": {name: _weighted_deficit(s, name) for name, (s, _) in scores.items()},
    }


def format_audit(tenant: TenantContext, snap: dict, audit: dict) -> str:
    scores = audit["scores"]
    weakest = max(audit["deficits"], key=audit["deficits"].get)
    strongest = max(scores, key=lambda n: scores[n][0])
    now = snap["now"].strftime("%Y-%m-%d %H:%M")

    lines = [
        f"# {tenant.name} — Account Audit — {now}",
        "",
        f"**VERDICT:** {audit['total']:.0f}/100 (grade {audit['grade']}) — "
        f"weakest dimension is **{weakest}** "
        f"({scores[weakest][0]:.0f}/100). "
        f"Strongest is {strongest} ({scores[strongest][0]:.0f}/100).",
        "",
        "Every score below is computed from this tenant's own kernel state "
        "(signals, tasks, log.md, captured reports, .env) — no estimates, no "
        "benchmark guessing.",
        "",
        "## Dimension Scores",
        "| Dimension | Weight | Score | Evidence |",
        "|---|---|---|---|",
    ]
    for name, (sub, note) in scores.items():
        lines.append(f"| {name} | {DIMENSION_WEIGHTS[name] * 100:.0f}% | "
                     f"{sub:.0f}/100 | {note} |")

    lines += ["", "## Top Fixes (ranked by weighted deficit)"]
    ranked = sorted(audit["deficits"], key=audit["deficits"].get, reverse=True)
    fixes = [n for n in ranked if scores[n][0] < 85][:5]
    if fixes:
        for i, name in enumerate(fixes, 1):
            lines.append(f"{i}. **{name}** — {FIX_TEXT[name]}")
    else:
        lines.append("None — every dimension is at or above 85. This account is "
                     "in good shape; spend the week on growth, not repair.")

    healthy = [n for n in scores if scores[n][0] >= 85]
    lines += ["", "## Do Not Touch"]
    if healthy:
        for name in healthy:
            lines.append(f"- **{name}:** {HEALTHY_TEXT[name]}")
    else:
        lines.append("- Nothing yet — no dimension is healthy enough to protect. "
                     "Fix first, protect later.")

    lines += ["", "## 30-Day Plan"]
    if fixes:
        lines += [
            f"- **Do today:** {FIX_TEXT[fixes[0]]}",
            f"- **Test this week:** {FIX_TEXT[fixes[1] if len(fixes) > 1 else fixes[0]]} "
            "Hypothesis: acting on this moves the dimension score above 70 "
            "within 7 days — re-run `audit` and compare.",
            f"- **Stop / reduce:** {'Stop leaving high-priority signals unprocessed'
                if snap['high_unprocessed'] else
                'Nothing identified as waste in current data — revisit once '
                'ad-intel has real spend data to look at'}.",
        ]
    else:
        lines += [
            "- **Do today:** nothing — all dimensions healthy.",
            "- **Test this week:** raise loop cadence or budget on the strongest "
            "channel, hypothesis first.",
            "- **Stop / reduce:** nothing identified as waste in current data.",
        ]

    lines += [
        "",
        "---",
        "*Deterministic audit — scores come from files on disk, not from a "
        "model. Re-run after every change and diff the two reports.*",
    ]
    return "\n".join(lines)


def run(tenant: TenantContext, opts: dict | None = None) -> int:
    snap = collect_snapshot(tenant)
    audit = build_audit(snap)
    report = format_audit(tenant, snap, audit)

    report_path = tenant.reports_dir / (
        f"{snap['now'].strftime('%Y-%m-%d-%H')}-audit.md"
    )
    report_path.write_text(report, encoding="utf-8")

    print(report)
    print(f"\n[{tenant.name}] audit: report written -> {report_path}")
    append_log(tenant.name, "audit",
               f"Account audit scored {audit['total']:.0f}/100 "
               f"(grade {audit['grade']})",
               report_path)
    return 0
