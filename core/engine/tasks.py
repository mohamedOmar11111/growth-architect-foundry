"""growth_engine.tasks — tenant-scoped Task write, schema-locked.

Reuses the exact frontmatter schema from architecture.md Section 2 (Task
Schema), applied inside a tenant's own `tasks/` folder. Tasks are created FROM
signals (or directly by the operator) and consumed by the relevant loop or by
the operator themself. Never auto-executed — `status: open` + `owner: agent`
means "drafted, needs review," not "done."
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

import yaml

from tenant import TenantContext

VALID_PRIORITIES = {"high", "medium", "low"}
VALID_OWNERS = {"agent", "operator"}


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60]


def write_task(
    tenant: TenantContext,
    *,
    domain: str,
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
    if owner not in VALID_OWNERS:
        raise ValueError(f"Invalid owner '{owner}'. Must be one of {VALID_OWNERS}")
    if len(acceptance_criteria) < 2:
        raise ValueError("Task needs at least 2 acceptance criteria (schema checklist).")

    now = datetime.datetime.now()
    frontmatter = {
        "date": now.strftime("%Y-%m-%d"),
        "domain": domain,
        "client": tenant.name,
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

    filename = f"{now.strftime('%Y-%m-%d')}-{domain}-{_slugify(slug)}.md"
    path = tenant.tasks_dir / filename
    n = 2
    while path.exists():
        path = tenant.tasks_dir / f"{now.strftime('%Y-%m-%d')}-{domain}-{_slugify(slug)}-{n}.md"
        n += 1
    path.write_text(content, encoding="utf-8")
    return path
