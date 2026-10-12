"""growth_engine.loops.ad_intel — Google Ads performance check, tenant-generic.

Zero tenant-specific values. Everything comes from the injected TenantContext:
credentials, customer_id, output paths. Ported from the original hardcoded
a single-account script (2 hardcoded campaign
IDs) — this version discovers campaigns dynamically per tenant account, so
there is nothing left to hardcode even as new tenants come online.

Read-only. Never modifies the live account — same rule as every other loop
(see architecture.md, domain/ad-intel/README.md).
"""

from __future__ import annotations

import datetime
import re

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from tenant import TenantContext
from utils import append_log, refresh_graph
from signals import write_signal, read_signals
from precedent import find_duplicate

_SUMMARY_SECTION_RE = re.compile(r"## Summary\n(.*?)\n\n## Detail", re.DOTALL)


def _extract_summary_line(body: str) -> str:
    """Pulls just the '## Summary' line out of a signal's body — comparing
    a short candidate phrase against a signal's FULL body (Summary+Detail+
    Suggested Action, much larger token set) dilutes Jaccard similarity
    below any reasonable threshold even for an exact-campaign duplicate.
    Comparing summary-to-summary keeps both sides the same order of
    magnitude, which is what made the dedup check actually work when
    tested (first version compared against full _body and never matched)."""
    match = _SUMMARY_SECTION_RE.search(body)
    return match.group(1) if match else body

BUDGET_BURN_THRESHOLD = 0.70
# Content-opportunity heuristic: a campaign performing well enough, on enough
# volume to not be noise, is worth telling content-engine about. Both
# thresholds are real judgment calls, not derived from a formal benchmark —
# revisit once there's enough cross-tenant history to tune them properly.
CONTENT_OPPORTUNITY_CTR = 5.0
CONTENT_OPPORTUNITY_MIN_CLICKS = 20


def _build_client(tenant: TenantContext) -> GoogleAdsClient:
    client_id, client_secret, refresh_token, developer_token = tenant.require(
        "GOOGLE_ADS_CLIENT_ID",
        "GOOGLE_ADS_CLIENT_SECRET",
        "GOOGLE_ADS_REFRESH_TOKEN",
        "GOOGLE_ADS_DEVELOPER_TOKEN",
    )
    config = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "developer_token": developer_token,
        "use_proto_plus": True,
    }
    return GoogleAdsClient.load_from_dict(config)


def _fetch_campaigns(client: GoogleAdsClient, customer_id: str) -> dict[str, dict]:
    """All ENABLED/PAUSED campaigns on the account — always returns a row per
    campaign regardless of delivery, unlike the metrics query below."""
    ga_service = client.get_service("GoogleAdsService")
    query = """
        SELECT campaign.id, campaign.name, campaign.status,
               campaign_budget.amount_micros
        FROM campaign
        WHERE campaign.status IN ('ENABLED', 'PAUSED')
    """
    attrs: dict[str, dict] = {}
    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        for row in response:
            attrs[str(row.campaign.id)] = {
                "name": row.campaign.name,
                "status": row.campaign.status.name,
                "budget_micros": row.campaign_budget.amount_micros,
            }
    except GoogleAdsException as ex:
        raise RuntimeError(f"Google Ads API error (attributes): {ex}") from ex
    return attrs


def _fetch_metrics(client: GoogleAdsClient, customer_id: str) -> list[dict]:
    """Last-7-day metric rows. Returns an empty list (not an error) for zero
    delivery — Google Ads reporting only emits a row per day with activity."""
    ga_service = client.get_service("GoogleAdsService")
    query = """
        SELECT campaign.id, metrics.impressions, metrics.clicks,
               metrics.cost_micros, metrics.conversions, segments.date
        FROM campaign
        WHERE segments.date DURING LAST_7_DAYS
    """
    rows: list[dict] = []
    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        for row in response:
            rows.append({
                "campaign_id": str(row.campaign.id),
                "date": row.segments.date,
                "impressions": row.metrics.impressions,
                "clicks": row.metrics.clicks,
                "cost_micros": row.metrics.cost_micros,
                "conversions": row.metrics.conversions,
            })
    except GoogleAdsException as ex:
        raise RuntimeError(f"Google Ads API error (metrics): {ex}") from ex
    return rows


