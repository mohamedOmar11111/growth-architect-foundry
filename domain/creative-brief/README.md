# Loop Contract: creative-brief

## Goal
Turn a finished content brief into structured image + video generation
prompts, using the Image Prompt Engineer agent's framework
(`01_Context_Vault/Agents/design/design-image-prompt-engineer.md`).

**This is the one loop in this kernel that calls an LLM** — reuses
agent_shim.py's own provider-calling functions rather than a second
implementation. Requires a configured `ANTHROPIC_API_KEY` /
`OPENAI_API_KEY` / `GEMINI_API_KEY` in the root `.env` — fails loud with
no key configured, same as agent_shim.py.

Does NOT call an image/video generation API (no DALL-E/Midjourney/Runway
dependency) — vendor-neutral by design. Produces the prompt; the operator
runs it through whichever tool they already use.

## Inputs
- `02_Content/*brief*.md` (written by content-engine, not yet visualized)
- Tenant's `CLAUDE.md`/`STRATEGY.md` — brand voice grounding for the prompt

## Outputs
- `02_Content/<brief>-visual-brief.md` — image prompt + short video concept
- One task per visual brief (domain: creative-brief)
- Run summary in `log.md`

## Verifier Checklist
- [ ] Generated prompts are grounded in the actual brief content, no
      invented product claims
- [ ] Operator has reviewed before running any prompt through an actual
      image/video tool
- [ ] No auto-generation of actual image/video assets performed

## Escalation
- Escalate to the operator via `signals/` if no LLM provider key is
  configured — this loop cannot run at all without one.
