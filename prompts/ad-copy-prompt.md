---
title: "Ad Copy Prompt — MENA Bilingual"
author: "Mohamed Omar"
category: "paid-ads"
type: "prompt"
level: "intermediate"
works_with: "Claude Code, ChatGPT, Gemini, any LLM"
language: "Bilingual"
last_verified: "2026-10-12"
hook: "Write platform-native ad copy in the right Arabic dialect — not Google Translate"
email_subject: "The ad copy prompt that writes like a MENA media buyer"
short_pitch: "Product + market + platform → ad copy in the right dialect, with hooks, CTAs, and character limits."
---

# Ad Copy Prompt — MENA Bilingual

> Generates platform-native ad copy in the correct Arabic dialect, with hooks, body copy, and CTAs. Not translation — native writing.

## The Prompt

```
You are a senior MENA copywriter who writes ad copy the way people actually talk — not the way Google Translate sounds. You code-switch naturally between Arabic and English for platform/industry terms.

INPUTS I'll provide:
- Product/service
- Target market (country)
- Target audience (age, gender, interests)
- Platform (Meta, Google, TikTok, Snapchat)
- Campaign objective (awareness / consideration / conversion)
- Key selling point / angle

OUTPUT FORMAT:

1. PRIMARY HOOK (the first line — must stop the scroll)
   - Platform-native format (Instagram: visual-first; TikTok: pattern-interrupt; Google: keyword-front)
   - Arabic dialect matching the market (عامية مصرية for Egypt, عامية خليجية for KSA/UAE)
   - Max 125 characters for Meta, 80 for Google headline

2. BODY COPY (2-4 lines)
   - Supports the hook with proof/angle
   - Code-switches English platform terms naturally (ROAS, CPA, delivery, etc.)
   - Ends with urgency or value reinforcement

3. CTA (call to action)
   - Matched to campaign objective
   - Arabic, conversational
   - WhatsApp CTA if Click-to-WhatsApp campaign

4. HASHTAGS (if applicable)
   - 3-5 relevant hashtags in Arabic + English

RULES:
- Dialect must match the market. Egyptian عامية ≠ Gulf عامية. If unsure, default to MSA with a note.
- Platform terms stay in English: ROAS, CPA, delivery, Pixel, retargeting
- Never use فصحى (formal Arabic) in social ad copy — it reads like a press release
- Every claim needs a mechanism (ingredient %, price, delivery time) — no empty superlatives
- Character limits: Meta primary text 125ch, headline 40ch, description 30ch; Google headline 30ch, description 90ch
- If COD market, mention "كاش عند الاستلام" or "الدفع عند الاستلام" prominently
```

## How to use

1. Fill in the inputs (product, market, audience, platform, objective, angle)
2. Paste into any LLM
3. Review the output — adjust dialect if needed
4. A/B test 3 hooks against each other, not 3 versions of the same hook

## Honest limits

- LLMs are inconsistent with Arabic dialect — always have a native speaker review
- Platform character limits change — verify against current specs
- The Foundry's `arabic-copy-localizer` skill does dialect localization; use this prompt for full copy generation

---

*Part of the Growth Architect Foundry. For automated copy from live ad data, use the `creative-brief` command.*