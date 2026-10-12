---
title: "Creative Brief Prompt"
author: "Mohamed Omar"
category: "content"
type: "prompt"
level: "intermediate"
works_with: "Claude Code, ChatGPT, Gemini, any LLM"
language: "Bilingual"
last_verified: "2026-10-12"
hook: "Turn a winning ad angle into a content brief in 60 seconds"
email_subject: "The creative brief prompt that turns ads into content"
short_pitch: "Paste a winning ad's data → get a structured brief with angle, format, hook, and distribution plan."
---

# Creative Brief Prompt

> Takes a winning ad angle and turns it into a content brief with specific formats, hooks, and distribution recommendations.

## The Prompt

```
You are a senior content strategist for a MENA-focused marketing agency. I will give you a winning ad angle (campaign name, CTR, clicks, conversions, and the ad copy/creative concept).

Create a content brief with:

1. ANGLE EXPANSION
- What's the core insight this ad proved? (one sentence)
- What organic content could serve the same search/audience intent?
- What's the content gap this ad is filling that organic content isn't?

2. FORMAT RECOMMENDATIONS (pick 2-3, justify each)
- Blog post: when the topic needs depth
- Social carousel: when the insight is visual/comparison
- Short-form video: when the hook is emotional/urgent
- Landing page section: when the angle is a value prop

3. HOOKS (3 options, platform-specific)
- Instagram: visual-first, ingredient/angle in the first frame
- TikTok: pattern-interrupt in first 3 seconds
- Blog: SEO-optimized headline with the insight front-loaded

4. DISTRIBUTION PLAN
- Where does this content live? (blog, social, email)
- When should it publish? (day of week, time of day for this market)
- How does it connect to the paid campaign? (retargeting, lookalike seed)

5. VOICE NOTES
- Pull from the client's STRATEGY.md voice rules
- If no voice rules exist, state assumptions and flag for review

RULES:
- Arabic-first for social, bilingual for blog
- Every recommendation has a reason tied to the ad's performance data
- Don't recommend 10 formats — pick the 2-3 with the highest leverage
- If the ad angle is thin (one insight, not a pattern), say so
```

## How to use

1. Find a winning ad in your account (CTR > 5%, or top performer by conversions)
2. Paste the prompt + the ad's data (campaign name, metrics, creative concept)
3. The LLM produces a structured brief
4. Review and adjust for the client's voice

## Honest limits

- This prompt produces a draft brief, not a final one. Always review before sharing with the client.
- The Foundry's `foundry creative hooks` command does part of this deterministically (angle extraction from signals). Use the prompt when you need the full brief with distribution plan.
- The LLM may hallucinate platform-specific best practices. Verify TikTok/Instagram format recommendations against current platform guidelines.

---

*Part of the Growth Architect Foundry. For automated briefs from live ad data, run the `content-engine` loop.*