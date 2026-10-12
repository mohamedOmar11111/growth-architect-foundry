---
name: social-media-ops
description: Turn a content-idea signal into platform-specific social posts using the SOCIAL_MEDIA squad. Use when the user says "post this", "social media plan", "which platform", "turn this into a tweet/LinkedIn post/reel", or when content-engine has produced a brief that needs distributing.
---

# Social Media Ops

Operating procedure for turning one piece of content into the right
platform-specific output(s) — not a generic social media guide, this is
specifically how it plugs into this kernel's signal/task/agent structure.

## Step 1 — Find the source
Most social content starts as one of two things:
- A `content-idea` signal in the tenant's `signals/` folder (written by
  `ad_intel.py` when a paid angle is converting well — see
  `core/engine/loops/ad_intel.py`)
- A finished draft brief in the tenant's `02_Content/` folder (written by
  `content_engine.py` from that signal)

If neither exists yet and the user just has a raw idea, that's fine — skip
to Step 2 with the raw idea as the source.

## Step 2 — Allocate before you write
Read `01_Context_Vault/Agents/marketing/marketing-social-media-strategist.md`
and apply its Decision Framework:
1. Who is this actually for? (B2B → LinkedIn-first, consumer/visual →
   Instagram/TikTok-first, real-time/news → Twitter/Reddit-first)
2. Check the tenant's `STRATEGY.md` for any platform AVOID/PREFER
   directives — these override default judgment.
3. Check platform cadence (recent `log.md`/tenant report entries) — don't
   pick a platform purely on content-fit if another platform has gone
   silent and needs something scheduled regardless.

Output of this step: a short list of platforms, in order, each with a
one-line format target (thread / carousel / short-form video / post).

## Step 3 — Execute per platform
Hand off to the matching specialist agent for the actual copy/script:

| Platform | Agent file |
|---|---|
| Twitter/X | `01_Context_Vault/Agents/marketing/marketing-twitter-engager.md` |
| LinkedIn | `01_Context_Vault/Agents/marketing/marketing-linkedin-strategist.md` |
| Instagram | `01_Context_Vault/Agents/marketing/marketing-instagram-curator.md` |
| TikTok | `01_Context_Vault/Agents/marketing/marketing-tiktok-strategist.md` |
| Reddit | `01_Context_Vault/Agents/marketing/marketing-reddit-community-builder.md` |

Each agent file's own Critical Rules / Content Strategy Framework section
governs the actual copywriting — don't freelance past what that file says
platform-appropriate, especially the "no engagement bait" / "native-first"
type rules (violating those tanks organic reach, not just looks bad).

Pull brand voice from the tenant's `CLAUDE.md`/`STRATEGY.md` before writing
any copy — same rule every other loop in this kernel follows (see
`content_engine.py`'s voice-note pattern).

## Step 4 — Draft, never publish
Write the output as a draft file — under the tenant's `02_Content/` folder
if it's tied to an existing brief, or `domain/content-engine/drafts/` via
`agent_shim.py` if you're running standalone (see that script's docstring).
**Never** claim to have posted anything. Nothing in this kernel auto-
publishes to a live social account — that's a hard rule
(`AGENTS.md` Section 9), not a missing feature.

If a task needs to be tracked (multi-platform rollout, waiting on
approval), write it via `write_task`/`write_signal` per `architecture.md`'s
schema — don't invent an ad-hoc format.

## Step 5 — Watch for lead signals
If a comment/engager on a published post (posted manually by the operator,
after their own review) looks like it matches the tenant's ICP — especially
on LinkedIn — write a `type: lead` signal per `architecture.md` so
`lead-qualify` picks it up. Don't let a warm inbound signal die in a
comment thread nobody's tracking.

## Step 6 — Cross-pollinate
If a platform's post clearly overperforms (use the tenant's own historical
numbers as the bar, not an industry benchmark), write a `content-idea`
signal back so `content-engine`/this skill considers adapting it for the
other platforms — same loop pattern `ad_intel.py` already uses for paid →
organic handoff.
