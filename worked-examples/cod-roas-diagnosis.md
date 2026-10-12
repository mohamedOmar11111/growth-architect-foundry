# Worked Example: COD ROAS Diagnosis

> **Labeled fictional.** This walkthrough uses invented numbers to show HOW the Foundry's commands chain together to diagnose a real problem. The pattern is real; the client is not.

---

## The Scenario

You're managing a COD skincare brand in KSA. The client says: "Meta says our ROAS is 8× but we're barely breaking even. Where's the money going?"

## Step 1: Check the real numbers

```
python foundry.py economics cod \
    --spend 30000 --orders 500 --aov 399 \
    --confirm 0.82 --deliver 0.74 \
    --cogs 120 --ship-out 35 --fees 5 --return-cost 25
```

**Output:**
```
Delivered orders:      303.50
Delivered revenue:     121,096.50
Real ROAS (delivered): 4.0366
Real CPA (per placed): 60.00
Break-even CPA:        82.47
Gross profit after ads: 6,859.00

VERDICT: profitable
```

**What happened:** Meta counted 500 orders × 399 AOV = 199,500 revenue → ROAS looks like 6.65×. Reality: only 303.5 orders delivered → revenue is 121,097 → real ROAS is 4.04×. The platform overcounted by 65%.

## Step 2: Run the account audit

```
python foundry.py account audit --client SkincareKSA
```

**Key finding:** Configuration score is 100/100 (all creds set), but Task throughput is 40/100 — 5 tasks stuck at max attempts. The operator has been ignoring the kernel's alerts.

## Step 3: Diagnose the bottleneck

```
python foundry.py account diagnose --client SkincareKSA --target-cpa 82
```

**Verdict:** The single biggest bottleneck is **Conversion** — CPA (60.00) is below target (82.47), which looks fine... until you account for the COD leakage. The "real" CPA after delivery losses is 60 / 0.607 (delivered rate) = 98.85, which is above the break-even CPA of 82.47.

**Wait — this means the account is actually unprofitable?** Let me re-check...

Actually, the `cod` command already accounts for delivery rates in its profit calculation. The 6,859 SAR profit is real — but thin. The issue isn't that the account is losing money; it's that the client *perceives* 8× ROAS when the real number is 4×.

## Step 4: The fix

1. **Set the optimization event to "Delivered"** — so Meta stops learning from phantom conversions
2. **Split Egypt and KSA** into separate campaigns (they were aggregated, diluting the KSA data)
3. **Run WhatsApp confirmation flow** — current confirmation rate is 82%, target 90%

## Step 5: Report to the client

```
python foundry.py account report --client SkincareKSA --lang ar --period week
```

**Verdict line:** «الحالة: الـ ROAS الحقيقي 4× (مش 8× زي ما المنصة بتقول). الأرباح حقيقية بس رقيقة — محتاجين نحسّن تأكيد الطلب على واتساب.»

---

## What this example teaches

1. Never trust platform ROAS on a COD account — always run `foundry economics cod`
2. The "real" number and the "platform" number can differ by 60%+
3. A profitable account can still be in trouble if the margin is thin
4. The Foundry's commands chain: economics → audit → diagnose → report

*Pattern is real. Client name, numbers, and market are fictional.*