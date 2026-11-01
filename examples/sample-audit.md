# Example - Performance Audit (imported CSV) - 2026-11-01 15:57

**VERDICT:** 45/100 (grade F). 1 campaign(s) spent heavily with no conversions: Campaign C - Broad.

## Score components
| Component | Weight | Score | Evidence |
|---|---|---|---|
| Efficiency | 40% | 12/100 | 35% of spend is waste (no conversions, or half of a loser's spend) |
| Conversion | 25% | 65/100 | 65% of spend sits in campaigns that convert (no target CPA set) |
| Traffic quality | 25% | 55/100 | 2.06% CTR overall |
| Spend spread | 10% | 100/100 | top campaign takes 50% of spend |

Confidence: **medium** (37 conversions in the data).

## Campaigns
| Campaign | Spend | Share | Conversions | CPA | Call |
|---|---|---|---|---|---|
| Campaign A - Prospecting | 500.00 USD | 50% | 31 | 16.13 | Keep |
| Campaign C - Broad | 350.00 USD | 35% | 0 | - | Stop |
| Campaign B - Retargeting | 150.00 USD | 15% | 6 | 25.00 | Too early |

## Top fixes (ranked)
1. **Campaign efficiency**: 1 campaign(s) spent heavily with no conversions: Campaign C - Broad. Evidence: 350.00 spent (35% of total) and 0 conversions. *confirmed by data*. Test: Confirm tracking is live for these campaigns, then pause them or cut their budget by 20%.
2. **Conversion**: No target CPA given, so CPA is compared only with this account's own average. Evidence: blended CPA 27.03. *hypothesis: verify with a real target*. Test: Work out break-even with `economics breakeven`, then re-run with `--target-cpa <value>`.
3. **Evidence**: Conversions come from Meta's Results column, which counts a different thing per campaign objective. Evidence: Results can be reach, clicks, messages or purchases. *confirmed by data*. Test: Export with a purchase or lead column (or check Result indicator) before scaling any campaign.

## 30-day plan
**Do today:**
- Confirm tracking is live on Campaign C - Broad, then pause or cut the budget.
**Test this week:**
- Work out break-even (`economics breakeven`) and re-run with --target-cpa.
**Stop / reduce:**
- Campaign C - Broad: 350.00 spent, no conversions

## Honest limits
- Period is whatever the export covered; the file does not say.
- Conversions are as the ad platform reports them. For cash-on-delivery, judge delivered revenue instead.
- Roles and the score use fixed heuristics from this engine, not industry benchmarks.
- A campaign needs at least 10 conversions before it is called a winner or a loser.