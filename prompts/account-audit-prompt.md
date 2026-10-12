---
title: "Account Audit Prompt"
author: "Mohamed Omar"
category: "paid-ads"
type: "prompt"
level: "intermediate"
works_with: "Claude Code, ChatGPT, Gemini, any LLM"
language: "Bilingual"
last_verified: "2026-10-12"
hook: "Paste this prompt + your ad account data → get a scored audit in 30 seconds"
email_subject: "The 30-second ad account audit prompt"
short_pitch: "Paste your last 30 days of ad data. Get a 0-100 score, ranked fixes, and a 30-day plan. Works for Meta, Google, TikTok."
---

# Account Audit Prompt

> Paste this into any LLM along with your last 30 days of ad data. It produces a structured audit with scores, ranked fixes, and a plan.

## The Prompt

```
You are a senior performance marketer auditing a paid advertising account. I will provide the last 30 days of campaign data.

AUDIT DIMENSIONS (score each 0-100):

1. STRUCTURE (20%)
- Campaign naming convention: consistent? scannable?
- Campaign granularity: one objective per campaign? geo split?
- Ad set / ad group logic: audience overlap? enough conversion volume per ad set?

2. WASTE (25%)
- Search terms: irrelevant queries eating budget?
- Placements: automatic placements pulling into low-quality inventory?
- Frequency: >4 on any campaign? creative fatigue?
- Overlap: same audience targeted by multiple campaigns?

3. CREATIVE (20%)
- Hook quality: does the first line stop the scroll?
- Angle diversity: are all ads saying the same thing?
- Format match: right format for each platform?
- Test structure: is there a structured test plan?

4. TRACKING (15%)
- Conversion events: are they set up correctly?
- Attribution: which model? consistent across platforms?
- Pixel/CAPI: is server-side tracking active?

5. ECONOMICS (20%)
- CPA vs target: above or below? by how much?
- ROAS: sustainable? improving or declining?
- Budget allocation: funnel-stage split logical?

OUTPUT FORMAT:
- VERDICT: one line — what's the single biggest problem
- SCORE: weighted total /100 + letter grade (A≥90, B≥80, C≥70, D≥60, F<60)
- DIMENSION TABLE: each dimension score + evidence
- TOP 5 FIXES: ranked by impact, each with a hypothesis
- DO NOT TOUCH: what's working (protect it)
- 30-DAY PLAN: do today / test this week / stop or reduce

RULES:
- Numbers, not adjectives. Show calculations.
- Every finding quotes the specific campaign/element it refers to.
- Mark each finding: confirmed by data or hypothesis — verify with X.
- If the product/offer is the problem, say so. Marketing can't fix a product nobody retains.
- Reply in the same language as the data.
```

## How to use

1. Export your last 30 days of campaign data (Meta Ads Manager / Google Ads / TikTok Ads)
2. Paste the prompt above
3. Paste your data below it
4. The LLM produces a structured audit

## Honest limits

- This is a prompt, not a calculator. CPA/ROAS calculations may be wrong — verify with `foundry economics breakeven` or `foundry economics cod`.
- The LLM doesn't have your client's context (market, season, competitive landscape). Its findings are generic unless you feed it context.
- The Foundry's `foundry account audit` command does the same thing deterministically — use it when you have the engine available.

---

*Part of the Growth Architect Foundry. For deterministic audits, use `foundry account audit --client <t>` instead.*