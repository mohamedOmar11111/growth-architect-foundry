"""growth_engine.commands.state — read-only snapshot of one tenant's operational state.

The command layer judges what has already happened: signals, tasks, run
history, captured ad reports, config completeness. Nothing here writes, and
nothing here reaches outside the tenant folder plus the root log.md — same
containment rule as every loop.

Reading lives here rather than in tasks.py/signals.py because the loop layer
owns writing and the command layer owns judging: the two have different
lifecycles, and keeping the snapshot format in one place stops each command
from re-parsing frontmatter its own way.
"""

from __future__ import annotations

import datetime
import math
import re
from pathlib import Path
from typing import Any

from envfile import load_frontmatter
from tenant import TenantContext
from signals import read_signals
from utils import LOG_PATH

_LOG_ENTRY_RE = re.compile(
    r"^## (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) — (.+?) / (.+?) \(Growth Engine\)",
    re.MULTILINE,
)
_SECTION_HEADER_RE = re.compile(r"^#{2,3}\s+(.+?)\s*$", re.MULTILINE)

# Values that only look configured — copied straight from .env.example.
_PLACEHOLDER_MARKERS = ("your_", "_here", "your name", "placeholder")

# Optional, but its absence caps how useful any media advice can be
# (rule: "advice without a target is content, not media buying").
TARGET_CPA_KEY = "TARGET_CPA"


