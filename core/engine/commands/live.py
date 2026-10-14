"""growth_engine.commands.live — live ad account operations.

This module is the ONLY place in the command layer that talks to external
APIs. Every other command reads from files on disk — this one reads from
(and writes to) live ad accounts.

Safety model (non-negotiable):
  - READ verbs (pull, optimize): fail loud if a configured platform's API call
    fails — a failed pull is NEVER reported as "no campaigns". Never modify.
  - WRITE verbs (pause, budget): require --confirm AND a person typing the
    campaign key at an interactive terminal (an AI agent's shell has none, so
    it cannot self-approve). The exact change is printed BEFORE the write. A
    write is refused outright if any platform's fetch failed (stale/partial).
  - Budget changes are capped at 20% CUMULATIVE per campaign over a rolling
    7-day window (ledger in the tenant's 04_Reports/), so repeated small
    steps cannot compound past the learning-phase guardrail.

Platform support: Google Ads (google-ads SDK; MCC via GOOGLE_ADS_LOGIN_CUSTOMER_ID)
and Meta (raw REST). New platforms: add a fetcher + mutator pair.
"""

from __future__ import annotations

import datetime
import json
import math
import sys
from pathlib import Path
from typing import Any

from tenant import TenantContext, TenantConfigError
from utils import append_log, sanitize_text

GRAPH_API_VERSION = "v21.0"
MAX_BUDGET_CHANGE_PCT = 0.20  # rule 3: respect learning
EXIT_REFUSED = 3  # a safety gate refused the action (distinct from failure=1, bad input=2)
BUDGET_WINDOW_DAYS = 7
LEDGER_NAME = "budget-ledger.json"

GOOGLE_KEYS = ("GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET",
               "GOOGLE_ADS_REFRESH_TOKEN", "GOOGLE_ADS_DEVELOPER_TOKEN",
               "GOOGLE_ADS_CUSTOMER_ID")
META_KEYS = ("META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID")


def _human_approved(target: str) -> bool:
    """Live writes need a person at a terminal, whatever agent launched this.

    --confirm is just a flag, so a prompt-injected agent can add it. Agent
    tool shells run commands without a terminal, so requiring a typed answer
    on a real TTY means the user must run the write themselves. Limit: an
    agent that attaches a pseudo-terminal could still answer; keep agent
    permission prompts on for these commands too.
    """
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("\n   REFUSED: live writes must be approved by a person at a terminal.\n"
              "   This command was not run from an interactive terminal (an AI agent's\n"
              "   shell is not one). Run the same command yourself in a terminal.",
              file=sys.stderr)
        return False
    try:
        typed = input(f"   Type the campaign key '{target}' to apply this change: ").strip()
    except EOFError:
        return False
    if typed != target:
        print("   Approval text did not match. No changes made.", file=sys.stderr)
        return False
    return True


class LiveFetchError(RuntimeError):
    """A configured platform's API call failed. Distinct from 'not configured'
    and from 'configured but genuinely has zero campaigns'."""


def _is_configured(tenant: TenantContext, keys: tuple[str, ...]) -> bool:
    try:
        tenant.require(*keys)
        return True
    except TenantConfigError:
        return False


# ── Google Ads ──────────────────────────────────────────────────────────────

