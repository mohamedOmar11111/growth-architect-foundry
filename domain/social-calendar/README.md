# Loop Contract: social-calendar

## Goal
Take content-engine's finished draft briefs and decide WHEN/WHERE they get
posted — platform allocation + scheduling, not copywriting. Does not read
raw signals directly (see social_calendar.py's docstring for why: it would
race content-engine for the same signal files).

## Inputs
- `02_Content/*brief*.md` (written by content-engine, not yet scheduled)
- Tenant's `STRATEGY.md` — AVOID/PREFER platform directives

## Outputs
- `02_Content/calendar/content_calendar.md` — running table, one row per
  scheduled item, all `DRAFT` status
- One task per scheduled item (domain: social-calendar), pointing to the
  matching platform agent in `01_Context_Vault/Agents/marketing/` for the
  actual copy/script
- Run summary in `log.md`

## Verifier Checklist
- [ ] Platform allocation respects tenant STRATEGY.md AVOID directives
- [ ] Cadence is balanced (no platform starved while another gets spammed)
- [ ] No auto-posting performed — every entry is DRAFT pending approval

## Escalation
- Escalate to the operator via `signals/` if every platform is under an
  AVOID directive (unusual tenant config, needs a human decision).
