"""growth_engine.loops.creative_brief — turns a finished content brief into
structured image + video generation prompts.

DELIBERATE ARCHITECTURAL EXCEPTION, stated explicitly rather than left as
a silent contradiction: every other loop in this kernel (ad_intel,
meta_ads, content_engine, lead_qualify, social_calendar) is pure
deterministic Python — confirmed by grep, documented in agent_shim.py's
own module docstring, previously asserted in this project's own audit
trail as "zero LLM calls anywhere in the kernel." That assertion is no
longer true as of this file. Turning a marketing idea into a genuinely
good image/video prompt is a language-judgment task, not a deterministic
transform — exactly the gap agent_shim.py's provider-calling layer exists
to fill. Rather than inventing a second, parallel way to call an LLM, this
loop imports and reuses agent_shim.py's own resolve_provider() and
provider-call functions directly. One LLM-calling code path in this
kernel, not two.

Consequence worth being explicit about: this loop CANNOT run without a
configured ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY (same
requirement as agent_shim.py) — it fails loud with the same clear error
agent_shim.py already raises if none is set, no silent fallback to a
template. Does NOT call an image/video generation API itself (no
DALL-E/Midjourney/Runway/etc dependency) — deliberately vendor-neutral,
consistent with this kernel's "not locked to one AI vendor" design.
Produces the PROMPT; the operator feeds it into whichever image/video
tool they already use.
"""

from __future__ import annotations

from pathlib import Path

from tenant import TenantContext
from tasks import write_task
from utils import append_log
from agent_shim import resolve_provider, _load_root_env, PROVIDERS, AgentShimError

HQ_ROOT = Path(__file__).resolve().parents[2].parent  # matches lead_qualify.py's DOMAIN_ROOT convention for files under loops/
IMAGE_PROMPT_AGENT = HQ_ROOT / "01_Context_Vault" / "Agents" / "design" / "design-image-prompt-engineer.md"
VISUAL_MARKER = "<!-- visual-brief-generated -->"


def _read_optional(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _pending_briefs(tenant: TenantContext) -> list[Path]:
    content_dir = tenant.root / "02_Content"
    if not content_dir.is_dir():
        return []
    return [
        p for p in sorted(content_dir.glob("*brief*.md"))
        if VISUAL_MARKER not in p.read_text(encoding="utf-8")
        and not p.name.endswith("-visual-brief.md")
    ]


def _build_prompt_request(tenant: TenantContext, brief_text: str, framework: str) -> tuple[str, str]:
    system = (
        f"{framework}\n\n"
        f"---\n"
        f"# Tenant Brand Voice\n{tenant.claude_md}\n\n{tenant.strategy_md}\n\n"
        f"---\n"
        "You are producing image AND video generation prompts for the content "
        "brief below, following the Image Prompt Engineer framework above "
        "exactly (subject/environment/lighting/technical/style layers for the "
        "image prompt). For video, add a short shot-list style concept "
        "(3-5 beats, each with a one-line visual description) suitable for a "
        "short-form platform (TikTok/Reels) — not a full script, just the "
        "visual concept a video editor or a text-to-video tool would need. "
        "Ground every detail in the brief's actual content — no invented "
        "product claims beyond what the brief states."
    )
    user = f"# Source Content Brief\n{brief_text}\n\nProduce the image prompt and video concept now."
    return system, user


def run(tenant: TenantContext) -> int:
    if not IMAGE_PROMPT_AGENT.exists():
        raise AgentShimError(
            f"Missing {IMAGE_PROMPT_AGENT} — this loop depends on that agent "
            "definition for its prompt-engineering framework."
        )

    env = _load_root_env()
    operator = env.get("OPERATOR_NAME", "the operator")
    provider, api_key = resolve_provider(env)
    call_fn = PROVIDERS[provider][1]
    framework = IMAGE_PROMPT_AGENT.read_text(encoding="utf-8")

    briefs = _pending_briefs(tenant)
    processed = 0
    for brief_path in briefs:
        brief_text = brief_path.read_text(encoding="utf-8")
        system, user = _build_prompt_request(tenant, brief_text, framework)
        result = call_fn(api_key, system, user)

        visual_path = brief_path.with_name(brief_path.stem + "-visual-brief.md")
        visual_path.write_text(
            f"# Visual Brief (DRAFT) — generated from `{brief_path.name}`\n\n"
            f"> Auto-drafted by growth_engine creative-brief loop via {provider}. "
            f"NOT reviewed, NOT approved, NOT sent to any image/video generator "
            f"yet. {operator} reviews before using these prompts anywhere.\n\n"
            f"---\n\n{result}\n",
            encoding="utf-8",
        )

        brief_path.write_text(
            brief_text + f"\n{VISUAL_MARKER}\n> Visual brief generated: "
            f"{visual_path.name}\n",
            encoding="utf-8",
        )

        write_task(
            tenant,
            domain="creative-brief",
            priority="medium",
            task_summary=f"Review visual brief and generate assets: {brief_path.stem[:50]}",
            context=(
                f"Auto-drafted image/video prompts at "
                f"`{visual_path.relative_to(tenant.root).as_posix()}` from brief "
                f"`{brief_path.name}`, via {provider}. {operator} reviews the "
                "prompts, then runs them through whichever image/video "
                "generation tool is actually in use (this loop does not call "
                "one — vendor-neutral by design)."
            ),
            acceptance_criteria=[
                f"{operator} has reviewed the generated prompts",
                "Prompts run through an actual image/video tool, or discarded if not usable",
                "This task does not include the generated assets themselves",
            ],
            linked_signal="none",
            slug=f"visual-brief-{brief_path.stem[:40]}",
        )
        processed += 1
        print(f"[{tenant.name}] creative-brief: '{brief_path.name}' -> "
              f"'{visual_path.name}' via {provider}")

    print(f"[{tenant.name}] creative-brief: {processed} brief(s) processed")

    if processed:
        append_log(
            tenant.name, "creative-brief",
            f"Generated {processed} image/video prompt brief(s) via {provider}, "
            f"all pending {operator} review",
            visual_path,
        )

    return 0
