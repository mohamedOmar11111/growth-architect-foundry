"""growth_engine.commands.diagnose — name the single biggest constraint.

Reads the funnel ladder top-down (attention -> traffic quality -> conversion),
gates on tracking/config and ops health first, and stops at the FIRST failing
layer — a diagnosis that lists six problems is a way to fix none of them.

Output contract:
  1. VERDICT — the one bottleneck, one line
  2. Funnel ladder table — reading + pass/fail per layer
  3. Findings ranked by leverage — each labeled *confirmed by data* or
     *hypothesis — verify with X*, each with a test
  4. THE ONE FIX — the single highest-leverage change and its hypothesis
  5. Honest limits — what this diagnosis could NOT see

Thresholds used here are heuristics, not benchmarks: CTR bands are anchored
to this kernel's own content-opportunity threshold (5.0% in ad_intel.py),
and CPA is judged only against this tenant's own target — never against
another market's numbers.
"""

from __future__ import annotations

from typing import Any

from tenant import TenantContext
from utils import append_log
from commands.state import collect_snapshot, TARGET_CPA_KEY

CTR_WEAK = 1.0
CTR_ACCEPTABLE = 3.0
CTR_STRONG = 5.0
CPA_OVER_TARGET_TOLERANCE = 1.20
MIN_IMPRESSIONS_FOR_VERDICT = 1000


def _resolve_target_cpa(tenant: TenantContext, opts: dict | None) -> float | None:
    raw = (opts or {}).get("target_cpa") or tenant.env.get(TARGET_CPA_KEY)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _ctr_verdict(ctr: float) -> tuple[str, str]:
    if ctr >= CTR_STRONG:
        return "strong", f"{ctr:.2f}% CTR is above the {CTR_STRONG}% signal threshold"
    if ctr >= CTR_ACCEPTABLE:
        return "pass", f"{ctr:.2f}% CTR is in the acceptable band"
    if ctr >= CTR_WEAK:
        return "weak", f"{ctr:.2f}% CTR is below the {CTR_ACCEPTABLE}% acceptable band"
    return "fail", f"{ctr:.2f}% CTR is below the {CTR_WEAK}% floor — attention is not converting to clicks"


