"""Unit tests for the money-moving paths in commands/live.py.
No network: SDK clients and `requests` are mocked."""
import datetime
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from commands import live


def make_tenant(tmp_path, env=None):
    reports = tmp_path / "04_Reports"
    reports.mkdir(exist_ok=True)

    def require(*keys):
        missing = [k for k in keys if k not in (env or {})]
        if missing:
            raise live.TenantConfigError(f"missing {missing}")
        return tuple(env[k] for k in keys)

    return SimpleNamespace(name="T", env=env or {}, reports_dir=reports, require=require)


GOOGLE_ENV = {k: "x" for k in live.GOOGLE_KEYS} | {"GOOGLE_ADS_CUSTOMER_ID": "123-456-7890"}
META_ENV = {"META_ACCESS_TOKEN": "tok", "META_AD_ACCOUNT_ID": "1"}


# ── cumulative budget cap ───────────────────────────────────────────────────

def test_baseline_is_live_budget_when_no_history():
    assert live.budget_baseline([], "meta:1", 100.0) == 100.0


def test_baseline_uses_earliest_change_in_window():
    now = datetime.datetime(2026, 10, 10)
    ledger = [
        {"ts": "2026-10-08T00:00:00", "key": "meta:1", "from": 100.0, "to": 120.0},
        {"ts": "2026-10-09T00:00:00", "key": "meta:1", "from": 120.0, "to": 144.0},
    ]
    assert live.budget_baseline(ledger, "meta:1", 144.0, now) == 100.0


def test_baseline_ignores_old_and_other_campaigns():
    now = datetime.datetime(2026, 10, 20)
    ledger = [
        {"ts": "2026-10-01T00:00:00", "key": "meta:1", "from": 50.0, "to": 60.0},
        {"ts": "2026-10-19T00:00:00", "key": "meta:2", "from": 10.0, "to": 12.0},
    ]
    assert live.budget_baseline(ledger, "meta:1", 60.0, now) == 60.0


def test_repeated_steps_cannot_compound_past_cap(tmp_path):
    tenant = make_tenant(tmp_path, META_ENV)
    campaigns = {"meta:1": {"name": "c", "budget": 100.0, "platform": "meta"}}
    with patch.object(live, "_meta_update_budget", return_value=(True, "ok")), \
         patch.object(live, "_human_approved", return_value=True), \
         patch.object(live, "append_log"):
        assert live._cmd_budget(tenant, campaigns, {"campaign_id": "meta:1", "new_budget": 120, "confirm": True}) == 0
        campaigns["meta:1"]["budget"] = 120.0           # account now reflects step 1
        # +20% again from 120 would be 144 = +44% cumulative -> must block
        assert live._cmd_budget(tenant, campaigns, {"campaign_id": "meta:1", "new_budget": 144, "confirm": True}) == 2
    ledger = json.loads((tenant.reports_dir / live.LEDGER_NAME).read_text())
    assert len(ledger) == 1


def test_budget_without_confirm_writes_nothing(tmp_path):
    tenant = make_tenant(tmp_path, META_ENV)
    campaigns = {"meta:1": {"name": "c", "budget": 100.0, "platform": "meta"}}
    with patch.object(live, "_meta_update_budget") as mutate:
        assert live._cmd_budget(tenant, campaigns, {"campaign_id": "meta:1", "new_budget": 110}) == 0
        mutate.assert_not_called()


def test_corrupt_ledger_fails_closed(tmp_path):
    tenant = make_tenant(tmp_path, META_ENV)
    (tenant.reports_dir / live.LEDGER_NAME).write_text("{not json")
    campaigns = {"meta:1": {"name": "c", "budget": 100.0, "platform": "meta"}}
    with patch.object(live, "_meta_update_budget") as mutate:
        assert live._cmd_budget(tenant, campaigns, {"campaign_id": "meta:1", "new_budget": 110, "confirm": True}) == 1
        mutate.assert_not_called()


# ── typed fetch failures ────────────────────────────────────────────────────

def test_fetch_all_distinguishes_unconfigured_from_failed(tmp_path):
    assert live._fetch_all(make_tenant(tmp_path, {})) == ({}, {}, [])
    tenant = make_tenant(tmp_path, META_ENV)
    with patch.object(live, "_meta_fetch_campaigns", side_effect=live.LiveFetchError("boom")):
        campaigns, errors, configured = live._fetch_all(tenant)
    assert campaigns == {} and errors == {"meta": "boom"} and configured == ["meta"]


