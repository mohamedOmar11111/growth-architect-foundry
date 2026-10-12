# COD Operations Playbook

> Cash-on-delivery is not prepaid with extra steps — it's a different business model with different math, different tracking, and different failure modes. This playbook is for accounts where 30%+ of orders are COD.

---

## The COD Profit Equation

Standard ROAS is a lie on COD accounts. The platform counts a "Purchase" when someone places an order — but you only get paid when the order is delivered. Your real math:

```
Real ROAS = Delivered Revenue ÷ Ad Spend
Real CPA  = Ad Spend ÷ Delivered Orders (not placed orders)
```

Use `foundry economics cod` to compute this with real numbers:
```
python foundry.py economics cod --spend 20000 --orders 400 --aov 499 \
    --confirm 0.85 --deliver 0.78 --cogs 150 --ship-out 45 --fees 3 --return-cost 30
```

## The Three Rates That Kill You

| Rate | What it means | Typical MENA range | Where to check |
|---|---|---|---|
| **Confirmation rate** | % of placed orders the customer confirms (answers the phone) | 70-90% | Backend / CRM |
| **Delivery rate** | % of confirmed orders that actually get delivered | 65-85% | Logistics partner |
| **Return rate** | % of delivered orders returned within the window | 5-15% | Backend / CRM |

**Effective delivered rate = confirmation × delivery.** If both are 85%, your effective rate is 72% — meaning 28% of every ad dollar spent on "conversions" produced zero revenue.

## What to Track (Platform Events)

| Event | What it means | Use it for |
|---|---|---|
| Purchase (platform default) | Order placed | Platform optimization (learning) |
| Confirmed | Customer answered + confirmed | Better funnel diagnosis |
| Delivered | Order received + paid | **Real ROAS calculation** |
| Returned | Order returned | Waste quantification |

**Set the platform optimization event to "Delivered" if your volume supports it (~50/week).** If not, optimize on "Purchase" but ALWAYS judge performance on "Delivered."

## Country-by-Country Differences

Egypt ≠ KSA ≠ UAE. Never aggregate them:

| Market | Typical confirm | Typical deliver | CPM range | Notes |
|---|---|---|---|---|
| Egypt | 70-80% | 60-75% | 15-40 EGP | High volume, low AOV, WhatsApp confirmations |
| KSA | 80-90% | 75-85% | 15-40 SAR | Higher AOV, faster delivery |
| UAE | 85-95% | 80-90% | 15-35 AED | Highest delivery rate, prepaid growing |
| Kuwait | 80-90% | 75-85% | 5-15 KWD | Small market, high AOV |

## Red Flags

1. **Platform ROAS looks great but client says no profit** → you're measuring placed orders, not delivered
2. **Delivery rate dropped suddenly** → check logistics partner, not ad creative
3. **Confirmation rate < 70%** → wrong audience or poor WhatsApp follow-up
4. **Return rate > 15%** → product/offer problem, not an ad problem

## The Fix Sequence

1. **Fix tracking first** — set "Delivered" as the optimization event
2. **Split by country** — Egypt and KSA in the same campaign is a guaranteed bad time
3. **Check confirmation flow** — WhatsApp confirmation within 1 hour of order raises confirmation rate 10-15%
4. **Then optimize ads** — only after the delivery pipeline is clean

---

*Use `foundry economics cod` for every money figure. Never trust the platform's ROAS on a COD account.*