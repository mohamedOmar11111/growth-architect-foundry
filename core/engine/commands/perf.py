"""Deterministic performance analysis of imported campaign rows (CSV mode). Pure: no I/O, no LLM.

Two outputs from the same numbers:
  * ranked findings + three action buckets (always available), and
  * a 0-100 performance score (withheld when there are no conversions to judge).

Every threshold below is a heuristic, named and documented here; the reports say so.
"""

from __future__ import annotations

from typing import Any

WASTE_CPA_MULTIPLE = 2.0       # spent more than 2 CPAs with no conversion
LOSER_VS_REFERENCE = 1.5       # CPA 50% above reference (blended CPA, or target when given)
LOSER_VS_TARGET = 1.2          # same tolerance diagnose.py uses
WINNER_VS_REFERENCE = 0.7
WASTE_PENALTY = 2.5            # every 1% of spend wasted costs 2.5 efficiency points
MIN_CONV_TO_JUDGE = 10         # fewer conversions than this: too thin to call winner or loser
WEAK_CTR, OK_CTR, STRONG_CTR = 1.0, 3.0, 5.0
CONCENTRATION_RISK = 0.70
CONFIDENCE_LOW, CONFIDENCE_MEDIUM = 30, 100   # total conversions
WEIGHTS = {"efficiency": 0.40, "conversion": 0.25, "traffic": 0.25, "concentration": 0.10}
GRADE_BANDS = ((90, "A"), (80, "B"), (70, "C"), (60, "D"), (0, "F"))


def _grade(score: float) -> str:
    return next(letter for floor, letter in GRADE_BANDS if score >= floor)


def _totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    cost = sum(r["cost"] for r in rows)
    impr = sum(r["impressions"] for r in rows)
    clicks = sum(r["clicks"] for r in rows)
    conv = sum(r["conversions"] for r in rows)
    return {"cost": cost, "impressions": impr, "clicks": clicks, "conversions": conv,
            "ctr": clicks / impr * 100 if impr else 0.0, "cpa": cost / conv if conv else None}


def _role(row: dict[str, Any], ref_cpa: float | None, has_target: bool) -> str:
    """waste | loser | winner | thin | ok | unjudged"""
    if ref_cpa is None:
        return "unjudged"
    if row["conversions"] == 0:
        return "waste" if row["cost"] >= WASTE_CPA_MULTIPLE * ref_cpa else "thin"
    if row["conversions"] < MIN_CONV_TO_JUDGE:
        return "thin"
    cpa = row["cost"] / row["conversions"]
    if cpa > ref_cpa * (LOSER_VS_TARGET if has_target else LOSER_VS_REFERENCE):
        return "loser"
    return "winner" if cpa < ref_cpa * WINNER_VS_REFERENCE else "ok"


def _ctr_score(ctr: float) -> float:
    return 100.0 if ctr >= STRONG_CTR else 80.0 if ctr >= OK_CTR else 55.0 if ctr >= WEAK_CTR else 25.0


def _concentration_score(top_share: float, n: int) -> float:
    if n < 2:
        return 50.0
    return 100.0 if top_share <= 0.5 else 75.0 if top_share <= CONCENTRATION_RISK else 50.0 if top_share <= 0.85 else 25.0


def _score(rows: list[dict[str, Any]], totals: dict[str, Any], target_cpa: float | None) -> dict[str, Any] | None:
    if totals["conversions"] == 0 or totals["cost"] == 0:
        return None
    spend = totals["cost"]
    wasted = sum(r["cost"] * (1.0 if r["role"] == "waste" else 0.5) for r in rows if r["role"] in ("waste", "loser"))
    efficiency = max(0.0, 100.0 - WASTE_PENALTY * wasted / spend * 100)
    converting = sum(r["cost"] for r in rows if r["conversions"] > 0)
    top_share = max(r["cost"] for r in rows) / spend
    if target_cpa:
        conversion = min(100.0, target_cpa / totals["cpa"] * 100)
        conv_note = f"blended CPA {totals['cpa']:.2f} vs target {target_cpa:.2f}"
    else:
        conversion = converting / spend * 100
        conv_note = f"{converting / spend:.0%} of spend sits in campaigns that convert (no target CPA set)"
    parts = {
        "efficiency": (efficiency, f"{wasted / spend:.0%} of spend is waste (no conversions, or half of a loser's spend)"),
        "conversion": (conversion, conv_note),
        "traffic": (_ctr_score(totals["ctr"]), f"{totals['ctr']:.2f}% CTR overall"),
        "concentration": (_concentration_score(top_share, len(rows)), f"top campaign takes {top_share:.0%} of spend"),
    }
    total = sum(parts[k][0] * WEIGHTS[k] for k in WEIGHTS)
    conv = totals["conversions"]
    confidence = "low" if conv < CONFIDENCE_LOW else "medium" if conv < CONFIDENCE_MEDIUM else "high"
    return {"total": total, "grade": _grade(total), "confidence": confidence,
            "components": {k: {"weight": WEIGHTS[k], "score": v[0], "evidence": v[1]} for k, v in parts.items()}}


def _finding(layer: str, finding: str, evidence: str, confidence: str, likelihood: str, test: str) -> dict[str, str]:
    return {"layer": layer, "finding": finding, "evidence": evidence, "confidence": confidence,
            "likelihood": likelihood, "test": test}


