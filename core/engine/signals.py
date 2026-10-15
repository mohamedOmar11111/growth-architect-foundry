"""growth_engine.signals — tenant-scoped Signal read/write, schema-locked.

Reuses the exact frontmatter schema from architecture.md Section 1 (Signal
Schema), applied inside a tenant's own `signals/` folder instead of root
`signals/` (dual-bus architecture — see projects/growth-engine/SEED-STATE.md).
The `<business>` filename prefix is dropped since the tenant folder already
scopes it, but the `business:` field is kept in frontmatter so a future
cross-tenant aggregator (Phase 4 master dashboard) can identify origin without
inferring it from a file path.

Any loop can write a signal. Any loop can read them. A signal is NOT a task —
writing one does not queue work by itself; a consuming loop decides whether to
turn it into a task (see tasks.py).
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Any

from envfile import yaml

from tenant import TenantContext

VALID_SOURCES = {"gmail", "whatsapp", "internal", "client-report", "ads-platform", "manual"}
VALID_TYPES = {
    "client-friction", "client-request", "bug", "lead", "idea", "risk",
    "competitor-intel", "performance-alert", "content-idea", "unanswered-message",
}
VALID_PRIORITIES = {"high", "medium", "low"}


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60]


def write_signal(
    tenant: TenantContext,
    *,
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
    """Writes one signal file, schema-validated before touching disk."""
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
        "business": tenant.name.lower(),
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

    filename = f"{now.strftime('%Y-%m-%d')}-{_slugify(slug)}.md"
    path = tenant.signals_dir / filename
    # Avoid clobbering a same-day same-slug signal from an earlier run today.
    n = 2
    while path.exists():
        path = tenant.signals_dir / f"{now.strftime('%Y-%m-%d')}-{_slugify(slug)}-{n}.md"
        n += 1
    path.write_text(content, encoding="utf-8")
    return path


def _parse_signal(path: Path) -> dict[str, Any] | None:
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


def read_signals(
    tenant: TenantContext,
    *,
    type_: str | None = None,
    unprocessed_only: bool = True,
) -> list[dict[str, Any]]:
    """Reads signals from this tenant's own signals/ folder only — never
    reaches into root signals/ or another tenant's folder."""
    results: list[dict[str, Any]] = []
    for path in sorted(tenant.signals_dir.glob("*.md")):
        parsed = _parse_signal(path)
        if parsed is None:
            continue
        if type_ is not None and parsed.get("type") != type_:
            continue
        if unprocessed_only and parsed.get("linked-task", "none") != "none":
            continue
        results.append(parsed)
    return results


def mark_signal_linked(signal_path: Path, task_filename: str) -> None:
    """Sets linked-task on a signal so it isn't reprocessed next run —
    the idempotency mechanism for the whole dual-bus handoff."""
    text = signal_path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    frontmatter = yaml.safe_load(parts[1]) or {}
    frontmatter["linked-task"] = task_filename
    new_content = "---\n" + yaml.safe_dump(frontmatter, sort_keys=False) + "---" + parts[2]
    signal_path.write_text(new_content, encoding="utf-8")
