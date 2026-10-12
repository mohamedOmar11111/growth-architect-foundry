"""growth_engine.loops.lead_qualify — Root Bus loop, Phase 3 proof.

Unlike ad-intel/content-engine (tenant bus, folder-isolated), this loop reads
the single shared root `signals/` across ALL businesses — this is the
operator's personal cross-business queue, per the Dual-Bus ruling. No TenantContext;
`run()` takes no arguments.

Implements the exact S-Score model from domain/lead-qualify/README.md
(Budget 40 / Intent 35 / Authority 25, HOT >= 80). Two real data sources for
scoring, both honest about their limits:
  - `company_size` / `icp` frontmatter fields on the signal, if the upstream
    loop (command-chase, not yet built) supplied them
  - keyword match against the signal body for intent, per the README's own
    "HOT Signal Keywords" list — this is the only part of the model that can
    run on a freeform message with no structured research behind it

HOT lead -> Telegram alert fires immediately (see telegram.py). If the bot
token isn't configured yet, this loop does NOT pretend to have sent it — it
records the real failure reason in STATE.md and log.md instead.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

import requests

from root_bus import read_signals, mark_signal_linked, write_task, append_root_log, get_operator_name
from telegram import send_message, TelegramConfigError

from paths import DOMAIN_WORKSPACE  # noqa: E402
DOMAIN_ROOT = DOMAIN_WORKSPACE / "lead-qualify"
DRAFTS_DIR = DOMAIN_ROOT / "drafts"
STATE_PATH = DOMAIN_ROOT / "STATE.md"

BUDGET_SCORES = {"enterprise": 40, "mid-size": 25, "small": 10, "unknown": 5}
AUTHORITY_SCORES = {
    "panicked-cto": 25, "retail-transformer": 20,
    "marketing-director": 15, "founder-ceo": 20, "unknown": 5,
}
HOT_KEYWORDS = {
    "services", "proposal", "pricing", "available", "how much", "strategy",
    "consulting", "ads", "growth", "marketing", "campaign", "results",
}
OPENERS = {
    "panicked-cto": (
        "[Name], one question about [Company]'s setup — is your current digital "
        "infrastructure converting revenue or just burning budget? I have a "
        "specific fix for [sector] teams that removed that gap in 6 weeks."
    ),
    "retail-transformer": (
        "[Name], I helped [similar client] turn their [sector] business into a "
        "digital revenue engine in 30 days. Same playbook applies to [Company]. "
        "Worth 15 minutes to see if it fits?"
    ),
    "marketing-director": (
        "[Name], I noticed [Company] is running [platform] ads. Your CPA can "
        "likely drop 30-40% with one structural change — I fixed this exact "
        "pattern before. Can I show you the before/after in 10 minutes?"
    ),
    "founder-ceo": (
        "[Name], [Company] is growing in [sector]. The question isn't whether "
        "you do marketing — it's whether your current system holds up if you "
        "double in size. I have a specific answer."
    ),
}
GENERIC_OPENER = (
    "[Name], saw your message about [topic] — happy to share exactly how we've "
    "solved this for similar teams. Worth 15 minutes?"
)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def _extract_summary(body: str) -> str:
    if "## Summary" not in body:
        return body[:120]
    after = body.split("## Summary", 1)[1]
    return after.split("##", 1)[0].strip()


def _score_intent(body: str) -> tuple[int, str]:
    lower = body.lower()
    matched = [kw for kw in HOT_KEYWORDS if kw in lower]
    if matched:
        return 35, f"Explicit intent keywords matched: {', '.join(sorted(matched))}"
    if len(body.strip()) > 40:
        return 20, "General interest — message present, no explicit service keyword"
    return 5, "Engagement only, no clear intent signal"


def _score_lead(signal: dict) -> dict:
    company_size = str(signal.get("company_size", "unknown")).lower()
    icp = str(signal.get("icp", "unknown")).lower()
    budget_score = BUDGET_SCORES.get(company_size, BUDGET_SCORES["unknown"])
    authority_score = AUTHORITY_SCORES.get(icp, AUTHORITY_SCORES["unknown"])
    intent_score, intent_reason = _score_intent(signal.get("_body", ""))
    total = budget_score + authority_score + intent_score
    tier = "HOT" if total >= 80 else "WARM" if total >= 50 else "COLD"
    return {
        "total": total, "tier": tier, "company_size": company_size, "icp": icp,
        "budget_score": budget_score, "authority_score": authority_score,
        "intent_score": intent_score, "intent_reason": intent_reason,
    }


def _draft_outreach(signal: dict, result: dict, name: str, company: str, operator: str) -> str:
    opener = OPENERS.get(result["icp"], GENERIC_OPENER)
    personalized = opener.replace("[Name]", name).replace("[Company]", company)
    return f"""# Outreach Draft (NOT SENT — {operator} approves before send)

**Lead:** {name} @ {company}
**Score:** {result['total']}/100 ({result['tier']})
**Source signal:** `{signal['_path'].name}`
**Scoring breakdown:** budget {result['budget_score']}/40 (company_size={result['company_size']}) \
| intent {result['intent_score']}/35 ({result['intent_reason']}) \
| authority {result['authority_score']}/25 (icp={result['icp']})

## Original Message
{_extract_summary(signal['_body'])}

