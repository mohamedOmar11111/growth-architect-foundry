---
title: "Experiment Log — [Hypothesis short name]"
author: "Mohamed Omar"
category: "experiment"
type: "experiment-log"
started: "YYYY-MM-DD"
ended: "YYYY-MM-DD"
status: "[running | passed | failed | inconclusive]"
---

# Experiment: [Hypothesis]

> "We believe [change] will move [metric] by [range] because [insight]."

---

## Setup

- **Hypothesis:** [exact statement]
- **Metric:** [what we're measuring — not vanity, not composite]
- **Success line:** [the number that means it worked — stated BEFORE the test starts]
- **Sample size:** [how many impressions/clicks/conversions needed for confidence]
- **Duration:** [planned end date — not "until it looks good"]
- **What changed:** [exactly what's different — campaign name, audience, creative, bid]
- **What held constant:** [everything else — because one variable at a time]

## Results

| Metric | Control | Variant | Δ | Confidence |
|---|---|---|---|---|
| [metric] | [value] | [value] | [%] | [high/medium/low] |

## Verdict

[PASS / FAIL / INCONCLUSIVE — and why, with the actual numbers.]

## What We Learned

[Non-obvious insight. Not "the variant won" — WHY it won, and what that means for the next test.]

## Next Test

[Based on this result, what's the next hypothesis? Chain experiments, don't run isolated ones.]

---

*Logged deterministically. Every number comes from a captured report or calculator (`calc.py`). Re-run the experiment log after the test ends and diff the two versions.*