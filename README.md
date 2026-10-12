# The Foundry
### The multi-agent growth kernel for agencies — now a Claude Code plugin

[![Kernel-Guard](https://github.com/mohamedOmar11111/growth-architect-foundry/actions/workflows/kernel-guard.yml/badge.svg)](https://github.com/mohamedOmar11111/growth-architect-foundry/actions/workflows/kernel-guard.yml)
[![Code-Quality-Guard](https://github.com/mohamedOmar11111/growth-architect-foundry/actions/workflows/pylint.yml/badge.svg)](https://github.com/mohamedOmar11111/growth-architect-foundry/actions/workflows/pylint.yml)

Every client you take on means rebuilding the same ops stack. The Foundry is
that stack, already built — plug in a client, plug in whichever AI tool you
already pay for, go. **23 deterministic commands**, multi-tenant isolation,
maker/checker safety, Arabic-first output.

---

## Install as a Claude Code Plugin

```
/plugin marketplace add mohamedOmar11111/growth-architect-foundry
/plugin install foundry@growth-architect-foundry
```

Then, in **your own project folder** (this is your workspace: tenants, `log.md`,
signals and tasks live here, never inside the plugin, so updates can't touch
client data):

```
/foundry:doctor              # checks Python + dependencies, prints the fix commands
/foundry:init Acme_Store     # scaffolds 02_Active_Clients/Acme_Store/
/foundry:audit Acme_Store    # 0-100 health score, top fixes, 30-day plan
```

Requirements: Python 3.10+ and `pip install -r requirements.txt` (Google Ads SDK
is optional). Or just talk to Claude: "audit my account" / "راجع حسابي".

Slash commands: `/foundry:init`, `doctor`, `audit`, `diagnose`, `report`, `live`.
The full 23+ command surface is available through the skill.

**Other interfaces:**

| You have | Use |
|---|---|
| Claude Code | Plugin install above |
| Cursor | `.cursor/rules/growth-architect-kernel.mdc` — already wired in |
| Terminal | `python foundry.py account audit --client Aurora_Skincare` (run from your workspace, or set `FOUNDRY_WORKSPACE`) |
| Just an API key | `python core/engine/agent_shim.py content-engine --task "..."` |

### Live ad-account safety

- Failed API calls are reported as **FETCH FAILED** and exit non-zero, never as "no campaigns".
- Writes (`live pause`, `live budget`) need `--confirm`, are refused if any platform fetch failed,
  and budget changes are capped at **20% cumulative per campaign per 7 days** (ledger in the tenant's `04_Reports/`).
- Agency accounts: set `GOOGLE_ADS_LOGIN_CUSTOMER_ID` (manager account) in the tenant `.env`.

---

## Getting Started (5 minutes, no credentials)

1. **Seed the brain:**
   ```
   python scripts/seed_db.py
   ```
2. **Activate the demo client:**
   ```
   cp 02_Active_Clients/Aurora_Skincare/.env.example 02_Active_Clients/Aurora_Skincare/.env
   ```
3. **Run a command:**
   ```
   python foundry.py account audit --client Aurora_Skincare
   ```
4. **Verify everything works:**
   ```
   python scripts/smoke_test.py
   ```

---

## Commands (23)

### Account
| Command | Arabic trigger | Output |
|---|---|---|
| `foundry account audit --client <t>` | راجع حسابي | 0-100 score + grade + top fixes + 30-day plan |
| `foundry account diagnose --client <t>` | الروآس وقع | Single biggest constraint + ranked findings |
| `foundry account report --client <t> --lang ar` | تقرير للعميل | Decision-first client readout, EN or AR |

### Economics (deterministic calculator)
| Command | Arabic | Output |
|---|---|---|
| `foundry economics breakeven --price 499 --cogs 150 ...` | نقطة التعادل | Break-even CPA + ROAS |
| `foundry economics cod --spend 20000 --orders 400 ...` | — | Real ROAS + profit verdict |
| `foundry economics learning --cpa 120` | — | Budget to exit learning |
| `foundry economics vat --budget 10000 --country SA` | — | VAT split by MENA country |

### Campaigns / Content / Tracking / Leads / Creative / Competitive / Seasonal / Forecast / Ops / Tenants
14 more verbs covering campaign visibility, content pipeline, tracking readiness, lead scoring, creative hooks/angles, competitive positioning, MENA seasonal planning, budget forecasting, engine health, and multi-tenant management. See `skills/foundry-commands/SKILL.md` for the full roster.

---

## How to Verify It Actually Works

`python -m pytest tests` runs unit tests for the money-moving paths (mocked SDK/HTTP). `python scripts/smoke_test.py` is a one-command, self-cleaning test that:
- Seeds the kernel and verifies the squad roster
- Confirms every engine module imports cleanly
- Re-checks the path-traversal security fix
- Runs a real signal through the content-engine pipeline
- Runs all 23 commands against the demo tenant
- Pins the calculator's money math to hand-computed values

13+ checks, pass/fail per check, final tally. Same test CI runs on every push.

---

## Loops (scheduled automation)

- **ad-intel** — Google Ads monitoring, budget-burn alerts, content-opportunity signals
- **meta-ads** — same pattern for Meta (Facebook/Instagram) Ads
- **content-engine** — turns signals into draft content briefs
- **social-calendar** — decides WHEN/WHERE briefs publish
- **creative-brief** — turns briefs into image/video generation prompts (the one LLM call)
- **lead-qualify** — scores inbound leads, drafts outreach

---

## Agents & Skills

- **`01_Context_Vault/Agents/`** — 67 agent definitions across marketing, engineering, design, product, testing, and support. Full social media squad: Twitter/X, LinkedIn, Instagram, TikTok, Reddit.
- **`01_Context_Vault/Skills/diagram-design/`** — 38 HTML/SVG diagram primitives.
- **`01_Context_Vault/Protocols/*/SKILL.md`** — operating procedures, not just personas.

---

## Architecture

Multi-tenant from day one. One kernel, unlimited clients. Each client's
credentials, strategy, and history live in their own isolated folder — no
risk of one client's data leaking into another's run.

- **Engine** (`core/engine/`) — Python state machine: signals, tasks, loops, commands, tenant isolation
- **Context Vault** (`01_Context_Vault/`) — agents, skills, protocols, methodology
- **Clients** (`02_Active_Clients/`) — per-tenant folders with .env, STRATEGY.md, signals, reports
- **Foundry CLI** (`foundry.py`) — unified entry point for all 23 commands

Every command is deterministic Python. No LLM calls in the engine. Judgment
work stays in the AI interface layer (skills and agents). Money figures come
from `calc.py` with assumptions printed alongside every number.

---

## Principles

- **No Magic:** Marketing is engineering.
- **No Slop:** Anti-AI writing protocols enforced.
- **No Waste:** Management by exception only.
- **No Auto-Publish:** Maker/checker built into every task contract.

---

## License

MIT (see LICENSE). Bundled third-party content keeps its own licences: see NOTICE.md and licenses/. Developed by Mohamed Omar (@mohamedOmar11111) | The Growth Architect.