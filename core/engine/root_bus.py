"""growth_engine.root_bus — Root Bus signal/task/log I/O.

Distinct from signals.py/tasks.py (tenant bus, one folder per tenant). This
module implements architecture.md's ORIGINAL schema exactly: a single shared
`signals/`/`tasks/` at HQ root, with `business:`/`client:` as a field inside
each file rather than a folder boundary. This is the operator's personal
cross-business queue (command-chase, lead-qualify) — per the Dual-Bus ruling,
it stays separate from tenant-scoped loops (ad-intel, content-engine).

Filename convention (architecture.md Section 1/2, root only):
    signals/YYYY-MM-DD-<business>-<slug>.md
    tasks/YYYY-MM-DD-<domain>-<slug>.md
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values

HQ_ROOT = Path(__file__).resolve().parents[2]
SIGNALS_DIR = HQ_ROOT / "signals"
TASKS_DIR = HQ_ROOT / "tasks"
LOG_PATH = HQ_ROOT / "log.md"
CLIENTS_ROOT = HQ_ROOT / "02_Active_Clients"

VALID_SOURCES = {"gmail", "whatsapp", "internal", "client-report", "ads-platform", "manual"}
VALID_LOOPS = {
    "command-chase", "grow-edge-sessions", "ad-intel", "meta-ads",
    "content-engine", "social-calendar", "creative-brief", "lead-qualify",
    "manual",
}
VALID_TYPES = {
    "client-friction", "client-request", "bug", "lead", "idea", "risk",
    "competitor-intel", "performance-alert", "content-idea", "unanswered-message",
}
VALID_PRIORITIES = {"high", "medium", "low"}

# Two universal slugs every deployment has (the operator's own root context and
# the unqualified sales pipeline), plus whatever tenant folders actually exist
# under 02_Active_Clients/ right now. Deliberately NOT a hardcoded roster of
# one operator's specific clients — that was the original bug here: a fixed
# whitelist of one person's business names meant no other operator's business
# could ever write a root-bus signal. Derived live so it self-maintains as
# tenants are added/removed, same as tenant.py already does for the tenant bus.
_UNIVERSAL_BUSINESSES = {"hq", "pipeline"}


def _valid_businesses() -> set[str]:
    tenant_slugs = set()
    if CLIENTS_ROOT.is_dir():
        tenant_slugs = {_slugify(p.name) for p in CLIENTS_ROOT.iterdir() if p.is_dir()}
    return _UNIVERSAL_BUSINESSES | tenant_slugs


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def get_operator_name(default: str = "the operator") -> str:
    """Root-bus loops have no TenantContext to read OPERATOR_NAME from — this
    is the equivalent for root .env. Same fallback default as
    tenant.get('OPERATOR_NAME', ...) so generated text reads the same either
    way when a buyer hasn't filled in their name yet."""
    values = dotenv_values(HQ_ROOT / ".env")
    return values.get("OPERATOR_NAME") or default


def write_signal(
    *,
    business: str,
    loop: str,
    source: str,
    type_: str,
    priority: str,
    action_needed: bool,
    summary: str,
    detail: str,
    suggested_action: str,
    slug: str,
) -> Path:
    """Writes one root-bus signal — schema-validated exactly per
    architecture.md Section 1, including the business-slug whitelist."""
    valid_businesses = _valid_businesses()
    if business not in valid_businesses:
        raise ValueError(
            f"Invalid business '{business}'. Must be one of {valid_businesses} "
            f"— add a folder under {CLIENTS_ROOT} to register a new tenant."
        )
    if loop not in VALID_LOOPS:
        raise ValueError(f"Invalid loop '{loop}'. Must be one of {VALID_LOOPS}")
    if source not in VALID_SOURCES:
        raise ValueError(f"Invalid source '{source}'. Must be one of {VALID_SOURCES}")
    if type_ not in VALID_TYPES:
        raise ValueError(f"Invalid type '{type_}'. Must be one of {VALID_TYPES}")
    if priority not in VALID_PRIORITIES:
        raise ValueError(f"Invalid priority '{priority}'. Must be one of {VALID_PRIORITIES}")

    now = datetime.datetime.now()
    frontmatter = {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "source": source,
        "business": business,
        "loop": loop,
        "type": type_,
        "priority": priority,
        "action-needed": "yes" if action_needed else "no",
        "linked-task": "none",
    }
    body = (
        f"## Summary\n{summary}\n\n"
        f"## Detail\n{detail}\n\n"
        f"## Suggested Action\n{suggested_action}\n"
    )
    content = "---\n" + yaml.safe_dump(frontmatter, sort_keys=False) + "---\n\n" + body

    SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{now.strftime('%Y-%m-%d')}-{business}-{_slugify(slug)}.md"
    path = SIGNALS_DIR / filename
    n = 2
    while path.exists():
        path = SIGNALS_DIR / f"{now.strftime('%Y-%m-%d')}-{business}-{_slugify(slug)}-{n}.md"
        n += 1
    path.write_text(content, encoding="utf-8")
    return path


