# Worked Example: Signal → Content Pipeline

> **Labeled fictional.** Shows how a winning ad angle becomes a content brief through the kernel's automated pipeline.

---

## The Scenario

You're running Google Ads for a KSA retinol brand. The `ad-intel` loop has been running every 6 hours. One morning it writes a signal.

## Step 1: ad-intel writes the signal

The ad-intel loop detects that campaign "Retinol 0.5% - Night" has:
- CTR: 6.10% (above the 5% content-opportunity threshold)
- Clicks: 340 (above the 20-click minimum)
- Cost: 412.50 SAR
- Conversions: 28

It writes a signal file: `signals/2026-10-12-retinol-0-5-night-content-opportunity.md`

## Step 2: content-engine turns it into a brief

```
python run_loop.py content-engine --client RetinolKSA
```

Reads the signal, creates a draft brief in `02_Content/`:
- The brief is grounded in the signal's real data (6.1% CTR, 340 clicks)
- Voice rules pulled from `STRATEGY.md`
- Marked as DRAFT — needs operator review

## Step 3: social-calendar decides when/where it publishes

```
python run_loop.py social-calendar --client RetinolKSA
```

Reads the brief, consults STRATEGY.md's PREFER/AVOID directives, and writes a content calendar entry:
- Instagram: 2 days from now (ingredient education angle)
- TikTok: 3 days from now (before/after format)
- Blog: 5 days from now (deep-dive "retinol 0.5% vs 1% comparison")

## Step 4: Check the pipeline

```
python foundry.py content pipeline --client RetinolKSA
```

**Output:**
```
## Content Pipeline
| Stage | Count |
|---|---|
| Content-idea signals (total) | 3 |
| Unprocessed content-idea signals | 0 |
| Content-engine tasks | 3 |
| Draft briefs | 3 |
| Calendar exists | yes |
```

All signals processed. Pipeline is healthy.

## Step 5: Get creative hooks

```
python foundry.py creative hooks --client RetinolKSA
```

**Output:** Three hook ideas drawn from the winning signals:
1. "Retinol 0.5% — the dose dermatologists actually recommend" (from the 6.1% CTR campaign)
2. "Why your retinol isn't working (it's the concentration, not the brand)"
3. "Retinol at night, SPF in the morning — the only routine that works"

Each hook is grounded in real performance data, not theory.

---

## What this example teaches

1. The pipeline is automated: signal → brief → calendar, with human review at each stage
2. Winning ad angles become organic content — same audience intent, no paid spend
3. The `creative hooks` command draws from real signals, not from a generic list
4. Nothing gets published without operator approval

*Pattern is real. Client name and numbers are fictional.*