def build_diagnosis(snap: dict, target_cpa: float | None) -> dict:
    """Returns ladder readings + ranked findings. Pure: no I/O, so the smoke
    test can assert on exact verdicts for known inputs."""
    findings: list[dict[str, Any]] = []
    ladder: list[dict[str, Any]] = []

    cfg = snap["config"]
    config_ready = all(g["ready"] for g in cfg["groups"].values())
    ladder.append({
        "layer": "Tracking / config",
        "reading": f"{sum(g['configured'] for g in cfg['groups'].values())}"
                   f"/{sum(g['required'] for g in cfg['groups'].values())} credentials configured",
        "verdict": "pass" if config_ready else "fail",
    })
    if not config_ready:
        findings.append({
            "layer": "Tracking / config",
            "finding": (
                "Ad credentials are placeholders — no loop can pull live data, so "
                "every paid-media reading below is provisional until this is fixed."
            ),
            "evidence": ".env contains unconfigured placeholder values",
            "confidence": "confirmed by data",
            "likelihood": "certain",
            "test": "Fill .env with real keys, run `run_loop.py ad-intel --client "
                    "<tenant>`, confirm a report lands in 04_Reports/",
        })

    if snap["high_unprocessed"]:
        findings.append({
            "layer": "Ops",
            "finding": (
                f"{len(snap['high_unprocessed'])} high-priority signal(s) have not "
                "been converted into work — the kernel is seeing problems faster "
                "than the operator is acting on them."
            ),
            "evidence": f"signals/ with linked-task: none and priority: high "
                        f"(oldest open {snap['oldest_open_age_days']} day(s))",
            "confidence": "confirmed by data",
            "likelihood": "certain",
            "test": "Link or discard every high-priority signal today, re-run `audit`",
        })
    if snap["stuck_tasks"]:
        findings.append({
            "layer": "Ops",
            "finding": f"{len(snap['stuck_tasks'])} task(s) are stuck at max attempts — "
                       "work is being retried instead of resolved.",
            "evidence": "tasks/ with attempts >= max-attempts and status: open",
            "confidence": "confirmed by data",
            "likelihood": "certain",
            "test": "Cancel or unblock each stuck task explicitly, then re-run `audit`",
        })

    ad = snap["ad_report"]
    if ad is None:
        ladder.append({
            "layer": "Attention / traffic / conversion",
            "reading": "no paid data captured yet",
            "verdict": "unknown",
        })
        findings.append({
            "layer": "Attention / traffic / conversion",
            "finding": "No ad-intel report exists for this tenant — the paid funnel "
                       "cannot be diagnosed yet, only the ops layer above.",
            "evidence": "04_Reports/ contains no *-ad-intel-report.md",
            "confidence": "confirmed by data",
            "likelihood": "certain",
            "test": "Run `run_loop.py ad-intel --client <tenant>` against the live "
                    "account (or import a report), then re-run `diagnose`",
        })
    else:
        totals = ad["totals"]
        rows = ad["rows"]
        total_impr = sum(r["impressions"] or 0.0 for r in rows)
        total_clicks = sum(r["clicks"] or 0.0 for r in rows)
        ctr = (total_clicks / total_impr * 100) if total_impr else 0.0
        cta_verdict, cta_note = _ctr_verdict(ctr)

        ladder.append({
            "layer": "Attention",
            "reading": f"{total_impr:,.0f} impressions, {totals['cost']:,.2f} spend "
                       f"({len(rows)} campaign(s))",
            "verdict": "pass" if total_impr >= MIN_IMPRESSIONS_FOR_VERDICT else "weak",
        })
        ladder.append({
            "layer": "Traffic quality",
            "reading": f"{ctr:.2f}% CTR ({total_clicks:,.0f} clicks)",
            "verdict": cta_verdict,
        })

        if total_impr < MIN_IMPRESSIONS_FOR_VERDICT:
            findings.append({
                "layer": "Attention",
                "finding": "Delivery volume is too low to judge anything downstream — "
                           "this is a spend/eligibility problem before it is a "
                           "creative problem.",
                "evidence": f"{total_impr:,.0f} impressions across {len(rows)} campaign(s)",
                "confidence": "confirmed by data",
                "likelihood": "high",
                "test": "Check ad approval status and keyword eligibility, then "
                        "compare against the account's own 90-day baseline",
            })
        elif cta_verdict in ("weak", "fail"):
            findings.append({
                "layer": "Traffic quality",
                "finding": cta_note + " — the creative/angle is not earning the click.",
                "evidence": f"{ctr:.2f}% CTR on {total_impr:,.0f} impressions",
                "confidence": "confirmed by data",
                "likelihood": "high",
                "test": "Rewrite the hook/angle on the weakest campaign (not the "
                        "fonts), hold everything else constant, read CTR in 7 days",
            })

        cpa = totals["cpa"]
        if target_cpa is None:
            ladder.append({
                "layer": "Conversion",
                "reading": f"CPA {cpa:.2f}" if cpa is not None else "no conversions",
                "verdict": "unknown",
            })
            findings.append({
                "layer": "Conversion",
                "finding": "No target CPA configured — cost per acquisition cannot be "
                           "judged. Advice without a target is content, not media buying.",
                "evidence": (
                    f"{TARGET_CPA_KEY} unset in .env and no --target-cpa passed; "
                    f"observed CPA {cpa:.2f}"
                    if cpa is not None
                    else f"{TARGET_CPA_KEY} unset; no conversions recorded"
                ),
                "confidence": "hypothesis — verify with a real target",
                "likelihood": "certain (the gap, not the number)",
                "test": "Set TARGET_CPA from break-even: `python calc.py breakeven "
                        "...` then re-run `diagnose --target-cpa <value>`",
            })
        elif cpa is None:
            ladder.append({"layer": "Conversion", "reading": "no conversions recorded",
                           "verdict": "fail"})
            findings.append({
                "layer": "Conversion",
                "finding": f"Spend is live but zero conversions against a target CPA "
                           f"of {target_cpa:.2f} — tracking or offer, not bidding.",
                "evidence": f"cost {totals['cost']:,.2f}, conversions 0",
                "confidence": "confirmed by data",
                "likelihood": "high",
                "test": "Verify the optimization event fires (Pixel/CAPI) before "
                        "touching bids — if tracking is clean, the offer is the problem",
            })
        elif cpa > target_cpa * CPA_OVER_TARGET_TOLERANCE:
            ladder.append({
                "layer": "Conversion",
                "reading": f"CPA {cpa:.2f} vs target {target_cpa:.2f}",
                "verdict": "fail",
            })
            findings.append({
                "layer": "Conversion",
                "finding": f"CPA is {cpa / target_cpa:.2f}x target — the funnel is "
                           "paying too much per acquisition.",
                "evidence": f"observed CPA {cpa:.2f}, target {target_cpa:.2f}",
                "confidence": "confirmed by data",
                "likelihood": "high",
                "test": "Cut the worst campaign first (waste before scale), then "
                        "re-read CPA on the remaining spend in 7 days",
            })
        else:
            ladder.append({
                "layer": "Conversion",
                "reading": f"CPA {cpa:.2f} vs target {target_cpa:.2f}",
                "verdict": "pass",
            })

    ranked = sorted(
        findings,
        key=lambda f: {"certain": 3, "high": 2, "medium": 1}.get(f["likelihood"].split()[0], 1),
        reverse=True,
    )
    bottleneck = ranked[0]["layer"] if ranked else "none — every layer passes"
    return {"ladder": ladder, "findings": ranked, "bottleneck": bottleneck}


