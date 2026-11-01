"""In-process coverage for forecast, season, tracking, tenants, leads (kept together: each is small)."""
import datetime

import pytest

from cov_helpers import make_tenant, import_csv, patch_workspace
from commands import forecast, season, tracking, tenants, leads, state
from tasks import write_task

READY = ("GOOGLE_ADS_CLIENT_ID=a1\nGOOGLE_ADS_CLIENT_SECRET=a2\nGOOGLE_ADS_REFRESH_TOKEN=a3\n"
         "GOOGLE_ADS_DEVELOPER_TOKEN=a4\nGOOGLE_ADS_CUSTOMER_ID=a5\n")
META = "META_ACCESS_TOKEN=b1\nMETA_AD_ACCOUNT_ID=b2\n"


# ---- forecast -------------------------------------------------------------------------------------
def test_forecast_without_report_says_so(monkeypatch, tmp_path, capsys):
    t = make_tenant(monkeypatch, tmp_path)
    assert forecast.run(t) == 0
    assert "No ad-intel report captured yet" in capsys.readouterr().out
    assert not list(t.reports_dir.glob("*-forecast.md"))


def test_forecast_projects_and_judges_against_target(monkeypatch, tmp_path, capsys):
    t = make_tenant(monkeypatch, tmp_path, env="TARGET_CPA=10\n")   # observed CPA 1000/58 = 17.24 -> 1.72x
    import_csv(t, tmp_path)
    opts = {"_extra": {}}
    assert forecast.run(t, opts) == 0
    out = capsys.readouterr().out
    data = opts["_extra"]["_data"]
    assert data["weekly_spend"] == 1000 and data["weekly_conversions"] == 58
    assert data["monthly_spend"] == pytest.approx(4330) and data["campaigns_active"] == 3
    assert data["observed_cpa"] == pytest.approx(1000 / 58) and data["target_cpa"] == 10.0
    assert "1.72x target — cut waste before scaling" in out and "not guarantees" in out


@pytest.mark.parametrize("target,needle", [("20", "at target"), ("15", "within tolerance")])
def test_forecast_target_bands(monkeypatch, tmp_path, capsys, target, needle):
    t = make_tenant(monkeypatch, tmp_path, env=f"TARGET_CPA={target}\n")
    import_csv(t, tmp_path)
    forecast.run(t)
    assert needle in capsys.readouterr().out


def test_forecast_zero_conversions_has_no_cpa(monkeypatch, tmp_path, capsys):
    t = make_tenant(monkeypatch, tmp_path, env="TARGET_CPA=10\n")
    import_csv(t, tmp_path, "Campaign name,Delivery,Results,Impressions,Clicks (all),Amount spent (USD)\n"
                            "A,active,0,1000,10,50\n")
    opts = {"_extra": {}}
    forecast.run(t, opts)
    assert opts["_extra"]["_data"]["observed_cpa"] is None
    assert "Observed CPA:** n/a" in capsys.readouterr().out


# ---- season ---------------------------------------------------------------------------------------
def freeze(monkeypatch, when):
    real = state.collect_snapshot
    monkeypatch.setattr(season, "collect_snapshot", lambda t: {**real(t), "now": when})


def test_season_active_and_prep_window(monkeypatch, tmp_path, capsys):
    t = make_tenant(monkeypatch, tmp_path)
    freeze(monkeypatch, datetime.datetime(2026, 11, 29, 9, 0))
    assert season.run(t) == 0
    out = capsys.readouterr().out
    assert "ACTIVE NOW" in out and "White Friday" in out
    assert "UAE National Day" in out and "(3 days away)" in out and "PREP WINDOW OPEN" in out
    assert "Start now:** 3 days left" in out
    assert "### Saudi National Day" not in out          # already past
    assert "Ramadan 2027 (approx)" in out and "prep starts 2027-01-19" in out
    assert list(t.reports_dir.glob("*-season-plan.md"))


def test_season_active_label_is_not_always_today(monkeypatch, tmp_path, capsys):
    t = make_tenant(monkeypatch, tmp_path)
    freeze(monkeypatch, datetime.datetime(2026, 11, 29, 9, 0))   # White Friday started 2026-11-27
    season.run(t)
    out = capsys.readouterr().out
    assert "Date: 2026-11-27 (started 2 days ago)" in out
    assert "(today)" not in out


def test_season_calendar_exhausted(monkeypatch, tmp_path, capsys):
    t = make_tenant(monkeypatch, tmp_path)
    freeze(monkeypatch, datetime.datetime(2028, 1, 1, 9, 0))
    assert season.run(t) == 0
    out = capsys.readouterr().out
    assert "No upcoming seasons in the calendar" in out and "ACTIVE NOW" not in out