def _aggregate(metric_rows: list[dict], attrs: dict[str, dict], campaign_id: str) -> dict:
    today = datetime.date.today().isoformat()
    campaign_rows = [r for r in metric_rows if r["campaign_id"] == campaign_id]

    total_impressions = sum(r["impressions"] for r in campaign_rows)
    total_clicks = sum(r["clicks"] for r in campaign_rows)
    total_cost = sum(r["cost_micros"] for r in campaign_rows) / 1_000_000
    total_conversions = sum(r["conversions"] for r in campaign_rows)
    today_cost = sum(
        r["cost_micros"] for r in campaign_rows if r["date"] == today
    ) / 1_000_000

    a = attrs.get(campaign_id, {})
    budget = a.get("budget_micros", 0) / 1_000_000
    ctr = (total_clicks / total_impressions * 100) if total_impressions else 0.0
    cpa = (total_cost / total_conversions) if total_conversions else None

    return {
        "name": a.get("name", campaign_id),
        "status": a.get("status", "UNKNOWN"),
        "budget": budget,
        "today_cost": today_cost,
        "impressions_7d": total_impressions,
        "clicks_7d": total_clicks,
        "cost_7d": total_cost,
        "conversions_7d": total_conversions,
        "ctr_7d": ctr,
        "cpa_7d": cpa,
    }


def _check_alerts(summary: dict) -> list[str]:
    alerts: list[str] = []
    if summary["status"] == "ENABLED" and summary["cost_7d"] == 0:
        alerts.append(
            f"ZERO SPEND — {summary['name']} is ENABLED with zero spend over "
            "the last 7 days. Check ad approval status and keyword eligibility."
        )
    if summary["budget"] > 0:
        burn_ratio = summary["today_cost"] / summary["budget"]
        if burn_ratio > BUDGET_BURN_THRESHOLD:
            alerts.append(
                f"BUDGET BURN — {summary['name']} has spent "
                f"{burn_ratio * 100:.0f}% of today's daily budget already."
            )
    return alerts


