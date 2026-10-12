"""growth_engine.loops.content_engine — consumes content-idea Signals.

Phase 2 proof: this is the first real signal handoff in Growth Engine. Reads
unprocessed `type: content-idea` signals from the tenant's own signals/
folder (written by ad_intel.py), drafts a content brief into the tenant's
02_Content/, writes a Task (schema-locked, status: open, owner: agent — never
auto-published), and marks the signal `linked-task` so it isn't reprocessed.

Zero tenant-specific values in the logic itself — everything (audience notes,
brand voice) is pulled from TenantContext.strategy_md / claude_md, not
hardcoded per business.
"""

from __future__ import annotations

import datetime
import re

from tenant import TenantContext
from signals import read_signals, mark_signal_linked
from tasks import write_task
from utils import append_log


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def _extract_section(body: str, header: str, default: str) -> str:
    if header not in body:
        return default
    after = body.split(header, 1)[1]
    return after.split("##", 1)[0].strip()


def _extract_summary(signal: dict) -> str:
    """Signal frontmatter has no 'summary' key — the summary lives in the
    body under '## Summary'. Pulled out once here so brief + task use the
    same real text instead of each guessing independently."""
    return _extract_section(signal["_body"], "## Summary", "Content opportunity from ad-intel")


def _draft_brief(tenant: TenantContext, signal: dict, summary: str) -> tuple[str, str]:
    """Builds a content brief from a signal's own data — no invented
    specifics beyond what the signal already contains. Returns
    (filename, content)."""
    now = datetime.datetime.now()
    operator = tenant.get("OPERATOR_NAME", "the operator")
    detail = _extract_section(signal["_body"], "## Detail", signal["_body"])
    ad_intel_suggestion = _extract_section(
        signal["_body"], "## Suggested Action", "(none given)"
    )

    has_strategy = bool(tenant.strategy_md.strip())
    voice_note = (
        "Pull tone/voice constraints from this tenant's STRATEGY.md/CLAUDE.md "
        "before writing final copy — do not freestyle voice."
        if has_strategy else
        f"No STRATEGY.md content loaded for voice guidance — confirm brand "
        f"voice with {operator} before publishing."
    )

    content = f"""# Content Brief (DRAFT) — {now.strftime('%Y-%m-%d')}

> Auto-drafted by growth_engine content-engine loop from signal
> `{signal['_path'].name}`. NOT reviewed, NOT approved, NOT published.
> {operator} must review before this becomes real content.

## Source Signal
{summary}

## Why This Brief Exists
{detail}

## What ad-intel Suggested
{ad_intel_suggestion}

## Suggested Angle
Expand the winning ad angle above into an organic piece (blog post, social
carousel, or landing-page section) targeting the same search/audience intent
that's already converting in paid — the goal is to earn some of that traffic
organically instead of paying for all of it.

## Voice Note
{voice_note}

## Next Step
{operator} reviews this brief, picks a format (blog / social / landing section),
and either approves for drafting or discards.
"""
    filename = f"{now.strftime('%Y-%m-%d')}-{_slugify(summary)[:50]}-brief.md"
    return filename, content


def run(tenant: TenantContext) -> int:
    content_dir = tenant.root / "02_Content"
    content_dir.mkdir(parents=True, exist_ok=True)
    operator = tenant.get("OPERATOR_NAME", "the operator")

    pending = read_signals(tenant, type_="content-idea", unprocessed_only=True)

    processed = 0
    last_brief_path = None
    for signal in pending:
        summary = _extract_summary(signal)
        filename, brief = _draft_brief(tenant, signal, summary)
        brief_path = content_dir / filename
        brief_path.write_text(brief, encoding="utf-8")

        task_path = write_task(
            tenant,
            domain="content-engine",
            priority=signal.get("priority", "medium"),
            task_summary=f"Review and finalize content brief: {summary}",
            context=(
                f"Auto-drafted from signal `{signal['_path'].name}` "
                f"(written by ad-intel). Draft brief at "
                f"`{brief_path.relative_to(tenant.root).as_posix()}`. "
                f"Needs {operator}'s review before any content is actually "
                "written or published — this task covers review + format "
                "decision, not final copy."
            ),
            acceptance_criteria=[
                f"{operator} has reviewed the draft brief",
                "Format decided (blog / social / landing section) or brief discarded",
                "If approved, final content drafted separately — this task does not include final copy",
            ],
            linked_signal=signal["_path"].name,
            slug=summary,
        )

        mark_signal_linked(signal["_path"], task_path.name)
        processed += 1
        last_brief_path = brief_path
        print(f"[{tenant.name}] content-engine: signal '{signal['_path'].name}' "
              f"-> brief '{filename}' -> task '{task_path.name}'")

    print(f"[{tenant.name}] content-engine: {processed} signal(s) processed, "
          f"{len(pending) - processed} skipped")

    if processed and last_brief_path is not None:
        append_log(
            tenant.name, "content-engine",
            f"Processed {processed} content-idea signal(s) from ad-intel into "
            f"draft brief(s) + task(s), all pending {operator} review",
            last_brief_path,
        )

    return 0
