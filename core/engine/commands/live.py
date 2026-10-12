"""growth_engine.commands.live — live ad account operations.

This module is the ONLY place in the command layer that talks to external
APIs. Every other command reads from files on disk — this one reads from
(and writes to) live ad accounts.

Safety model (non-negotiable):
  - READ verbs (pull, optimize): same as every command — fail loud if creds
    missing, never modify anything.
  - WRITE verbs (pause, budget): require --confirm flag. The exact change is
    printed BEFORE the write happens. No --confirm = no write, full stop.
    Budget changes capped at 20% per action (rule 3: respect learning).

Platform support: Google Ads (via google-ads SDK, same as ad_intel.py) and
Meta (via raw REST, same as meta_ads.py). New platforms added by adding a
fetcher + mutator pair, not by changing the command logic.
"""

from __future__ import annotations

import datetime
import json
import sys
from typing import Any

from tenant import TenantContext, TenantConfigError
from utils import append_log

# ── Google Ads integration (reuses ad_intel.py patterns) ────────────────────

def _google_fetch_campaigns(tenant: TenantContext) -> dict[str, dict]:
    """Pull live Google Ads campaign data. Returns empty dict if creds missing."""
    try:
        tenant.require(
            "GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET",
            "GOOGLE_ADS_REFRESH_TOKEN", "GOOGLE_ADS_DEVELOPER_TOKEN",
            "GOOGLE_ADS_CUSTOMER_ID",
        )
    except TenantConfigError:
        return {}

    try:
        from google.ads.googleads.client import GoogleAdsClient
        from google.ads.googleads.errors import GoogleAdsException
    except ImportError:
        print("WARNING: google-ads SDK not installed — skipping Google Ads pull.",
              file=sys.stderr)
        return {}

    config = {
        "client_id": tenant.env["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": tenant.env["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": tenant.env["GOOGLE_ADS_REFRESH_TOKEN"],
        "developer_token": tenant.env["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "use_proto_plus": True,
    }
    try:
        client = GoogleAdsClient.load_from_dict(config)
    except Exception as e:
        print(f"WARNING: Google Ads client init failed (likely placeholder creds): {e}",
              file=sys.stderr)
        return {}

    customer_id = tenant.env["GOOGLE_ADS_CUSTOMER_ID"]
    ga_service = client.get_service("GoogleAdsService")

    try:
        response = ga_service.search(
            customer_id=customer_id,
            query="""
                SELECT campaign.id, campaign.name, campaign.status,
                       campaign_budget.amount_micros,
                       metrics.impressions, metrics.clicks,
                       metrics.cost_micros, metrics.conversions,
                       segments.date
                FROM campaign
                WHERE campaign.status IN ('ENABLED', 'PAUSED')
                  AND segments.date DURING LAST_7_DAYS
            """,
        )
        campaigns: dict[str, dict] = {}
        for row in response:
            cid = str(row.campaign.id)
            if cid not in campaigns:
                campaigns[cid] = {
                    "id": cid,
                    "name": row.campaign.name,
                    "status": row.campaign.status.name,
                    "budget": row.campaign_budget.amount_micros / 1_000_000,
                    "platform": "google",
                    "impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0.0,
                }
            c = campaigns[cid]
            c["impressions"] += row.metrics.impressions
            c["clicks"] += row.metrics.clicks
            c["cost"] += row.metrics.cost_micros / 1_000_000
            c["conversions"] += row.metrics.conversions
        for c in campaigns.values():
            c["ctr"] = (c["clicks"] / c["impressions"] * 100) if c["impressions"] else 0.0
            c["cpa"] = (c["cost"] / c["conversions"]) if c["conversions"] else None
        return campaigns
    except GoogleAdsException as e:
        print(f"WARNING: Google Ads API error: {e}", file=sys.stderr)
        return {}


def _google_pause_campaign(tenant: TenantContext, campaign_id: str) -> tuple[bool, str]:
    """Pause a Google Ads campaign. Returns (success, message)."""
    from google.ads.googleads.client import GoogleAdsClient

    config = {
        "client_id": tenant.env["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": tenant.env["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": tenant.env["GOOGLE_ADS_REFRESH_TOKEN"],
        "developer_token": tenant.env["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "use_proto_plus": True,
    }
    client = GoogleAdsClient.load_from_dict(config)
    customer_id = tenant.env["GOOGLE_ADS_CUSTOMER_ID"]

    campaign_service = client.get_service("CampaignService")
    campaign_operation = client.get_type("CampaignOperation")
    campaign = campaign_operation.update
    campaign.resource_name = campaign_service.campaign_path(customer_id, campaign_id)
    campaign.status = client.enums.CampaignStatusEnum.PAUSED
    field_mask = client.get_type("FieldMask")
    field_mask.paths.append("status")
    campaign_operation.update_mask.CopyFrom(field_mask)

    try:
        response = campaign_service.mutate_campaigns(
            customer_id=customer_id, operations=[campaign_operation],
        )
        return True, f"Google Ads campaign {campaign_id} paused: {response.results[0].resource_name}"
    except Exception as e:
        return False, f"Failed to pause Google Ads campaign {campaign_id}: {e}"


def _google_update_budget(tenant: TenantContext, campaign_id: str,
                          new_budget: float) -> tuple[bool, str]:
    """Update a Google Ads campaign budget. Returns (success, message)."""
    from google.ads.googleads.client import GoogleAdsClient

    config = {
        "client_id": tenant.env["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": tenant.env["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": tenant.env["GOOGLE_ADS_REFRESH_TOKEN"],
        "developer_token": tenant.env["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "use_proto_plus": True,
    }
    client = GoogleAdsClient.load_from_dict(config)
    customer_id = tenant.env["GOOGLE_ADS_CUSTOMER_ID"]

    # Get the campaign's budget resource name
    ga_service = client.get_service("GoogleAdsService")
    response = ga_service.search(
        customer_id=customer_id,
        query=f"SELECT campaign.campaign_budget FROM campaign WHERE campaign.id = {campaign_id}",
    )
    budget_resource = None
    for row in response:
        budget_resource = row.campaign.campaign_budget
        break
    if not budget_resource:
        return False, f"Campaign {campaign_id} not found or has no budget."

    budget_service = client.get_service("CampaignBudgetService")
    budget_operation = client.get_type("CampaignBudgetOperation")
    budget_op = budget_operation.update
    budget_op.resource_name = budget_resource
    budget_op.amount_micros = int(new_budget * 1_000_000)
    field_mask = client.get_type("FieldMask")
    field_mask.paths.append("amount_micros")
    budget_operation.update_mask.CopyFrom(field_mask)

    try:
        result = budget_service.mutate_campaign_budgets(
            customer_id=customer_id, operations=[budget_operation],
        )
        return True, f"Google Ads budget updated to {new_budget:.2f}: {result.results[0].resource_name}"
    except Exception as e:
        return False, f"Failed to update budget: {e}"


# ── Meta Ads integration (reuses meta_ads.py patterns) ──────────────────────

GRAPH_API_VERSION = "v21.0"
MAX_BUDGET_CHANGE_PCT = 0.20  # rule 3: respect learning


def _meta_fetch_campaigns(tenant: TenantContext) -> dict[str, dict]:
    """Pull live Meta Ads campaign data. Returns empty dict if creds missing."""
    try:
        access_token, ad_account_id = tenant.require("META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID")
    except TenantConfigError:
        return {}

    try:
        import requests
    except ImportError:
        print("WARNING: requests not installed — skipping Meta Ads pull.", file=sys.stderr)
        return {}

    try:
        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/act_{ad_account_id}/campaigns"
        params = {
            "fields": "id,name,status,daily_budget,lifetime_budget",
            "access_token": access_token, "limit": 200,
        }
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"WARNING: Meta Ads API call failed (likely placeholder creds): {e}",
              file=sys.stderr)
        return {}

    campaigns: dict[str, dict] = {}
    for row in resp.json().get("data", []):
        budget_cents = row.get("daily_budget") or row.get("lifetime_budget") or "0"
        campaigns[row["id"]] = {
            "id": row["id"],
            "name": row["name"],
            "status": row["status"],
            "budget": int(budget_cents) / 100,
            "platform": "meta",
            "impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0.0,
        }

    # Fetch insights
    import datetime as dt
    since = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    until = dt.date.today().isoformat()
    insights_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/act_{ad_account_id}/insights"
    insights_params = {
        "level": "campaign",
        "fields": "campaign_id,impressions,clicks,spend,actions",
        "time_range": json.dumps({"since": since, "until": until}),
        "time_increment": 1,
        "access_token": access_token, "limit": 500,
    }
    resp2 = requests.get(insights_url, params=insights_params, timeout=30)
    resp2.raise_for_status()

    from loops.meta_ads import CONVERSION_ACTION_TYPES
    for row in resp2.json().get("data", []):
        cid = row["campaign_id"]
        if cid not in campaigns:
            continue
        c = campaigns[cid]
        c["impressions"] += int(row.get("impressions", 0))
        c["clicks"] += int(row.get("clicks", 0))
        c["cost"] += float(row.get("spend", 0))
        c["conversions"] += sum(
            float(a["value"]) for a in row.get("actions", [])
            if a.get("action_type") in CONVERSION_ACTION_TYPES
        )

    for c in campaigns.values():
        c["ctr"] = (c["clicks"] / c["impressions"] * 100) if c["impressions"] else 0.0
        c["cpa"] = (c["cost"] / c["conversions"]) if c["conversions"] else None

    return campaigns


def _meta_pause_campaign(tenant: TenantContext, campaign_id: str) -> tuple[bool, str]:
    """Pause a Meta campaign. Returns (success, message)."""
    import requests

    access_token, _ = tenant.require("META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID")
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{campaign_id}"
    resp = requests.post(url, params={"access_token": access_token},
                         json={"status": "PAUSED"}, timeout=30)
    if resp.status_code == 200:
        return True, f"Meta campaign {campaign_id} paused."
    return False, f"Failed to pause Meta campaign {campaign_id}: {resp.text}"


def _meta_update_budget(tenant: TenantContext, campaign_id: str,
                        new_budget: float) -> tuple[bool, str]:
    """Update a Meta campaign daily budget. Budget in cents."""
    import requests

    access_token, _ = tenant.require("META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID")
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{campaign_id}"
    resp = requests.post(url, params={"access_token": access_token},
                         json={"daily_budget": int(new_budget * 100)}, timeout=30)
    if resp.status_code == 200:
        return True, f"Meta campaign {campaign_id} budget updated to {new_budget:.2f}."
    return False, f"Failed to update Meta budget: {resp.text}"


# ── Unified fetch ───────────────────────────────────────────────────────────

def _fetch_all(tenant: TenantContext) -> dict[str, dict]:
    """Pull from every configured platform. Keys are prefixed with platform."""
    all_campaigns: dict[str, dict] = {}
    google = _google_fetch_campaigns(tenant)
    for cid, c in google.items():
        all_campaigns[f"google:{cid}"] = c
    meta = _meta_fetch_campaigns(tenant)
    for cid, c in meta.items():
        all_campaigns[f"meta:{cid}"] = c
    return all_campaigns


def _parse_platform_key(key: str) -> tuple[str, str]:
    """Split 'google:12345' into ('google', '12345')."""
    platform, cid = key.split(":", 1)
    return platform, cid


# ── Command verbs ───────────────────────────────────────────────────────────

def _cmd_pull(tenant: TenantContext, campaigns: dict[str, dict]) -> int:
    now = datetime.datetime.now()
    if not campaigns:
        print(f"[{tenant.name}] campaigns pull: no campaigns found. Check credentials "
              "in .env (Google Ads and/or Meta).")
        return 0

    lines = [
        f"# {tenant.name} — Live Campaigns — {now.strftime('%Y-%m-%d %H:%M')}",
        "",
        f"**Source:** live API pull ({len(campaigns)} campaign(s) across "
        f"{len({v['platform'] for v in campaigns.values()})} platform(s))",
        "",
        "| Platform | Campaign | Status | Budget | Spend (7d) | Impr. | Clicks | CTR | Conv. | CPA |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for key, c in sorted(campaigns.items(), key=lambda x: x[1]["cost"], reverse=True):
        platform, cid = _parse_platform_key(key)
        cpa_str = f"{c['cpa']:.2f}" if c["cpa"] is not None else "—"
        lines.append(
            f"| {platform} | {c['name']} | {c['status']} | {c['budget']:.2f} | "
            f"{c['cost']:.2f} | {c['impressions']:,} | {c['clicks']:,} | "
            f"{c['ctr']:.2f}% | {c['conversions']:.0f} | {cpa_str} |"
        )

    report = "\n".join(lines)
    report_path = tenant.reports_dir / f"{now.strftime('%Y-%m-%d-%H')}-live-pull.md"
    report_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n[{tenant.name}] campaigns pull: {len(campaigns)} campaign(s) pulled -> {report_path}")
    append_log(tenant.name, "campaigns-pull",
               f"Live pull: {len(campaigns)} campaign(s) from "
               f"{len({v['platform'] for v in campaigns.values()})} platform(s)",
               report_path)
    return 0


def _cmd_optimize(tenant: TenantContext, campaigns: dict[str, dict],
                  opts: dict) -> int:
    now = datetime.datetime.now()
    target_cpa_raw = opts.get("target_cpa") or tenant.env.get("TARGET_CPA")
    target_cpa = float(target_cpa_raw) if target_cpa_raw else None

    if not campaigns:
        print(f"[{tenant.name}] campaigns optimize: no campaigns to analyze.")
        return 0

    lines = [
        f"# {tenant.name} — Optimize Recommendations — {now.strftime('%Y-%m-%d %H:%M')}",
        "",
        "Every recommendation below is an estimate. No changes are made "
        "without --confirm. Budget changes are capped at 20% per action "
        "(rule: respect learning).",
        "",
    ]

    if target_cpa:
        lines.append(f"**Target CPA:** {target_cpa:.2f}")
    else:
        lines.append("**Target CPA:** not set — optimization is spend-based only. "
                     "Set TARGET_CPA in .env or pass --target-cpa for CPA-aware recommendations.")
    lines.append("")

    recommendations: list[dict[str, Any]] = []

    for key, c in sorted(campaigns.items(), key=lambda x: x[1]["cost"], reverse=True):
        platform, cid = _parse_platform_key(key)
        action = "hold"
        reason = ""
        budget_change = 0.0

        if c["status"] == "PAUSED":
            action = "hold"
            reason = "already paused"
        elif c["cost"] == 0 and c["status"] == "ENABLED":
            action = "investigate"
            reason = "ENABLED with zero spend — check ad approval status"
        elif c["conversions"] == 0 and c["cost"] > 0:
            action = "reduce"
            reason = f"spend {c['cost']:.2f} with zero conversions — tracking or offer problem"
            budget_change = -c["budget"] * 0.20
        elif target_cpa and c["cpa"] and c["cpa"] > target_cpa * 1.5:
            action = "reduce"
            reason = f"CPA {c['cpa']:.2f} is {c['cpa']/target_cpa:.1f}× target {target_cpa:.2f}"
            budget_change = -c["budget"] * 0.20
        elif target_cpa and c["cpa"] and c["cpa"] < target_cpa * 0.8:
            action = "scale"
            reason = f"CPA {c['cpa']:.2f} is below target {target_cpa:.2f} — room to scale"
            budget_change = c["budget"] * 0.15
        elif c["ctr"] < 1.0 and c["impressions"] > 1000:
            action = "test"
            reason = f"CTR {c['ctr']:.2f}% is weak on {c['impressions']:,} impressions — rewrite the angle"

        recommendations.append({
            "platform": platform, "name": c["name"], "id": cid,
            "action": action, "reason": reason,
            "current_budget": c["budget"],
            "proposed_budget": c["budget"] + budget_change,
            "budget_change": budget_change,
        })

    lines += [
        "## Recommendations",
        "| Campaign | Action | Reason | Current Budget | Proposed Budget | Change |",
        "|---|---|---|---|---|---|",
    ]
    for r in recommendations:
        change_str = f"{r['budget_change']:+.2f}" if r["budget_change"] else "—"
        proposed_str = f"{r['proposed_budget']:.2f}" if r["budget_change"] else "—"
        lines.append(
            f"| {r['platform']}:{r['name']} | **{r['action'].upper()}** | "
            f"{r['reason']} | {r['current_budget']:.2f} | {proposed_str} | {change_str} |"
        )

    scale_count = sum(1 for r in recommendations if r["action"] == "scale")
    reduce_count = sum(1 for r in recommendations if r["action"] == "reduce")
    lines += [
        "",
        "## Summary",
        f"- **Scale:** {scale_count} campaign(s)",
        f"- **Reduce:** {reduce_count} campaign(s)",
        f"- **Hold:** {len(recommendations) - scale_count - reduce_count} campaign(s)",
        "",
        "## Next Step",
        "Review the recommendations above. To apply budget changes, run:",
        "`foundry campaigns budget --client <t> --campaign-id <id> --new-budget <value> --confirm`",
        "",
        "No changes are made automatically. Every write requires --confirm.",
    ]

    report = "\n".join(lines)
    report_path = tenant.reports_dir / f"{now.strftime('%Y-%m-%d-%H')}-optimize.md"
    report_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n[{tenant.name}] campaigns optimize: report written -> {report_path}")
    append_log(tenant.name, "campaigns-optimize",
               f"Optimize: {scale_count} scale, {reduce_count} reduce, "
               f"{len(recommendations) - scale_count - reduce_count} hold",
               report_path)
    return 0


def _cmd_pause(tenant: TenantContext, campaigns: dict[str, dict],
              opts: dict) -> int:
    campaign_key = opts.get("campaign_id")
    if not campaign_key:
        print("ERROR: --campaign-id is required for pause (e.g., 'google:12345' or 'meta:67890').",
              file=sys.stderr)
        return 2

    if campaign_key not in campaigns:
        available = ", ".join(sorted(campaigns.keys()))
        print(f"ERROR: campaign '{campaign_key}' not found. Available: {available}",
              file=sys.stderr)
        return 2

    c = campaigns[campaign_key]
    platform, cid = _parse_platform_key(campaign_key)

    if c["status"] == "PAUSED":
        print(f"Campaign '{c['name']}' is already paused.")
        return 0

    # Show the exact change BEFORE executing
    print(f"⚠️  ABOUT TO PAUSE: {platform} campaign '{c['name']}' (ID: {cid})")
    print(f"   Current status: {c['status']}")
    print(f"   7-day spend: {c['cost']:.2f}")
    print(f"   7-day conversions: {c['conversions']:.0f}")

    if not opts.get("confirm"):
        print("\n   No --confirm flag passed. No changes made.")
        print("   To execute: add --confirm to the command.")
        return 0

    if platform == "google":
        ok, msg = _google_pause_campaign(tenant, cid)
    elif platform == "meta":
        ok, msg = _meta_pause_campaign(tenant, cid)
    else:
        print(f"ERROR: unsupported platform '{platform}'", file=sys.stderr)
        return 2

    print(f"\n{'✅' if ok else '❌'} {msg}")
    if ok:
        append_log(tenant.name, "campaigns-pause",
                   f"Paused {platform} campaign '{c['name']}' (ID: {cid})",
                   tenant.reports_dir / "pause-log.md")
    return 0 if ok else 1


def _cmd_budget(tenant: TenantContext, campaigns: dict[str, dict],
               opts: dict) -> int:
    campaign_key = opts.get("campaign_id")
    new_budget_raw = opts.get("new_budget")

    if not campaign_key or new_budget_raw is None:
        print("ERROR: --campaign-id and --new-budget are required for budget changes.",
              file=sys.stderr)
        return 2

    try:
        new_budget = float(new_budget_raw)
    except (TypeError, ValueError):
        print(f"ERROR: --new-budget must be a number, got '{new_budget_raw}'.", file=sys.stderr)
        return 2

    if campaign_key not in campaigns:
        available = ", ".join(sorted(campaigns.keys()))
        print(f"ERROR: campaign '{campaign_key}' not found. Available: {available}",
              file=sys.stderr)
        return 2

    c = campaigns[campaign_key]
    platform, cid = _parse_platform_key(campaign_key)
    current = c["budget"]
    change_pct = abs(new_budget - current) / current if current else 0

    # Show the exact change BEFORE executing
    print(f"⚠️  ABOUT TO CHANGE BUDGET: {platform} campaign '{c['name']}' (ID: {cid})")
    print(f"   Current budget: {current:.2f}")
    print(f"   Proposed budget: {new_budget:.2f}")
    print(f"   Change: {new_budget - current:+.2f} ({change_pct * 100:+.1f}%)")

    if change_pct > MAX_BUDGET_CHANGE_PCT:
        print(f"\n   ❌ BLOCKED: change is {change_pct * 100:.1f}% — exceeds the "
              f"{MAX_BUDGET_CHANGE_PCT * 100:.0f}% cap per action (rule: respect learning).")
        print(f"   Maximum allowed change: {current * (1 + MAX_BUDGET_CHANGE_PCT):.2f} "
              f"or {current * (1 - MAX_BUDGET_CHANGE_PCT):.2f}")
        return 2

    if not opts.get("confirm"):
        print("\n   No --confirm flag passed. No changes made.")
        print("   To execute: add --confirm to the command.")
        return 0

    if platform == "google":
        ok, msg = _google_update_budget(tenant, cid, new_budget)
    elif platform == "meta":
        ok, msg = _meta_update_budget(tenant, cid, new_budget)
    else:
        print(f"ERROR: unsupported platform '{platform}'", file=sys.stderr)
        return 2

    print(f"\n{'✅' if ok else '❌'} {msg}")
    if ok:
        append_log(tenant.name, "campaigns-budget",
                   f"Budget {platform} campaign '{c['name']}' (ID: {cid}): "
                   f"{current:.2f} -> {new_budget:.2f} ({change_pct * 100:+.1f}%)",
                   tenant.reports_dir / "budget-log.md")
    return 0 if ok else 1


# ── Dispatch ────────────────────────────────────────────────────────────────

def run(tenant: TenantContext, opts: dict | None = None) -> int:
    opts = opts or {}
    verb = opts.get("verb", "pull")

    # Pull live data (works for all verbs — read-only verbs need it, write
    # verbs need it to validate the campaign ID exists)
    campaigns = _fetch_all(tenant)

    if verb == "pull":
        return _cmd_pull(tenant, campaigns)
    elif verb == "optimize":
        return _cmd_optimize(tenant, campaigns, opts)
    elif verb == "pause":
        return _cmd_pause(tenant, campaigns, opts)
    elif verb == "budget":
        return _cmd_budget(tenant, campaigns, opts)
    else:
        print(f"ERROR: unknown live verb '{verb}'", file=sys.stderr)
        return 1