def _names(rows: list[dict[str, Any]], limit: int = 3) -> str:
    shown = ", ".join(r["name"] for r in rows[:limit])
    return shown + (f" (+{len(rows) - limit} more)" if len(rows) > limit else "")


def _findings(totals: dict[str, Any], by_role: dict[str, list], rows: list[dict[str, Any]],
              target_cpa: float | None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    spend = totals["cost"]
    if spend > 0 and totals["conversions"] == 0:
        out.append(_finding(
            "Conversion tracking", "Money is being spent and not one conversion is recorded in this export.",
            f"{spend:,.2f} spent, 0 conversions across {len(rows)} campaign(s)", "hypothesis: verify the export has the conversion column",
            "certain", "Check the conversion event fires and that the export includes the results/conversions column, before touching bids"))
        return out
    if by_role["waste"]:
        waste = by_role["waste"]
        lost = sum(r["cost"] for r in waste)
        out.append(_finding(
            "Campaign efficiency", f"{len(waste)} campaign(s) spent heavily with no conversions: {_names(waste)}.",
            f"{lost:,.2f} spent ({lost / spend:.0%} of total) and 0 conversions", "confirmed by data", "certain",
            "Confirm tracking is live for these campaigns, then pause them or cut their budget by 20%"))
    if by_role["loser"]:
        loser = by_role["loser"]
        out.append(_finding(
            "Campaign efficiency", f"{len(loser)} campaign(s) cost far more per conversion than the rest: {_names(loser)}.",
            f"CPA above {'target' if target_cpa else 'the account average'} by more than "
            f"{(LOSER_VS_TARGET if target_cpa else LOSER_VS_REFERENCE) - 1:.0%}", "confirmed by data", "high",
            "Cut their budget by 20% and move it to the best campaign; re-read CPA in 7 days"))
    if totals["ctr"] < WEAK_CTR and totals["impressions"] >= 1000:
        out.append(_finding(
            "Traffic quality", f"Overall CTR is {totals['ctr']:.2f}%: the ads are not earning the click.",
            f"{totals['clicks']:,.0f} clicks on {totals['impressions']:,.0f} impressions", "confirmed by data", "high",
            "Rewrite the hook or angle on the biggest campaign (not the fonts), hold the rest constant, read CTR in 7 days"))
    top = max(rows, key=lambda r: r["cost"])
    if len(rows) > 1 and top["cost"] / spend > CONCENTRATION_RISK:
        out.append(_finding(
            "Spend concentration", f"{top['name']} takes {top['cost'] / spend:.0%} of spend: one campaign carries the account.",
            f"{top['cost']:,.2f} of {spend:,.2f}", "confirmed by data", "medium",
            "Keep it, but start a second campaign with a different angle so one fatigue curve cannot sink the account"))
    if by_role["thin"] and len(by_role["thin"]) >= len(rows) / 2:
        out.append(_finding(
            "Evidence", f"Most campaigns have fewer than {MIN_CONV_TO_JUDGE} conversions, too few to call winners or losers.",
            f"{len(by_role['thin'])} of {len(rows)} campaigns", "confirmed by data", "medium",
            "Consolidate budget into fewer campaigns so each can collect enough conversions"))
    if target_cpa is None:
        out.append(_finding(
            "Conversion", "No target CPA given, so CPA is compared only with this account's own average.",
            f"blended CPA {totals['cpa']:.2f}", "hypothesis: verify with a real target", "certain",
            "Work out break-even with `economics breakeven`, then re-run with `--target-cpa <value>`"))
    return out


def rows_from_report(ad_report: dict[str, Any]) -> list[dict[str, Any]]:
    """Parsed report rows (cells may be None) -> clean numeric rows for analyse()."""
    return [{"name": r["name"], "status": r.get("status", ""), "cost": r.get("cost") or 0.0,
             "impressions": r.get("impressions") or 0.0, "clicks": r.get("clicks") or 0.0,
             "conversions": r.get("conversions") or 0.0} for r in ad_report["rows"]]


def analyse(rows: list[dict[str, Any]], target_cpa: float | None = None,
            results_based: bool = False) -> dict[str, Any]:
    """rows: campaign dicts with name, cost, impressions, clicks, conversions. Only rows with spend are judged.

    results_based: conversions came from Meta's "Results" column, which mixes objectives (reach, clicks, messages,
    purchases), so no campaign is called a winner on it."""
    live = [dict(r) for r in rows if r["cost"] > 0]
    totals = _totals(live)
    ref = target_cpa or totals["cpa"]
    for r in live:
        r["role"] = _role(r, ref, target_cpa is not None)
        if results_based and r["role"] == "winner":
            r["role"] = "ok"
        r["share"] = r["cost"] / totals["cost"] if totals["cost"] else 0.0
    by_role = {k: [r for r in live if r["role"] == k] for k in ("waste", "loser", "winner", "thin", "ok", "unjudged")}
    findings = _findings(totals, by_role, live, target_cpa) if live else []
    if results_based and live:
        findings.append(_finding(
            "Evidence", "Conversions come from Meta's Results column, which counts a different thing per campaign objective.",
            "Results can be reach, clicks, messages or purchases", "confirmed by data", "medium",
            "Export with a purchase or lead column (or check Result indicator) before scaling any campaign"))
    return {"totals": totals, "campaigns": sorted(live, key=lambda r: r["cost"], reverse=True), "by_role": by_role,
            "findings": findings, "score": _score(live, totals, target_cpa) if live else None,
            "target_cpa": target_cpa, "skipped_no_spend": len(rows) - len(live)}