def _format_report(tenant: TenantContext, summaries: dict[str, dict], alerts: list[str]) -> str:
    now = datetime.datetime.now()
    lines = [
        f"# {tenant.name} — Google Ads Daily Check — {now.strftime('%Y-%m-%d %H:%M')}",
        "",
        "Scope: all ENABLED/PAUSED campaigns on this tenant's Google Ads "
        "account. Read-only, no live changes.",
        "",
        "## Alerts",
    ]
    if alerts:
        lines.extend(f"- {a}" for a in alerts)
    else:
        lines.append("None.")
    lines += [
        "",
        "## Campaign Summary (last 7 days)",
        "| Campaign | Status | Daily Budget | Today's Spend | Impr. | Clicks | "
        "CTR | Cost | Conversions | CPA |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in summaries.values():
        cpa_str = f"{s['cpa_7d']:.2f}" if s["cpa_7d"] is not None else "—"
        lines.append(
            f"| {s['name']} | {s['status']} | {s['budget']:.2f} | "
            f"{s['today_cost']:.2f} | {s['impressions_7d']:,} | "
            f"{s['clicks_7d']:,} | {s['ctr_7d']:.2f}% | {s['cost_7d']:.2f} | "
            f"{s['conversions_7d']:.1f} | {cpa_str} |"
        )
    return "\n".join(lines)


def _signal_content_opportunities(tenant: TenantContext, summaries: dict[str, dict]) -> list:
    """Writes one content-idea Signal per campaign that's converting attention
    well on real volume — this is the actual ad-intel -> content-engine
    handoff. Real data, real threshold, no fabricated finding: if nothing
    qualifies, nothing gets written.

    Dedup against already-pending signals before writing: this loop runs
    every 6h (per domain/ad-intel/README.md's cadence) recalculating a
    rolling 7-day window fresh each time, while content-engine only runs
    every 3 days. A campaign that stays above threshold for a week would
    write ~28 near-identical signals for the same campaign before
    content-engine ever processes the first one, without this check."""
    pending = [
        {"_path": sig["_path"], "summary_line": _extract_summary_line(sig["_body"])}
        for sig in read_signals(tenant, type_="content-idea", unprocessed_only=True)
    ]
    written = []
    for s in summaries.values():
        if s["ctr_7d"] < CONTENT_OPPORTUNITY_CTR:
            continue
        if s["clicks_7d"] < CONTENT_OPPORTUNITY_MIN_CLICKS:
            continue

        candidate_text = f"Campaign '{s['name']}' is converting attention well"
        duplicate = find_duplicate(candidate_text, pending, text_key="summary_line")
        if duplicate is not None:
            print(f"[{tenant.name}] ad-intel: skipping '{s['name']}' — "
                  f"already covered by pending signal "
                  f"'{duplicate['_path'].name}'")
            continue

        path = write_signal(
            tenant,
            loop="ad-intel",
            source="ads-platform",
            type_="content-idea",
            priority="medium",
            action_needed=True,
            summary=(
                f"Campaign '{s['name']}' is converting attention well: "
                f"{s['ctr_7d']:.2f}% CTR over {s['clicks_7d']:,} clicks "
                "(last 7 days)."
            ),
            detail=(
                f"Google Ads campaign '{s['name']}' (tenant: {tenant.name}) "
                f"logged {s['ctr_7d']:.2f}% CTR on {s['impressions_7d']:,} "
                f"impressions / {s['clicks_7d']:,} clicks over the last 7 "
                f"days, SAR {s['cost_7d']:.2f} spent, "
                f"{s['conversions_7d']:.1f} conversions. Above the "
                f"{CONTENT_OPPORTUNITY_CTR}% CTR / "
                f"{CONTENT_OPPORTUNITY_MIN_CLICKS}-click content-opportunity "
                "threshold — the ad angle is resonating with real search "
                "intent, which usually means there's an underserved organic "
                "content gap around the same query space."
            ),
            suggested_action=(
                f"Draft a supporting blog/social content brief that expands "
                f"on the '{s['name']}' ad angle for organic reach — same "
                "audience intent, no paid spend required to test it."
            ),
            slug=f"{tenant.name}-content-opportunity-{s['name']}",
        )
        written.append(path)
    return written


def run(tenant: TenantContext) -> int:
    (customer_id,) = tenant.require("GOOGLE_ADS_CUSTOMER_ID")
    client = _build_client(tenant)

    attrs = _fetch_campaigns(client, customer_id)
    metric_rows = _fetch_metrics(client, customer_id)
    summaries = {cid: _aggregate(metric_rows, attrs, cid) for cid in attrs}

    all_alerts: list[str] = []
    for s in summaries.values():
        all_alerts.extend(_check_alerts(s))

    report = _format_report(tenant, summaries, all_alerts)

    now = datetime.datetime.now()
    report_path = tenant.reports_dir / f"{now.strftime('%Y-%m-%d-%H')}-ad-intel-report.md"
    report_path.write_text(report, encoding="utf-8")

    print(f"[{tenant.name}] ad-intel: report written -> {report_path}")
    print(f"[{tenant.name}] ad-intel: {len(all_alerts)} alert(s)")
    for a in all_alerts:
        print(f"  - {a}")

    signal_paths = _signal_content_opportunities(tenant, summaries)
    print(f"[{tenant.name}] ad-intel: {len(signal_paths)} content-idea signal(s) written")
    for p in signal_paths:
        print(f"  - {p.name}")

    alert_note = f"{len(all_alerts)} alert(s)" if all_alerts else "no alerts"
    append_log(
        tenant.name, "ad-intel",
        f"Automated read-only Google Ads check via Growth Engine, {alert_note}, "
        f"{len(signal_paths)} content-idea signal(s) written",
        report_path,
    )
    refresh_graph(tenant.root)

    return 0