def _parse_frontmatter(path: Path) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    frontmatter = yaml.safe_load(parts[1]) or {}
    frontmatter["_path"] = path
    frontmatter["_body"] = parts[2].strip()
    return frontmatter


def read_signals(*, type_: str | None = None, unprocessed_only: bool = True) -> list[dict[str, Any]]:
    """Reads across ALL businesses in root signals/ — this is the whole point
    of the root bus, unlike the tenant bus which is folder-isolated."""
    results: list[dict[str, Any]] = []
    if not SIGNALS_DIR.is_dir():
        return results
    for path in sorted(SIGNALS_DIR.glob("*.md")):
        if path.name == "README.md":
            continue
        parsed = _parse_frontmatter(path)
        if parsed is None:
            continue
        if type_ is not None and parsed.get("type") != type_:
            continue
        if unprocessed_only and parsed.get("linked-task", "none") != "none":
            continue
        results.append(parsed)
    return results


def mark_signal_linked(signal_path: Path, task_filename: str) -> None:
    text = signal_path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    frontmatter = yaml.safe_load(parts[1]) or {}
    frontmatter["linked-task"] = task_filename
    new_content = "---\n" + yaml.safe_dump(frontmatter, sort_keys=False) + "---" + parts[2]
    signal_path.write_text(new_content, encoding="utf-8")


def write_task(
    *,
    domain: str,
    client: str,
    priority: str,
    task_summary: str,
    context: str,
    acceptance_criteria: list[str],
    linked_signal: str,
    slug: str,
    owner: str = "agent",
) -> Path:
    if priority not in VALID_PRIORITIES:
        raise ValueError(f"Invalid priority '{priority}'. Must be one of {VALID_PRIORITIES}")
    if owner not in {"agent", "operator"}:
        raise ValueError("owner must be 'agent' or 'operator'")
    if len(acceptance_criteria) < 2:
        raise ValueError("Task needs at least 2 acceptance criteria (schema checklist).")

    now = datetime.datetime.now()
    frontmatter = {
        "date": now.strftime("%Y-%m-%d"),
        "domain": domain,
        "client": client,
        "priority": priority,
        "status": "open",
        "owner": owner,
        "attempts": 0,
        "max-attempts": 3,
        "deadline": "none",
        "linked-signal": linked_signal,
    }
    criteria_lines = "\n".join(f"- [ ] {c}" for c in acceptance_criteria)
    body = (
        f"## Task\n{task_summary}\n\n"
        f"## Context\n{context}\n\n"
        f"## Acceptance Criteria\n{criteria_lines}\n\n"
        f"## Verifier Checklist\n"
        f"- [ ] Output reviewed by separate verifier agent\n"
        f"- [ ] Output matches acceptance criteria\n"
        f"- [ ] No auto-send, auto-publish, or auto-commit performed\n"
        f"- [ ] Run logged to log.md\n\n"
        f"## Outcome\n(Filled in when status = done or cancelled)\n"
    )
    content = "---\n" + yaml.safe_dump(frontmatter, sort_keys=False) + "---\n\n" + body

    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{now.strftime('%Y-%m-%d')}-{domain}-{_slugify(slug)}.md"
    path = TASKS_DIR / filename
    n = 2
    while path.exists():
        path = TASKS_DIR / f"{now.strftime('%Y-%m-%d')}-{domain}-{_slugify(slug)}-{n}.md"
        n += 1
    path.write_text(content, encoding="utf-8")
    return path


def append_root_log(loop: str, summary: str, actioned: int, skipped: int, next_note: str) -> None:
    """Appends exactly architecture.md Section 3's one-line format — the root
    bus's own log convention, distinct from the tenant-loop log style used by
    growth_engine/utils.append_log."""
    now = datetime.datetime.now()
    entry = (
        f"[{now.strftime('%Y-%m-%d %H:%M')}] | {loop} | {summary} | "
        f"Items: {actioned} actioned, {skipped} skipped | Next: {next_note}\n"
    )
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(entry)