def _google_client(tenant: TenantContext):
    """Build a Google Ads client. Raises LiveFetchError if the SDK is missing
    or the credentials are rejected by the SDK."""
    try:
        from google.ads.googleads.client import GoogleAdsClient
    except ImportError as exc:
        raise LiveFetchError(
            "google-ads SDK not installed — run: pip install google-ads") from exc
    config = {
        "client_id": tenant.env["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": tenant.env["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": tenant.env["GOOGLE_ADS_REFRESH_TOKEN"],
        "developer_token": tenant.env["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "use_proto_plus": True,
    }
    login = tenant.env.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID")  # agency MCC
    if login:
        config["login_customer_id"] = login.replace("-", "")
    try:
        return GoogleAdsClient.load_from_dict(config)
    except (ValueError, KeyError, *_google_errors()) as exc:
        raise LiveFetchError(f"Google Ads client init failed: {_gerr(tenant, exc)}") from exc


def _gerr(tenant: TenantContext, exc: Exception) -> str:
    """Google exception text with this tenant's credentials scrubbed."""
    return _safe_error(exc, *(tenant.env.get(k, "") for k in (
        "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN", "GOOGLE_ADS_DEVELOPER_TOKEN")))


def _google_errors() -> tuple[type[Exception], ...]:
    """API errors AND auth errors (bad/revoked OAuth client or token raise
    GoogleAuthError, not GoogleAdsException)."""
    from google.ads.googleads.errors import GoogleAdsException
    from google.auth.exceptions import GoogleAuthError
    return (GoogleAdsException, GoogleAuthError)


def _google_customer_id(tenant: TenantContext) -> str:
    return tenant.env["GOOGLE_ADS_CUSTOMER_ID"].replace("-", "")


def _google_fetch_campaigns(tenant: TenantContext) -> dict[str, dict]:
    """Pull live Google Ads campaigns. Raises LiveFetchError on any failure."""
    client = _google_client(tenant)
    ga_service = client.get_service("GoogleAdsService")
    try:
        response = ga_service.search(
            customer_id=_google_customer_id(tenant),
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
        rows = list(response)
    except _google_errors() as exc:
        raise LiveFetchError(f"Google Ads API error: {_gerr(tenant, exc)}") from exc

    campaigns: dict[str, dict] = {}
    for row in rows:
        cid = str(row.campaign.id)
        if cid not in campaigns:
            campaigns[cid] = {
                "id": cid, "name": sanitize_text(row.campaign.name),
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
    return _finish_rates(campaigns)


def _google_pause_campaign(tenant: TenantContext, campaign_id: str) -> tuple[bool, str]:
    """Pause a Google Ads campaign. Returns (success, message)."""
    client = _google_client(tenant)
    customer_id = _google_customer_id(tenant)
    campaign_service = client.get_service("CampaignService")
    operation = client.get_type("CampaignOperation")
    operation.update.resource_name = campaign_service.campaign_path(customer_id, campaign_id)
    operation.update.status = client.enums.CampaignStatusEnum.PAUSED
    mask = client.get_type("FieldMask")
    mask.paths.append("status")
    operation.update_mask.CopyFrom(mask)
    try:
        response = campaign_service.mutate_campaigns(
            customer_id=customer_id, operations=[operation])
    except _google_errors() as exc:
        return False, f"Failed to pause Google Ads campaign {campaign_id}: {_gerr(tenant, exc)}"
    return True, f"Google Ads campaign {campaign_id} paused: {response.results[0].resource_name}"


def _google_update_budget(tenant: TenantContext, campaign_id: str,
                          new_budget: float) -> tuple[bool, str]:
    """Update a Google Ads campaign budget. Returns (success, message)."""
    client = _google_client(tenant)
    customer_id = _google_customer_id(tenant)
    ga_service = client.get_service("GoogleAdsService")
    try:
        found = list(ga_service.search(
            customer_id=customer_id,
            query=("SELECT campaign.campaign_budget FROM campaign "
                   f"WHERE campaign.id = {int(campaign_id)}"),
        ))
    except (*_google_errors(), ValueError) as exc:
        return False, f"Could not look up campaign {campaign_id}: {_gerr(tenant, exc)}"
    if not found or not found[0].campaign.campaign_budget:
        return False, f"Campaign {campaign_id} not found or has no budget."

    budget_service = client.get_service("CampaignBudgetService")
    operation = client.get_type("CampaignBudgetOperation")
    operation.update.resource_name = found[0].campaign.campaign_budget
    operation.update.amount_micros = int(new_budget * 1_000_000)
    mask = client.get_type("FieldMask")
    mask.paths.append("amount_micros")
    operation.update_mask.CopyFrom(mask)
    try:
        result = budget_service.mutate_campaign_budgets(
            customer_id=customer_id, operations=[operation])
    except _google_errors() as exc:
        return False, f"Failed to update budget: {_gerr(tenant, exc)}"
    return True, f"Google Ads budget updated to {new_budget:.2f}: {result.results[0].resource_name}"


# ── Meta Ads ────────────────────────────────────────────────────────────────

def _safe_error(exc: Exception, *secrets: str) -> str:
    """Error text with credentials scrubbed. requests embeds the full URL
    (including ?access_token=...) in its exception messages."""
    text = str(exc)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


def _meta_get(url: str, params: dict) -> dict:
    import requests
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise LiveFetchError(
            f"Meta Ads API call failed: {_safe_error(exc, params.get('access_token', ''))}") from exc


def _meta_fetch_campaigns(tenant: TenantContext) -> dict[str, dict]:
    """Pull live Meta campaigns + 7d insights. Raises LiveFetchError on failure."""
    access_token, ad_account_id = tenant.require(*META_KEYS)
    base = f"https://graph.facebook.com/{GRAPH_API_VERSION}/act_{ad_account_id}"
    data = _meta_get(f"{base}/campaigns", {
        "fields": "id,name,status,daily_budget,lifetime_budget",
        "access_token": access_token, "limit": 200})  # ponytail: no pagination past 200

    campaigns: dict[str, dict] = {}
    for row in data.get("data", []):
        budget_cents = row.get("daily_budget") or row.get("lifetime_budget") or "0"
        campaigns[row["id"]] = {
            "id": row["id"], "name": sanitize_text(row["name"]), "status": row["status"],
            "budget": int(budget_cents) / 100, "platform": "meta",
            "impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0.0,
        }

    today = datetime.date.today()
    insights = _meta_get(f"{base}/insights", {
        "level": "campaign",
        "fields": "campaign_id,impressions,clicks,spend,actions",
        "time_range": json.dumps({"since": (today - datetime.timedelta(days=7)).isoformat(),
                                  "until": today.isoformat()}),
        "time_increment": 1, "access_token": access_token, "limit": 500})

    from loops.meta_ads import CONVERSION_ACTION_TYPES
    for row in insights.get("data", []):
        c = campaigns.get(row["campaign_id"])
        if c is None:
            continue
        c["impressions"] += int(row.get("impressions", 0))
        c["clicks"] += int(row.get("clicks", 0))
        c["cost"] += float(row.get("spend", 0))
        c["conversions"] += sum(
            float(a["value"]) for a in row.get("actions", [])
            if a.get("action_type") in CONVERSION_ACTION_TYPES)
    return _finish_rates(campaigns)


def _meta_post(tenant: TenantContext, campaign_id: str, body: dict,
               ok_msg: str, fail_msg: str) -> tuple[bool, str]:
    import requests
    access_token, _ = tenant.require(*META_KEYS)
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{campaign_id}"
    try:
        resp = requests.post(url, params={"access_token": access_token},
                             json=body, timeout=30)
    except requests.RequestException as exc:
        return False, f"{fail_msg}: {_safe_error(exc, access_token)}"
    if resp.status_code == 200:
        return True, ok_msg
    return False, f"{fail_msg}: {_safe_error(Exception(resp.text), access_token)}"


def _meta_pause_campaign(tenant: TenantContext, campaign_id: str) -> tuple[bool, str]:
    return _meta_post(tenant, campaign_id, {"status": "PAUSED"},
                      f"Meta campaign {campaign_id} paused.",
                      f"Failed to pause Meta campaign {campaign_id}")


def _meta_update_budget(tenant: TenantContext, campaign_id: str,
                        new_budget: float) -> tuple[bool, str]:
    """Daily budget, in cents on the wire."""
    return _meta_post(tenant, campaign_id, {"daily_budget": int(new_budget * 100)},
                      f"Meta campaign {campaign_id} budget updated to {new_budget:.2f}.",
                      "Failed to update Meta budget")


def _finish_rates(campaigns: dict[str, dict]) -> dict[str, dict]:
    for c in campaigns.values():
        c["ctr"] = (c["clicks"] / c["impressions"] * 100) if c["impressions"] else 0.0
        c["cpa"] = (c["cost"] / c["conversions"]) if c["conversions"] else None
    return campaigns


# ── Cumulative budget guardrail ─────────────────────────────────────────────

def _ledger_path(tenant: TenantContext) -> Path:
    return tenant.reports_dir / LEDGER_NAME


def _read_ledger(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        # Fail closed: a corrupt ledger must not silently disable the cap.
        raise LiveFetchError(f"Budget ledger unreadable ({path}): {exc}") from exc


def budget_baseline(ledger: list[dict], key: str, current: float,
                    now: datetime.datetime | None = None) -> float:
    """The budget the 20% cap is measured against: the earliest 'from' value
    recorded for this campaign inside the rolling window, else the live budget."""
    now = now or datetime.datetime.now()
    cutoff = now - datetime.timedelta(days=BUDGET_WINDOW_DAYS)
    recent = [e for e in ledger
              if e["key"] == key and datetime.datetime.fromisoformat(e["ts"]) >= cutoff]
    return min(recent, key=lambda e: e["ts"])["from"] if recent else current


def _record_budget_change(path: Path, key: str, old: float, new: float) -> None:
    ledger = _read_ledger(path)
    ledger.append({"ts": datetime.datetime.now().isoformat(timespec="seconds"),
                   "key": key, "from": old, "to": new})
    path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")


# ── Unified fetch ───────────────────────────────────────────────────────────

def _fetch_all(tenant: TenantContext) -> tuple[dict[str, dict], dict[str, str], list[str]]:
    """Pull from every configured platform.
    Returns (campaigns keyed 'platform:id', errors by platform, configured platforms)."""
    campaigns: dict[str, dict] = {}
    errors: dict[str, str] = {}
    configured: list[str] = []
    for platform, keys, fetch in (("google", GOOGLE_KEYS, _google_fetch_campaigns),
                                  ("meta", META_KEYS, _meta_fetch_campaigns)):
        if not _is_configured(tenant, keys):
            continue
        configured.append(platform)
        try:
            for cid, c in fetch(tenant).items():
                campaigns[f"{platform}:{cid}"] = c
        except LiveFetchError as exc:
            errors[platform] = str(exc)
    return campaigns, errors, configured


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

    if opts.get("confirm") is not True:
        print("\n   No --confirm flag passed. No changes made.")
        print("   To execute: add --confirm to the command.")
        return 0
    if not _human_approved(campaign_key):
        return EXIT_REFUSED

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
    # float("nan") parses fine and `nan > cap` is False, which would silently
    # bypass the cap; inf/negative/zero are never a valid daily budget either.
    if not math.isfinite(new_budget) or new_budget <= 0:
        print(f"ERROR: --new-budget must be a finite number > 0, got '{new_budget_raw}'.",
              file=sys.stderr)
        return 2

    if campaign_key not in campaigns:
        available = ", ".join(sorted(campaigns.keys()))
        print(f"ERROR: campaign '{campaign_key}' not found. Available: {available}",
              file=sys.stderr)
        return 2

    c = campaigns[campaign_key]
    platform, cid = _parse_platform_key(campaign_key)
    current = c["budget"]
    try:
        ledger = _read_ledger(_ledger_path(tenant))
    except LiveFetchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    baseline = budget_baseline(ledger, campaign_key, current)
    if baseline <= 0:
        # No known starting budget (e.g. budget lives on ad sets, or lifetime
        # budget): the 20% cap cannot be evaluated, so fail closed.
        print(f"ERROR: campaign '{c['name']}' reports no campaign-level budget ({baseline:.2f}); "
              "the cumulative cap cannot be verified. Change it in the ad platform UI.",
              file=sys.stderr)
        return 2
    change_pct = abs(new_budget - baseline) / baseline

    # Show the exact change BEFORE executing
    print(f"⚠️  ABOUT TO CHANGE BUDGET: {platform} campaign '{c['name']}' (ID: {cid})")
    print(f"   Current budget: {current:.2f}")
    print(f"   Proposed budget: {new_budget:.2f}")
    print(f"   Change: {new_budget - current:+.2f}")
    if baseline != current:
        print(f"   {BUDGET_WINDOW_DAYS}-day baseline: {baseline:.2f} (earlier changes in the window count)")
    print(f"   Cumulative vs baseline: {(new_budget - baseline) / baseline * 100:+.1f}%")

    if change_pct > MAX_BUDGET_CHANGE_PCT:
        print(f"\n   ❌ BLOCKED: cumulative change is {change_pct * 100:.1f}% — exceeds the "
              f"{MAX_BUDGET_CHANGE_PCT * 100:.0f}% cap per {BUDGET_WINDOW_DAYS} days (rule: respect learning).")
        print(f"   Allowed range: {baseline * (1 - MAX_BUDGET_CHANGE_PCT):.2f} "
              f"to {baseline * (1 + MAX_BUDGET_CHANGE_PCT):.2f}")
        return 2

    if opts.get("confirm") is not True:
        print("\n   No --confirm flag passed. No changes made.")
        print("   To execute: add --confirm to the command.")
        return 0
    if not _human_approved(campaign_key):
        return EXIT_REFUSED

    if platform == "google":
        ok, msg = _google_update_budget(tenant, cid, new_budget)
    elif platform == "meta":
        ok, msg = _meta_update_budget(tenant, cid, new_budget)
    else:
        print(f"ERROR: unsupported platform '{platform}'", file=sys.stderr)
        return 2

    print(f"\n{'✅' if ok else '❌'} {msg}")
    if ok:
        _record_budget_change(_ledger_path(tenant), campaign_key, current, new_budget)
        append_log(tenant.name, "campaigns-budget",
                   f"Budget {platform} campaign '{c['name']}' (ID: {cid}): "
                   f"{current:.2f} -> {new_budget:.2f} ({change_pct * 100:+.1f}%)",
                   tenant.reports_dir / "budget-log.md")
    return 0 if ok else 1


# ── Dispatch ────────────────────────────────────────────────────────────────

def run(tenant: TenantContext, opts: dict | None = None) -> int:
    opts = opts or {}
    verb = opts.get("verb", "pull")

    campaigns, errors, configured = _fetch_all(tenant)
    if not configured:
        print(f"[{tenant.name}] campaigns {verb}: no ad platform configured. "
              "Add Google Ads and/or Meta credentials to the tenant .env.", file=sys.stderr)
        return 1
    for platform, msg in errors.items():
        print(f"❌ {platform} FETCH FAILED: {msg}", file=sys.stderr)
    if errors and verb in ("pause", "budget"):
        print("Refusing to write with stale/partial account state. Fix the error above and retry.",
              file=sys.stderr)
        return 1

    if errors and not campaigns:
        return 1  # nothing usable fetched: don't render an "empty account" report

    code = _dispatch(tenant, verb, campaigns, opts)
    return 1 if errors and code == 0 else code


def _dispatch(tenant: TenantContext, verb: str, campaigns: dict[str, dict], opts: dict) -> int:
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