def read_tasks(tenant: TenantContext) -> list[dict[str, Any]]:
    """Every task file in this tenant's tasks/ folder, frontmatter + body.

    Unlike signals, tasks are read in ALL states — an audit that only saw
    open items couldn't compute a closure rate."""
    results: list[dict[str, Any]] = []
    for path in sorted(tenant.tasks_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        parts = text.split("---", 2)
        if len(parts) < 3:
            continue
        meta = load_frontmatter(parts[1])
        meta["_path"] = path
        meta["_body"] = parts[2].strip()
        results.append(meta)
    return results


def read_log_entries(tenant_name: str) -> list[dict[str, Any]]:
    """Root log.md entries for one tenant, oldest first. The log is the
    episodic record of what actually ran — the only proof of cadence."""
    if not LOG_PATH.exists():
        return []
    entries: list[dict[str, Any]] = []
    for match in _LOG_ENTRY_RE.finditer(LOG_PATH.read_text(encoding="utf-8")):
        when, entry_tenant, loop = match.groups()
        if entry_tenant != tenant_name:
            continue
        entries.append({
            "when": datetime.datetime.strptime(when, "%Y-%m-%d %H:%M"),
            "loop": loop,
        })
    return entries


def _to_number(cell: str) -> float | None:
    cleaned = cell.replace(",", "").replace("%", "").strip()
    if cleaned in ("—", "-", ""):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def read_ad_report(tenant: TenantContext) -> dict[str, Any] | None:
    """The most recent ad report captured for this tenant (from ad-intel,
    meta-ads, or live pull), with its campaign table parsed into numbers.

    Returns None when no report exists yet — commands must say "no paid data
    captured" rather than invent figures."""
    if not tenant.reports_dir.exists():
        return None
    reports = sorted(
        [*tenant.reports_dir.glob("*-ad-intel-report.md"),
         *tenant.reports_dir.glob("*-meta-ads-report.md"),
         *tenant.reports_dir.glob("*-live-pull.md")],
        key=lambda p: p.name,
    )
    if not reports:
        return None

    path = reports[-1]
    is_live_pull = path.name.endswith("-live-pull.md")
    rows: list[dict[str, Any]] = []
    text = path.read_text(encoding="utf-8")
    scope = next((ln for ln in text.splitlines() if ln.startswith("Scope: imported from")), "")
    currency = re.search(r"currency ([A-Z]{3})\b", scope)
    from_results = "conversions <- `Results`" in text or "conversions <- `النتائج`" in text
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 10 or cells[0] in ("Campaign", "Platform") or set(cells[0]) <= {"-", ":"}:
            continue
        if is_live_pull:
            rows.append({
                "platform": cells[0],
                "name": cells[1],
                "status": cells[2],
                "daily_budget": _to_number(cells[3]),
                "today_spend": None,
                "cost": _to_number(cells[4]),
                "impressions": _to_number(cells[5]),
                "clicks": _to_number(cells[6]),
                "ctr": _to_number(cells[7]),
                "conversions": _to_number(cells[8]),
                "cpa": _to_number(cells[9]),
            })
        else:
            rows.append({
                "name": cells[0],
                "status": cells[1],
                "daily_budget": _to_number(cells[2]),
                "today_spend": _to_number(cells[3]),
                "impressions": _to_number(cells[4]),
                "clicks": _to_number(cells[5]),
                "ctr": _to_number(cells[6]),
                "cost": _to_number(cells[7]),
                "conversions": _to_number(cells[8]),
                "cpa": _to_number(cells[9]),
            })
    if not rows:
        return None

    total_cost = sum(r["cost"] or 0.0 for r in rows)
    total_conversions = sum(r["conversions"] or 0.0 for r in rows)
    return {
        "path": path,
        "source": "csv" if scope else "live",
        "currency": currency.group(1) if currency else None,
        "conversions_from_results": from_results,
        "age_days": _report_age_days(path),
        "rows": rows,
        "totals": {
            "cost": total_cost,
            "conversions": total_conversions,
            "cpa": (total_cost / total_conversions) if total_conversions else None,
        },
    }


def content_artifacts(tenant: TenantContext) -> dict[str, int]:
    content_dir = tenant.root / "02_Content"
    calendar = content_dir / "calendar" / "content_calendar.md"
    return {
        "briefs": len(list(content_dir.glob("*brief*.md"))) if content_dir.exists() else 0,
        "calendar": int(calendar.exists()),
    }


def strategy_headers(strategy_md: str) -> set[str]:
    return {m.group(1).strip().lower() for m in _SECTION_HEADER_RE.finditer(strategy_md)}


def _is_placeholder(value: str | None) -> bool:
    if value is None:
        return True
    lowered = value.strip().lower()
    return not lowered or any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def operator_name(tenant: TenantContext) -> str | None:
    """The real operator name, or None if it's still the .env.example
    placeholder — generated artifacts must never address "Your Name"."""
    value = tenant.get("OPERATOR_NAME")
    return None if _is_placeholder(value) else str(value).strip()


def config_status(env: dict[str, str]) -> dict[str, Any]:
    """Per-integration credential readiness. Distinguishes 'key present' from
    'key actually configured' — a copied .env.example has every key present
    and nothing usable, and reporting it as configured would be a lie the
    first live run would immediately expose."""
    groups = {
        "google-ads": [
            "GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET",
            "GOOGLE_ADS_REFRESH_TOKEN", "GOOGLE_ADS_DEVELOPER_TOKEN",
            "GOOGLE_ADS_CUSTOMER_ID",
        ],
        "meta-ads": ["META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID"],
    }
    status: dict[str, Any] = {
        "groups": {},
        "operator_set": not _is_placeholder(env.get("OPERATOR_NAME")),
        "target_cpa": env.get(TARGET_CPA_KEY),
    }
    for group, keys in groups.items():
        real = [k for k in keys if not _is_placeholder(env.get(k))]
        status["groups"][group] = {
            "configured": len(real),
            "required": len(keys),
            "ready": len(real) == len(keys),
        }
    return status


CSV_MODE_MAX_AGE_DAYS = 30


def _report_age_days(path: Path) -> int:
    """Days since the report's YYYY-MM-DD filename prefix (0 when the name carries no date)."""
    try:
        return (datetime.date.today() - datetime.date.fromisoformat(path.name[:10])).days
    except ValueError:
        return 0


def resolve_target_cpa(tenant: TenantContext, opts: dict | None) -> float | None:
    """--target-cpa wins over TARGET_CPA in the tenant .env; anything unparsable counts as unset."""
    raw = (opts or {}).get("target_cpa") or tenant.env.get(TARGET_CPA_KEY)
    try:
        value = float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None
    return value if value is not None and math.isfinite(value) and value > 0 else None


def collect_snapshot(tenant: TenantContext) -> dict[str, Any]:
    """Everything the command layer needs about one tenant, parsed once."""
    now = datetime.datetime.now()
    signals = read_signals(tenant, unprocessed_only=False)
    unprocessed = [s for s in signals if s.get("linked-task", "none") == "none"]
    tasks = read_tasks(tenant)

    oldest_open_age = 0
    for s in unprocessed:
        try:
            when = datetime.datetime.strptime(str(s.get("date")), "%Y-%m-%d")
        except (TypeError, ValueError):
            continue
        oldest_open_age = max(oldest_open_age, (now - when).days)

    snapshot = {
        "now": now,
        "tenant": tenant,
        "signals": signals,
        "unprocessed": unprocessed,
        "high_unprocessed": [s for s in unprocessed if s.get("priority") == "high"],
        "oldest_open_age_days": oldest_open_age,
        "tasks": tasks,
        "open_tasks": [t for t in tasks if t.get("status") == "open"],
        "done_tasks": [t for t in tasks if t.get("status") == "done"],
        "stuck_tasks": [
            t for t in tasks
            if t.get("status") == "open" and (t.get("attempts") or 0) >= (t.get("max-attempts") or 3)
        ],
        "log_entries": read_log_entries(tenant.name),
        "ad_report": read_ad_report(tenant),
        "content": content_artifacts(tenant),
        "strategy_headers": strategy_headers(tenant.strategy_md),
        "config": config_status(tenant.env),
    }
    ad = snapshot["ad_report"]
    # CSV mode only when the user has NOT connected any ad account and the import is recent.
    snapshot["csv_mode"] = bool(ad and ad["source"] == "csv" and ad["age_days"] <= CSV_MODE_MAX_AGE_DAYS
                                and not any(g["ready"] for g in snapshot["config"]["groups"].values()))
    return snapshot
