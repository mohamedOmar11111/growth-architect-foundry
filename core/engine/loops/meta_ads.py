"""growth_engine.loops.meta_ads — Meta (Facebook/Instagram) Ads performance
check, tenant-generic. Same shape as ad_intel.py deliberately — one proven
pattern, two ad platforms, not two different architectures to maintain.

Zero tenant-specific values. Everything comes from the injected
TenantContext: credentials, ad account id, output paths.

Read-only. Never modifies the live account — same rule as every other loop
(see architecture.md, domain/meta-ads/README.md).

Meta Marketing API accessed via raw REST (requests, already a kernel
dependency) — no facebook-business SDK dependency added, consistent with
agent_shim.py's approach of raw HTTP over vendor SDKs where the API is
simple enough not to need one.
"""

from __future__ import annotations

import datetime

import requests

from tenant import TenantContext
from utils import append_log, refresh_graph
from signals import write_signal, read_signals
from precedent import find_duplicate

GRAPH_API_VERSION = "v21.0"
BUDGET_BURN_THRESHOLD = 0.70
CONTENT_OPPORTUNITY_CTR = 3.0  # Meta's organic CTR baseline runs lower than Google Search's
CONTENT_OPPORTUNITY_MIN_CLICKS = 20
# Meta's insights `actions` array has no single canonical "conversion" type —
# it lists every action type that fired (link_click, lead, purchase, etc).
# This is a judgment call on which action_types count as a real conversion
# for alerting purposes, not a platform-defined constant — revisit per
# tenant if their actual conversion event differs from these.
CONVERSION_EVENTS = {"lead", "purchase", "complete_registration", "messaging_conversation_started_7d"}


def _canonical_action(action_type: str) -> str:
    """Strip Meta's prefixes so 'offsite_conversion.fb_pixel_purchase', 'omni_purchase' and
    'purchase' all map to 'purchase'; 'lead_grouped' maps to 'lead'."""
    for prefix in ("offsite_conversion.fb_pixel_", "offsite_conversion.", "onsite_conversion.", "omni_"):
        if action_type.startswith(prefix):
            action_type = action_type[len(prefix):]
            break
    return "lead" if action_type == "lead_grouped" else action_type


def count_conversions(actions: list[dict]) -> float:
    """Sum real conversions from a Meta `actions` array without double counting.

    Meta reports the same event under several action_types (e.g. 'purchase' AND
    'offsite_conversion.fb_pixel_purchase'), so take the max per canonical event, then sum events.
    Messaging campaigns count 'messaging_conversation_started_7d' as their conversion."""
    best: dict[str, float] = {}
    for a in actions or []:
        name = _canonical_action(a.get("action_type", ""))
        if name in CONVERSION_EVENTS:
            best[name] = max(best.get(name, 0.0), float(a["value"]))
    return sum(best.values())


