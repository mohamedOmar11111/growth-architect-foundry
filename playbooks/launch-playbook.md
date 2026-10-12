# Launch Playbook — New Client Onboarding

> The 7-day sprint from "signed the contract" to "first live campaign pulling data." Not theory — the exact sequence this kernel enforces.

---

## Day 0 — Intake (30 minutes)

Run `foundry account audit --client <new_client>` immediately after copying the tenant folder. The audit score tells you exactly what's missing — don't guess.

1. Copy `02_Active_Clients/Aurora_Skincare/` → `02_Active_Clients/<ClientName>/`
2. Fill `.env` with real credentials (Google Ads keys, Meta token)
3. Fill `STRATEGY.md` with the client's actual voice, audience, directives
4. Run `foundry tracking check --client <ClientName>` — confirm all integrations ready
5. Run `foundry economics breakeven` with the client's real unit economics
6. Set `TARGET_CPA` in `.env` to the break-even CPA ÷ 1.2

## Day 1 — Baseline (1 hour)

7. Run `foundry account report --client <ClientName> --period month` — this is your "before" snapshot
8. Run `foundry campaigns list --client <ClientName>` — see what's live
9. Run `foundry campaigns status --client <ClientName>` — flag zero-spend and paused
10. Run `foundry tracking events --client <ClientName>` — confirm optimization events fire

## Day 2-3 — First Optimization

11. Run `foundry account diagnose --client <ClientName>` — name the ONE bottleneck
12. Fix the bottleneck (usually tracking or budget allocation)
13. Run `foundry campaigns compare --client <ClientName>` — identify the weakest campaign
14. Cut waste before scaling (rule 6: waste first, scale second)

## Day 4-5 — Content Pipeline

15. Run `foundry creative hooks --client <ClientName>` — get angle ideas from winning signals
16. Run `foundry content pipeline --client <ClientName>` — check signal→brief flow
17. Run the `content-engine` loop to draft briefs from winning ad angles
18. Run `foundry season plan --client <ClientName>` — check upcoming MENA dates

## Day 6-7 — First Report

19. Run `foundry account report --client <ClientName> --lang ar --period week`
20. Review the report, add your operator notes, send to client
21. Run `foundry ops cadence --client <ClientName>` — confirm loops are on schedule
22. Run `foundry account audit --client <ClientName>` — compare score to Day 0

## Ongoing

- **Daily:** `foundry campaigns status --client <ClientName>` (30 seconds)
- **Weekly:** `foundry account report --client <ClientName>` (5 minutes)
- **Monthly:** `foundry account audit --client <ClientName>` + full review
- **Before every client call:** `foundry account diagnose --client <ClientName>`

---

*Every step uses a deterministic command. No guessing, no "I'll check manually."*