# ---- tracking -------------------------------------------------------------------------------------
def test_tracking_check_placeholders_means_nothing_configured(monkeypatch, tmp_path, capsys):
    t = make_tenant(monkeypatch, tmp_path)
    assert tracking.run(t, {"verb": "check"}) == 0
    out = capsys.readouterr().out
    assert "No integrations configured" in out and "INCOMPLETE (0/5)" in out and "INCOMPLETE (0/2)" in out
    assert "Operator name: not set" in out and "Target CPA: not set" in out
    assert list(t.reports_dir.glob("*-tracking-check.md"))


def test_tracking_check_partial_and_full(monkeypatch, tmp_path, capsys):
    t = make_tenant(monkeypatch, tmp_path, env="OPERATOR_NAME=Sam\nTARGET_CPA=9\n" + META)
    tracking.run(t)                                   # default verb is check
    out = capsys.readouterr().out
    assert "| meta-ads | 2/2 | READY |" in out and "Partial setup:** google-ads" in out
    assert "Operator name: set" in out and "Target CPA: set" in out
    t2 = make_tenant(monkeypatch, tmp_path, name="Full", env=READY + META)
    tracking.run(t2, {"verb": "check"})
    assert "All integrations configured" in capsys.readouterr().out


def test_tracking_events(monkeypatch, tmp_path, capsys):
    t = make_tenant(monkeypatch, tmp_path, env=META)
    assert tracking.run(t, {"verb": "events"}) == 0
    out = capsys.readouterr().out
    assert "| Meta (Pixel/Conversions API) | ✓ | YES — keys configured |" in out
    assert "| Google Ads (Pixel/CAPI) | ✗ | NO — keys missing |" in out and "COD note" in out


def test_tracking_unknown_verb_fails(monkeypatch, tmp_path, capsys):
    t = make_tenant(monkeypatch, tmp_path)
    assert tracking.run(t, {"verb": "bogus"}) == 1
    assert "unknown tracking verb 'bogus'" in capsys.readouterr().err
    assert not list(t.reports_dir.glob("*-tracking-*.md"))


# ---- tenants --------------------------------------------------------------------------------------
def test_tenants_no_clients_folder(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(tenants, "CLIENTS_ROOT", tmp_path / "nope")
    assert tenants.run() == 0
    assert "No clients folder at" in capsys.readouterr().out


def test_tenants_empty_folder(monkeypatch, tmp_path, capsys):
    patch_workspace(monkeypatch, tmp_path)
    assert tenants.run() == 0
    assert "No tenants configured yet" in capsys.readouterr().out


def test_tenants_lists_readiness(monkeypatch, tmp_path, capsys):
    t = make_tenant(monkeypatch, tmp_path, name="Alpha", env=META)
    (t.root / "02_Content").mkdir()
    (t.reports_dir / "r.md").write_text("x", encoding="utf-8")
    (t.signals_dir / "s.md").write_text("x", encoding="utf-8")
    (tmp_path / "02_Active_Clients" / "Bare").mkdir()      # folder with neither .env nor STRATEGY.md
    assert tenants.run({}) == 0
    out = capsys.readouterr().out
    assert "# Tenants — 1 configured" in out
    assert "| Alpha | ✓ | ✓ | 1/2 | 1 | 1 | ✓ |" in out
    assert "| Bare | ✗ | ✗ | 0/2 | 0 | 0 | ✗ |" in out


# ---- leads ----------------------------------------------------------------------------------------
def lead_task(t, slug):
    return write_task(t, domain="lead-qualify", priority="high", task_summary=f"Call {slug}", context="c",
                      acceptance_criteria=["a", "b"], linked_signal="none", slug=slug)


def test_leads_none_yet(monkeypatch, tmp_path, capsys):
    t = make_tenant(monkeypatch, tmp_path)
    write_task(t, domain="ads", priority="low", task_summary="x", context="c",
               acceptance_criteria=["a", "b"], linked_signal="none", slug="other")   # not a lead task
    assert leads.run(t) == 0
    assert "No lead-qualify tasks yet" in capsys.readouterr().out
    assert not list(t.reports_dir.glob("*-leads-score.md"))


def test_leads_counts_open_and_done(monkeypatch, tmp_path, capsys):
    t = make_tenant(monkeypatch, tmp_path)
    lead_task(t, "one")
    done = lead_task(t, "two")
    done.write_text(done.read_text(encoding="utf-8").replace("status: open", "status: done"), encoding="utf-8")
    assert leads.run(t) == 0
    out = capsys.readouterr().out
    assert "**Total lead tasks:** 2" in out and "**Open:** 1" in out and "**Done:** 1" in out
    assert "| high |" in out and "Task" in out
    assert list(t.reports_dir.glob("*-leads-score.md"))


def test_leads_truncates_after_twenty(monkeypatch, tmp_path, capsys):
    t = make_tenant(monkeypatch, tmp_path)
    for i in range(22):
        lead_task(t, f"lead-{i:02d}")
    leads.run(t)
    out = capsys.readouterr().out
    assert "**Total lead tasks:** 22" in out and "... and 2 more" in out
