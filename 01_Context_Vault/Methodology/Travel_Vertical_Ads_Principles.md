# Travel/Tourism Vertical — Google Ads Structural Principles

**Status:** Generic methodology, illustrative only. No client-specific
account data, keyword lists, or targeting parameters below — every buyer's
actual keyword set, negative list, and CPA target must be built fresh
against their own account and market, not copied from here.

---

## 1. Structural Philosophy: Single-Node Architecture
- **The Rule:** One Campaign = One Ad Group, where account size allows.
- **The Logic:** Fragmentation is a budget killer. Pooling conversion data
  into a single "Master" node per destination/offer lets Google's Smart
  Bidding reach its Learning Phase faster than a fragmented account
  structure would.
- **Must Not:** Split budgets across city-specific or interest-specific ad
  groups purely for organizational tidiness — every split divides the
  conversion-data volume each ad group needs to actually learn.

## 2. Conversion Integrity: Primary vs Secondary
- **The Rule:** Only genuine "final terminal actions" (a completed booking,
  a qualifying call, a real form submission) should be marked Primary.
- **The Logic:** Smart Bidding optimizes toward whatever is marked Primary.
  If a low-intent action (page view, button click, form start) is Primary,
  the algorithm will buy you more of THAT, not more buyers.
- **Rule:** All informational/soft actions should be Secondary
  (observation-only) — visible in reporting, never bid-optimization targets.

## 3. Keyword Architecture: Intent-Tiering
- **Broad-Intent (Volume):** Broad match is appropriate for category-level,
  early-funnel terms (e.g. generic package/offer searches) where the goal
  is volume + Smart Bidding signal, not immediate conversion.
- **Exact-Commitment (Lock):** Exact match for high-intent, late-stage
  planning terms specific to your actual inventory (destination names,
  product SKUs, "book now"-adjacent phrasing).
- **A general heuristic, not specific to any vertical:** searches for a
  mandatory downstream requirement tied to already-decided intent (e.g.
  required documentation/insurance for a trip already booked) can be a
  useful high-density late-funnel signal — but validate this against your
  own account's actual search-term report, don't assume it transfers.

## 4. Targeting Protocol
- **Geography:** Prefer "Presence" targeting (people actually in-market
  geographically) over "Presence or Interest" when local intent matters
  more than reach.
- **Audiences:** Use Observation Mode to give Smart Bidding signal without
  restricting total auction reach — don't hard-restrict to an audience
  segment unless you have the volume to support it.

## 5. Negative-Keyword Hygiene (Categories, Not Lists)
Build your own negative lists per category — don't import someone else's
literal list, since actual negative terms are account- and
language-specific:
- **Informational block:** generic research terms with no purchase intent
  (images, maps, weather, news, time-zone lookups).
- **Low-intent block:** free/job/discount-hunting terms unrelated to your
  actual offer.
- **Relevance block:** terms tied to markets/segments/legal categories your
  business doesn't actually serve.

## 6. Scaling & Governance: The 20% Rule
- **The Threshold:** Avoid increasing a daily budget by more than ~20% in
  any 48-72 hour window.
- **The Logic:** Large budget spikes reset Smart Bidding's learning state
  and cause CPA spikes. Small, iterative steps preserve the conversion
  signal density the algorithm needs.

---

## How to apply this to a real account
This document is structural principles only. To make it real for a
specific tenant:
1. Build that tenant's actual keyword lists from their own search-term
   report (`analyze_search_terms`-equivalent data), not from any example
   list.
2. Set their actual CPA target from their own margin math, not a borrowed
   number.
3. Store the resulting real strategy in that tenant's own `STRATEGY.md`
   under `02_Active_Clients/<tenant>/` — never in this shared Methodology
   folder, which every tenant's context can potentially read.