def format_diagnosis(tenant: TenantContext, snap: dict, diag: dict,
                     target_cpa: float | None) -> str:
    now = snap["now"].strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# {tenant.name} — Diagnosis — {now}",
        "",
        f"**VERDICT:** the single biggest constraint is **{diag['bottleneck']}**. "
        "Everything else is downstream or noise until that moves.",
        "",
        "## Funnel Ladder (top-down, first failing layer wins)",
        "| Layer | Reading | Verdict |",
        "|---|---|---|",
    ]
    for row in diag["ladder"]:
        lines.append(f"| {row['layer']} | {row['reading']} | {row['verdict']} |")

    lines += ["", "## Findings (ranked by leverage)",
              "| # | Finding | Evidence | Confidence | Test |",
              "|---|---|---|---|---|"]
    if diag["findings"]:
        for i, f in enumerate(diag["findings"], 1):
            lines.append(f"| {i} | {f['finding']} | {f['evidence']} | "
                         f"{f['confidence']} | {f['test']} |")
    else:
        lines.append("| — | Nothing wrong in the layers this diagnosis can see. "
                     "| — | — | — |")

    lines += ["", "## The One Fix"]
    if diag["findings"]:
        top = diag["findings"][0]
        lines.append(
            f"Fix **{top['layer']}** first: {top['test']}. "
            f"Hypothesis: this lifts the {top['layer'].lower()} layer to passing "
            "within one cadence cycle — re-run `diagnose` and compare the ladder."
        )
    else:
        lines.append("Nothing to fix — scale instead. Any scale recommendation "
                     "still needs unit economics: run `python calc.py breakeven` first.")

    lines += ["", "## Honest Limits",
              "- Thresholds here are heuristics (CTR bands anchored to this "
              "kernel's 5% signal threshold), not industry benchmarks. Judge this "
              "account against its own 90-day baseline, not another market's numbers.",
              "- Every projection on this page is an estimate. Nothing here is a "
              "guarantee, and none of it is legal or tax advice.",
              f"- Target CPA used: {target_cpa:.2f}" if target_cpa is not None
              else "- No target CPA configured — conversion layer judged as unknown, "
                   "not as passing."]
    return "\n".join(lines)


def run(tenant: TenantContext, opts: dict | None = None) -> int:
    snap = collect_snapshot(tenant)
    target_cpa = _resolve_target_cpa(tenant, opts)
    diag = build_diagnosis(snap, target_cpa)
    report = format_diagnosis(tenant, snap, diag, target_cpa)

    report_path = tenant.reports_dir / (
        f"{snap['now'].strftime('%Y-%m-%d-%H')}-diagnose.md"
    )
    report_path.write_text(report, encoding="utf-8")

    if opts is not None:
        opts.get("_extra", {})["_data"] = diag
    print(report)
    print(f"\n[{tenant.name}] diagnose: report written -> {report_path}")
    append_log(tenant.name, "diagnose",
               f"Diagnosis identified '{diag['bottleneck']}' as the primary constraint",
               report_path)
    return 0