def test_meta_get_wraps_request_errors():
    import requests
    with patch("requests.get", side_effect=requests.ConnectionError("down")):
        with pytest.raises(live.LiveFetchError):
            live._meta_get("http://x", {})


def test_run_refuses_writes_when_a_fetch_failed(tmp_path):
    tenant = make_tenant(tmp_path, META_ENV)
    with patch.object(live, "_meta_fetch_campaigns", side_effect=live.LiveFetchError("boom")), \
         patch.object(live, "_meta_pause_campaign") as pause:
        assert live.run(tenant, {"verb": "pause", "campaign_id": "meta:1", "confirm": True}) == 1
        pause.assert_not_called()


def test_run_pull_failure_is_nonzero_not_empty_success(tmp_path):
    tenant = make_tenant(tmp_path, META_ENV)
    with patch.object(live, "_meta_fetch_campaigns", side_effect=live.LiveFetchError("boom")):
        assert live.run(tenant, {"verb": "pull"}) == 1


# ── mutators (mocked SDK / HTTP) ────────────────────────────────────────────

def test_meta_pause_and_budget_payloads(tmp_path):
    tenant = make_tenant(tmp_path, META_ENV)
    ok = MagicMock(status_code=200)
    with patch("requests.post", return_value=ok) as post:
        assert live._meta_pause_campaign(tenant, "9")[0] is True
        assert post.call_args.kwargs["json"] == {"status": "PAUSED"}
        assert live._meta_update_budget(tenant, "9", 12.34)[0] is True
        assert post.call_args.kwargs["json"] == {"daily_budget": 1234}


def test_meta_mutator_reports_http_failure(tmp_path):
    tenant = make_tenant(tmp_path, META_ENV)
    with patch("requests.post", return_value=MagicMock(status_code=400, text="bad")):
        ok, msg = live._meta_pause_campaign(tenant, "9")
    assert ok is False and "bad" in msg


def test_google_client_sets_mcc_login_customer_id(tmp_path):
    tenant = make_tenant(tmp_path, GOOGLE_ENV | {"GOOGLE_ADS_LOGIN_CUSTOMER_ID": "999-888-7777"})
    with patch("google.ads.googleads.client.GoogleAdsClient.load_from_dict") as load:
        live._google_client(tenant)
    assert load.call_args.args[0]["login_customer_id"] == "9998887777"


def test_google_pause_sends_paused_status_mask(tmp_path):
    tenant = make_tenant(tmp_path, GOOGLE_ENV)
    client = MagicMock()
    with patch.object(live, "_google_client", return_value=client):
        ok, _ = live._google_pause_campaign(tenant, "42")
    assert ok is True
    service = client.get_service.return_value
    service.campaign_path.assert_called_once_with("1234567890", "42")
    service.mutate_campaigns.assert_called_once()
    client.get_type.return_value.update_mask.CopyFrom.assert_called_once()


def test_google_budget_converts_to_micros(tmp_path):
    tenant = make_tenant(tmp_path, GOOGLE_ENV)
    client = MagicMock()
    row = SimpleNamespace(campaign=SimpleNamespace(campaign_budget="customers/1/campaignBudgets/7"))
    client.get_service.return_value.search.return_value = [row]
    with patch.object(live, "_google_client", return_value=client):
        ok, _ = live._google_update_budget(tenant, "42", 12.5)
    assert ok is True
    assert client.get_type.return_value.update.amount_micros == 12_500_000


def test_google_budget_rejects_non_numeric_campaign_id(tmp_path):
    tenant = make_tenant(tmp_path, GOOGLE_ENV)
    with patch.object(live, "_google_client", return_value=MagicMock()):
        ok, msg = live._google_update_budget(tenant, "1 OR 1=1", 10)
    assert ok is False and "Could not look up" in msg


def test_google_auth_error_is_typed_fetch_failure(tmp_path):
    """Regression: a revoked/invalid OAuth client raises GoogleAuthError, which
    previously escaped as an untyped exception."""
    from google.auth.exceptions import RefreshError
    tenant = make_tenant(tmp_path, GOOGLE_ENV)
    client = MagicMock()
    client.get_service.return_value.search.side_effect = RefreshError("invalid_client")
    with patch.object(live, "_google_client", return_value=client):
        with pytest.raises(live.LiveFetchError):
            live._google_fetch_campaigns(tenant)


