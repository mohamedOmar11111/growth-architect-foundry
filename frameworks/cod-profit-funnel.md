# Framework: COD Profit Funnel

> A mental model for thinking about cash-on-delivery profitability. The platform sees a funnel; the operator sees a pipeline with three places money leaks.

---

## The Three Gates

```
Ad Spend → [Gate 1: Confirmation] → [Gate 2: Delivery] → [Gate 3: Retention] → Revenue
              70-90%                    65-85%                85-95%
```

**Gate 1 — Confirmation rate.** The customer placed the order but will they answer the phone? In MENA COD markets, 15-30% of orders are never confirmed. This is a marketing problem (wrong audience) AND an operations problem (slow follow-up).

**Gate 2 — Delivery rate.** The customer confirmed but will they be home? Will they accept the product? 10-25% of confirmed orders never deliver. This is a logistics problem, not an ad problem — but it kills your ROAS just the same.

**Gate 3 — Retention rate.** The customer received it — will they keep it? 5-15% return. This is a product/offer problem. If return rate spikes, the ad creative isn't the issue.

## The Math

For every 1,000 SAR spent on ads:

| Metric | Optimistic | Realistic | Pessimistic |
|---|---|---|---|
| Orders placed | 50 | 40 | 30 |
| Confirmed (85%) | 43 | 34 | 26 |
| Delivered (80%) | 34 | 27 | 20 |
| Kept (90%) | 31 | 24 | 18 |
| Revenue at 499 SAR AOV | 15,469 | 11,976 | 8,982 |
| **Effective ROAS** | **15.5×** | **12.0×** | **9.0×** |

Platform shows 50 orders → ROAS looks like 25×. Reality: 31 orders → ROAS is 15.5×. The platform overcounts by 61%.

## Where to Intervene

| Gate | Whose problem | What to fix | Leverage |
|---|---|---|---|
| Confirmation | Marketing + Ops | WhatsApp follow-up within 1 hour, audience targeting | High — 10-15% improvement typical |
| Delivery | Logistics | Delivery partner SLA, address verification | Medium — depends on partner |
| Retention | Product | Product quality, accurate descriptions, packaging | Low — slow to move |

**Start at Gate 1** (highest leverage, fastest to fix). Then Gate 2. Gate 3 is a product conversation, not a marketing one.

## Using the Framework

1. Run `foundry economics cod` with real numbers
2. Identify which gate is leaking most
3. If Gate 1: fix WhatsApp flow + audience targeting
4. If Gate 2: talk to logistics, not to the ad platform
5. If Gate 3: escalate to the client — marketing can't fix a product nobody wants

---

*This framework is a mental model, not a calculator. For real numbers, use `foundry economics cod --spend ... --orders ... --confirm ... --deliver ...`.*