## Suggested Opener
{personalized}

## Status
Draft only. NEVER send without {operator}'s explicit approval.
"""


def _update_state(hot_rows: list[str], warm_rows: list[str], hot_count: int, warm_count: int) -> None:
    """Targeted line/table updates — not a full markdown rewrite, so manual
    edits elsewhere in STATE.md survive between runs."""
    if not STATE_PATH.exists():
        return
    text = STATE_PATH.read_text(encoding="utf-8")
    now = datetime.datetime.now()

    text = re.sub(r"^last-run:.*$", f"last-run: {now.strftime('%Y-%m-%d %H:%M')}", text, flags=re.MULTILINE)
    text = re.sub(r"^hot-leads-today:.*$", f"hot-leads-today: {hot_count}", text, flags=re.MULTILINE)

    if hot_rows:
        marker = "| Date | Name | Company | Score | Telegram Sent | Draft File | Status |\n|---|---|---|---|---|---|---|\n"
        text = text.replace(marker, marker + "\n".join(hot_rows) + "\n", 1)

    if warm_rows:
        marker = "| Name | Company | Sector | Source | S-Score | Status | Draft | Last Touch | Notes |\n|---|---|---|---|---|---|---|---|---|\n"
        text = text.replace(marker, marker + "\n".join(warm_rows) + "\n", 1)

    STATE_PATH.write_text(text, encoding="utf-8")


def run() -> int:
    pending = read_signals(type_="lead", unprocessed_only=True)
    operator = get_operator_name()

    actioned = 0
    skipped = 0
    hot_count = 0
    hot_state_rows: list[str] = []
    warm_state_rows: list[str] = []

    for signal in pending:
        result = _score_lead(signal)
        name = signal.get("name", "Unknown Lead")
        company = signal.get("company", "Unknown Company")
        source = signal.get("source", "unknown")
        now = datetime.datetime.now()

        if result["tier"] == "COLD":
            mark_signal_linked(signal["_path"], "cold-log-only")
            skipped += 1
            print(f"[lead-qualify] {name}@{company}: COLD ({result['total']}) — logged only, no draft")
            continue

        draft = _draft_outreach(signal, result, name, company, operator)
        tier_dir = DRAFTS_DIR / result["tier"]
        tier_dir.mkdir(parents=True, exist_ok=True)
        draft_path = tier_dir / f"{now.strftime('%Y-%m-%d')}-{_slugify(name)}-{_slugify(company)}.md"
        draft_path.write_text(draft, encoding="utf-8")

        task_path = write_task(
            domain="lead-qualify",
            client=signal.get("business", "pipeline"),
            priority="high" if result["tier"] == "HOT" else "medium",
            task_summary=f"Review + send outreach to {name} @ {company} (score {result['total']}/100, {result['tier']})",
            context=(
                f"Auto-scored from signal `{signal['_path'].name}` (source: {source}). "
                f"Draft at `{draft_path.relative_to(DOMAIN_ROOT.parent.parent).as_posix()}`. "
                f"NEVER send without {operator}'s explicit approval."
            ),
            acceptance_criteria=[
                f"{operator} has reviewed the scoring and the draft opener",
                f"{operator} approves, edits, or discards the draft",
                f"If approved, message sent manually by {operator} — this task does not send anything",
            ],
            linked_signal=signal["_path"].name,
            slug=f"{name}-{company}",
        )
        mark_signal_linked(signal["_path"], task_path.name)
        actioned += 1

        telegram_status = "not attempted (not HOT)"
        if result["tier"] == "HOT":
            hot_count += 1
            alert_text = (
                f"🔥 HOT LEAD: {name} @ {company} | Score: {result['total']}/100 | "
                f"Source: {source} | Message: {_extract_summary(signal['_body'])[:50]}"
            )
            try:
                send_message(alert_text)
                telegram_status = "DELIVERED"
                print(f"[lead-qualify] Telegram HOT alert delivered for {name}@{company}")
            except (TelegramConfigError, requests.RequestException) as e:
                telegram_status = f"FAILED — {e}"
                print(f"[lead-qualify] Telegram HOT alert FAILED for {name}@{company}: {e}")

            hot_state_rows.append(
                f"| {now.strftime('%Y-%m-%d')} | {name} | {company} | {result['total']} | "
                f"{telegram_status} | {draft_path.name} | draft-ready |"
            )
        else:
            warm_state_rows.append(
                f"| {name} | {company} | — | {source} | {result['total']} | draft-ready | "
                f"{draft_path.name} | {now.strftime('%Y-%m-%d')} | auto-scored |"
            )

        print(f"[lead-qualify] {name}@{company}: {result['tier']} ({result['total']}) "
              f"-> draft '{draft_path.name}', task '{task_path.name}', telegram: {telegram_status}")

    _update_state(hot_state_rows, warm_state_rows, hot_count, len(warm_state_rows))

    summary = (
        f"Scored {len(pending)} pending lead signal(s) from root bus, "
        f"{hot_count} HOT, {len(warm_state_rows)} WARM, {skipped} COLD"
    )
    append_root_log(
        "lead-qualify", summary, actioned, skipped,
        "Re-run picks up any new signals; command-chase not yet wired as a real upstream source",
    )
    print(f"[lead-qualify] {summary}")

    return 0