def _fetch_campaigns(access_token: str, ad_account_id: str) -> dict[str, dict]:
    """All campaigns with delivery status + budget, regardless of spend."""
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/act_{ad_account_id}/campaigns"
    params = {
        "fields": "id,name,status,daily_budget,lifetime_budget",
        "access_token": access_token,
        "limit": 200,
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    attrs: dict[str, dict] = {}
    for row in data.get("data", []):
        budget_micros = row.get("daily_budget") or row.get("lifetime_budget") or "0"
        attrs[row["id"]] = {
            "name": row["name"],
            "status": row["status"],
            # Meta returns budget as a string, in account currency's minor
            # unit (cents for USD) — dividing by 100 assumes a 2-decimal
            # currency. Tenants on a 0-decimal or 3-decimal currency need
            # this adjusted; not detected automatically here.
            "budget": int(budget_micros) / 100,
        }
    return attrs


def _fetch_insights(access_token: str, ad_account_id: str) -> list[dict]:
    """Last-7-day + today's insight rows, per campaign, per day — mirrors
    ad_intel.py's _fetch_metrics shape so _aggregate/_check_alerts can stay
    structurally similar between the two platforms."""
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/act_{ad_account_id}/insights"
    params = {
        "level": "campaign",
        "fields": "campaign_id,impressions,clicks,spend,actions",
        "time_range": "{'since':'" + _n_days_ago(7) + "','until':'" + _today() + "'}",
        "time_increment": 1,
        "access_token": access_token,
        "limit": 500,
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    rows: list[dict] = []
    for row in data.get("data", []):
        conversions = count_conversions(row.get("actions", []))
        rows.append({
            "campaign_id": row["campaign_id"],
            "date": row.get("date_start", _today()),
            "impressions": int(row.get("impressions", 0)),
            "clicks": int(row.get("clicks", 0)),
            "spend": float(row.get("spend", 0)),
            "conversions": conversions,
        })
    return rows


def _today() -> str:
    return datetime.date.today().isoformat()


def _n_days_ago(n: int) -> str:
    return (datetime.date.today() - datetime.timedelta(days=n)).isoformat()


def _aggregate(insight_rows: list[dict], attrs: dict[str, dict], campaign_id: str) -> dict:
    today = _today()
    rows = [r for r in insight_rows if r["campaign_id"] == campaign_id]

    total_impressions = sum(r["impressions"] for r in rows)
    total_clicks = sum(r["clicks"] for r in rows)
    total_spend = sum(r["spend"] for r in rows)
    total_conversions = sum(r["conversions"] for r in rows)
    today_spend = sum(r["spend"] for r in rows if r["date"] == today)

    a = attrs.get(campaign_id, {})
    budget = a.get("budget", 0)
    ctr = (total_clicks / total_impressions * 100) if total_impressions else 0.0
    cpa = (total_spend / total_conversions) if total_conversions else None

    return {
        "name": a.get("name", campaign_id),
        "status": a.get("status", "UNKNOWN"),
        "budget": budget,
        "today_spend": today_spend,
        "impressions_7d": total_impressions,
        "clicks_7d": total_clicks,
        "spend_7d": total_spend,
        "conversions_7d": total_conversions,
        "ctr_7d": ctr,
        "cpa_7d": cpa,
    }


def _check_alerts(summary: dict) -> list[str]:
    alerts: list[str] = []
    if summary["status"] == "ACTIVE" and summary["spend_7d"] == 0:
        alerts.append(
            f"ZERO SPEND — {summary['name']} is ACTIVE with zero spend over "
            "the last 7 days. Check ad review status and audience size."
        )
    if summary["budget"] > 0:
        burn_ratio = summary["today_spend"] / summary["budget"]
        if burn_ratio > BUDGET_BURN_THRESHOLD:
            alerts.append(
                f"BUDGET BURN — {summary['name']} has spent "
                f"{burn_ratio * 100:.0f}% of today's daily budget already."
            )
    return alerts


def _format_report(tenant: TenantContext, summaries: dict[str, dict], alerts: list[str]) -> str:
    now = datetime.datetime.now()
    lines = [
        f"# {tenant.name} — Meta Ads Daily Check — {now.strftime('%Y-%m-%d %H:%M')}",
        "",
        "Scope: all campaigns on this tenant's Meta Ads account. Read-only, "
        "no live changes.",
        "",
        "## Alerts",
    ]
    lines.extend(f"- {a}" for a in alerts) if alerts else lines.append("None.")
    lines += [
        "",
        "## Campaign Summary (last 7 days)",
        "| Campaign | Status | Daily Budget | Today's Spend | Impr. | Clicks | "
        "CTR | Spend | Conversions | CPA |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in summaries.values():
        cpa_str = f"{s['cpa_7d']:.2f}" if s["cpa_7d"] is not None else "—"
        lines.append(
            f"| {s['name']} | {s['status']} | {s['budget']:.2f} | "
            f"{s['today_spend']:.2f} | {s['impressions_7d']:,} | "
            f"{s['clicks_7d']:,} | {s['ctr_7d']:.2f}% | {s['spend_7d']:.2f} | "
            f"{s['conversions_7d']:.1f} | {cpa_str} |"
        )
    return "\n".join(lines)


def _signal_content_opportunities(tenant: TenantContext, summaries: dict[str, dict]) -> list:
    """Same content-idea handoff + dedup pattern as ad_intel.py — see that
    file's docstring for why the dedup check exists (a campaign staying hot
    across many 6h runs would otherwise spam near-identical signals)."""
    pending = [
        {"_path": sig["_path"], "summary_line": sig["_body"].split("\n\n", 1)[0].replace("## Summary\n", "")}
        for sig in read_signals(tenant, type_="content-idea", unprocessed_only=True)
    ]
    written = []
    for s in summaries.values():
        if s["ctr_7d"] < CONTENT_OPPORTUNITY_CTR or s["clicks_7d"] < CONTENT_OPPORTUNITY_MIN_CLICKS:
            continue

        candidate_text = f"Campaign '{s['name']}' is converting attention well"
        if find_duplicate(candidate_text, pending, text_key="summary_line") is not None:
            continue

        path = write_signal(
            tenant,
            loop="meta-ads",
            source="ads-platform",
            type_="content-idea",
            priority="medium",
            action_needed=True,
            summary=(
                f"Campaign '{s['name']}' is converting attention well: "
                f"{s['ctr_7d']:.2f}% CTR over {s['clicks_7d']:,} clicks "
                "(last 7 days, Meta)."
            ),
            detail=(
                f"Meta Ads campaign '{s['name']}' (tenant: {tenant.name}) "
                f"logged {s['ctr_7d']:.2f}% CTR on {s['impressions_7d']:,} "
                f"impressions / {s['clicks_7d']:,} clicks over the last 7 "
                f"days, {s['spend_7d']:.2f} spent, "
                f"{s['conversions_7d']:.1f} conversions. Above the "
                f"{CONTENT_OPPORTUNITY_CTR}% CTR / "
                f"{CONTENT_OPPORTUNITY_MIN_CLICKS}-click content-opportunity "
                "threshold for this platform."
            ),
            suggested_action=(
                f"Draft a supporting organic post/reel that expands on the "
                f"'{s['name']}' ad angle — same audience intent, no paid "
                "spend required to test it organically."
            ),
            slug=f"{tenant.name}-meta-content-opportunity-{s['name']}",
        )
        written.append(path)
    return written


def run(tenant: TenantContext) -> int:
    access_token, ad_account_id = tenant.require("META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID")

    attrs = _fetch_campaigns(access_token, ad_account_id)
    insight_rows = _fetch_insights(access_token, ad_account_id)
    summaries = {cid: _aggregate(insight_rows, attrs, cid) for cid in attrs}

    all_alerts: list[str] = []
    for s in summaries.values():
        all_alerts.extend(_check_alerts(s))

    report = _format_report(tenant, summaries, all_alerts)
    now = datetime.datetime.now()
    report_path = tenant.reports_dir / f"{now.strftime('%Y-%m-%d-%H')}-meta-ads-report.md"
    report_path.write_text(report, encoding="utf-8")

    print(f"[{tenant.name}] meta-ads: report written -> {report_path}")
    print(f"[{tenant.name}] meta-ads: {len(all_alerts)} alert(s)")
    for a in all_alerts:
        print(f"  - {a}")

    signal_paths = _signal_content_opportunities(tenant, summaries)
    print(f"[{tenant.name}] meta-ads: {len(signal_paths)} content-idea signal(s) written")

    alert_note = f"{len(all_alerts)} alert(s)" if all_alerts else "no alerts"
    append_log(
        tenant.name, "meta-ads",
        f"Automated read-only Meta Ads check via Growth Engine, {alert_note}, "
        f"{len(signal_paths)} content-idea signal(s) written",
        report_path,
    )
    refresh_graph(tenant.root)

    return 0