def test_google_fetch_aggregates_rows_and_rates(tmp_path):
    tenant = make_tenant(tmp_path, GOOGLE_ENV)
    def row(i, cost):
        return SimpleNamespace(
            campaign=SimpleNamespace(id=i, name="c", status=SimpleNamespace(name="ENABLED")),
            campaign_budget=SimpleNamespace(amount_micros=50_000_000),
            metrics=SimpleNamespace(impressions=1000, clicks=50, cost_micros=cost, conversions=2.0))
    client = MagicMock()
    client.get_service.return_value.search.return_value = [row(7, 10_000_000), row(7, 20_000_000)]
    with patch.object(live, "_google_client", return_value=client):
        out = live._google_fetch_campaigns(tenant)
    c = out["7"]
    assert c["cost"] == 30.0 and c["clicks"] == 100 and c["budget"] == 50.0
    assert c["ctr"] == 5.0 and c["cpa"] == 7.5


def test_meta_fetch_merges_insights(tmp_path):
    tenant = make_tenant(tmp_path, META_ENV)
    payloads = [
        {"data": [{"id": "1", "name": "m", "status": "ACTIVE", "daily_budget": "5000"}]},
        {"data": [{"campaign_id": "1", "impressions": "200", "clicks": "10", "spend": "4.5",
                   "actions": [{"action_type": "purchase", "value": "3"}]}]},
    ]
    with patch.object(live, "_meta_get", side_effect=payloads):
        out = live._meta_fetch_campaigns(tenant)
    assert out["1"]["budget"] == 50.0 and out["1"]["cost"] == 4.5 and out["1"]["conversions"] == 3.0


def test_pause_confirm_gate_and_success(tmp_path):
    tenant = make_tenant(tmp_path, META_ENV)
    campaigns = {"meta:1": {"name": "c", "status": "ACTIVE", "cost": 1.0, "conversions": 0, "platform": "meta"}}
    with patch.object(live, "_meta_pause_campaign", return_value=(True, "ok")) as pause, \
         patch.object(live, "_human_approved", return_value=True), \
         patch.object(live, "append_log"):
        assert live._cmd_pause(tenant, campaigns, {"campaign_id": "meta:1"}) == 0
        pause.assert_not_called()
        assert live._cmd_pause(tenant, campaigns, {"campaign_id": "meta:1", "confirm": True}) == 0
        pause.assert_called_once()


def test_google_client_init_auth_error_is_typed(tmp_path):
    from google.auth.exceptions import RefreshError
    tenant = make_tenant(tmp_path, GOOGLE_ENV)
    with patch("google.ads.googleads.client.GoogleAdsClient.load_from_dict",
               side_effect=RefreshError("invalid_client")):
        with pytest.raises(live.LiveFetchError):
            live._google_client(tenant)


# ── secrets never leak; confirm must be a bare flag ─────────────────────────

def test_meta_http_error_does_not_leak_access_token():
    import requests
    err = requests.HTTPError("400 for url: https://graph.facebook.com/x?access_token=SECRET123&limit=1")
    with patch("requests.get", side_effect=err):
        with pytest.raises(live.LiveFetchError) as info:
            live._meta_get("http://x", {"access_token": "SECRET123"})
    assert "SECRET123" not in str(info.value)


def test_meta_mutator_failure_does_not_leak_token(tmp_path):
    import requests
    tenant = make_tenant(tmp_path, {"META_ACCESS_TOKEN": "SECRET123", "META_AD_ACCOUNT_ID": "1"})
    with patch("requests.post", side_effect=requests.ConnectionError("failed ?access_token=SECRET123")):
        ok, msg = live._meta_pause_campaign(tenant, "9")
    assert ok is False and "SECRET123" not in msg


def test_confirm_with_a_value_does_not_authorise_writes(tmp_path):
    """`--confirm 0.85` (an economics rate) must never count as write approval."""
    tenant = make_tenant(tmp_path, META_ENV)
    campaigns = {"meta:1": {"name": "c", "status": "ACTIVE", "cost": 1.0, "conversions": 0,
                            "budget": 100.0, "platform": "meta"}}
    with patch.object(live, "_meta_pause_campaign") as pause:
        live._cmd_pause(tenant, campaigns, {"campaign_id": "meta:1", "confirm": "0.85"})
        pause.assert_not_called()


def test_count_conversions_messaging_and_no_double_count():
    from loops.meta_ads import count_conversions
    actions = [
        {"action_type": "link_click", "value": "900"},
        {"action_type": "onsite_conversion.messaging_conversation_started_7d", "value": "92"},
        {"action_type": "purchase", "value": "3"},
        {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "3"},
        {"action_type": "omni_purchase", "value": "3"},
    ]
    assert count_conversions(actions) == 95.0
    assert count_conversions([]) == 0.0
    assert count_conversions([{"action_type": "post_engagement", "value": "50"}]) == 0.0
