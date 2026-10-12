# Funnel Playbook — Finding and Fixing the Leak

> The funnel is a chain, not a list. Fix the first broken link — everything downstream is noise until that moves.

---

## The Ladder (always check top-down)

### 1. Tracking — "Can we even measure?"

**Symptoms:**
- Platform shows conversions, backend shows zero (or vice versa)
- CPA looks great on-platform but the client says no sales
- COD accounts: platform counts "Purchase" but real revenue is "Delivered"

**Check:** `foundry tracking check --client <t>` + `foundry tracking events --client <t>`

**Fix first.** Every number below is provisional until tracking is clean. Rule 1: signal before bids.

**COD-specific:** track the "Delivered" event, not "Purchase." The platform's conversion count includes orders that will be returned — your real ROAS is only delivered revenue.

### 2. Attention — "Is anyone seeing the ads?"

**Symptoms:**
- Impressions < 1,000/week across all campaigns
- ENABLED campaigns with zero spend
- Budget burned by 10am, nothing after

**Check:** `foundry campaigns status --client <t>`

**Thresholds:**
- < 1,000 impressions/week → delivery problem (ad approval, keyword eligibility, budget too low)
- Zero-spend ENABLED campaigns → check ad approval status
- Budget burned early → raise daily budget or switch to shared budget

### 3. Traffic Quality — "Are they clicking?"

**Symptoms:**
- CTR < 1% on Search campaigns
- High impressions, low clicks
- Broad-match terms eating budget

**Check:** `foundry campaigns list --client <t>` — look at CTR column

**Thresholds (heuristics, not benchmarks):**
- CTR < 1% → creative/keyword mismatch — rewrite the ad, not the bid
- CTR 1-3% → acceptable, room to improve
- CTR 3-5% → strong
- CTR > 5% → content-opportunity signal (ad-intel writes this automatically)

**Fix:** Diagnose the ANGLE, not the font. "Are we showing the right message to the right search intent?"

### 4. Conversion — "Are they buying?"

**Symptoms:**
- CTR fine but no conversions
- CPA 2× target
- Lots of add-to-carts, no checkouts

**Check:** `foundry account diagnose --client <t> --target-cpa <value>`

**Thresholds:**
- CPA ≤ target → on track
- CPA 1.0-1.2× target → watch it, don't panic
- CPA > 1.2× target → cut the worst campaign first

**COD-specific:** check confirmation and delivery rates. A 70% delivery rate means 30% of your "sales" evaporate — your real CPA is 1.4× what the platform shows.

### 5. Saturation — "Have we exhausted the audience?"

**Symptoms:**
- Frequency > 4 on Meta/Snapchat
- CTR declining week-over-week on the same creative
- CPA rising despite no bid changes

**Check:** `foundry campaigns compare --client <t>` — look at week-over-week trends

**Fix:** New creative angle (not new fonts), expand audience, or shift budget to a fresh platform.

---

## The One-Fix Rule

A diagnosis that lists six problems is a way to fix none of them. Run `diagnose`, fix the first failing layer, re-run `diagnose`. If the bottleneck moved, you fixed the right thing. If it didn't, you didn't.

---

*Every threshold here is a heuristic anchored to this kernel's own constants (e.g., 5% CTR = content-opportunity threshold in ad_intel.py). Judge each account against its own 90-day baseline, not these numbers.*