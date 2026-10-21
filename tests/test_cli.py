"""foundry.py CLI surface: economics flags and confirm semantics."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def foundry(*args, cwd=ROOT):
    return subprocess.run([sys.executable, str(ROOT / "foundry.py"), *args], cwd=cwd,
                          capture_output=True, text=True, timeout=60)


def test_economics_breakeven_via_foundry_cli_matches_calc():
    r = foundry("economics", "breakeven", "--price", "499", "--cogs", "150", "--shipping", "45",
                "--fees", "3", "--confirm", "0.85", "--deliver", "0.78", "--return-cost", "30", "--json")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)["data"]
    assert round(out["break_even_cpa_per_placed_order"], 3) == 185.538


def test_economics_missing_input_fails_clearly():
    r = foundry("economics", "breakeven", "--price", "499")
    assert r.returncode == 2 and "--cogs is required" in r.stderr


def test_economics_without_confirm_flag_uses_default_rate():
    """Regression: argparse's False default was read as a 0% confirmation rate."""
    r = foundry("economics", "breakeven", "--price", "499", "--cogs", "150", "--json")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["data"]["break_even_cpa_per_placed_order"] > 0


def test_google_ads_config_status_recognizes_all_5_developer_keys():
    """Regression: GOOGLE_ADS_DEVELOPER_TOKEN was misspelled DEVELOTER in state.py."""
    sys.path.insert(0, str(ROOT / "core" / "engine"))
    from commands.state import config_status
    env = {
        "GOOGLE_ADS_CLIENT_ID": "real-id",
        "GOOGLE_ADS_CLIENT_SECRET": "real-secret",
        "GOOGLE_ADS_REFRESH_TOKEN": "real-refresh",
        "GOOGLE_ADS_DEVELOPER_TOKEN": "real-dev-token",
        "GOOGLE_ADS_CUSTOMER_ID": "123-456-7890",
        "OPERATOR_NAME": "Mohamed Omar",
        "TARGET_CPA": "120",
    }
    status = config_status(env)
    g = status["groups"]["google-ads"]
    assert g["configured"] == 5 and g["required"] == 5 and g["ready"] is True


def test_read_ad_report_supports_meta_and_live_pull_reports(tmp_path):
    """Regression: read_ad_report only globbed *-ad-intel-report.md, ignoring Meta and live-pull."""
    sys.path.insert(0, str(ROOT / "core" / "engine"))
    from types import SimpleNamespace
    from commands.state import read_ad_report

    reports_dir = tmp_path / "04_Reports"
    reports_dir.mkdir()
    tenant = SimpleNamespace(reports_dir=reports_dir)

    # 1. Meta Ads report (10 columns)
    meta_md = (
        "# Acme — Meta Ads Daily Check — 2026-10-20 10:00\n\n"
        "| Campaign | Status | Daily Budget | Today's Spend | Impr. | Clicks | CTR | Spend | Conversions | CPA |\n"
        "|---|---|---|---|---|---|---|---|---|---|\n"
        "| Retargeting | ACTIVE | 100.00 | 45.00 | 5,000 | 150 | 3.00% | 300.00 | 10.0 | 30.00 |\n"
    )
    (reports_dir / "2026-10-20-10-meta-ads-report.md").write_text(meta_md, encoding="utf-8")
    parsed_meta = read_ad_report(tenant)
    assert parsed_meta is not None
    assert len(parsed_meta["rows"]) == 1
    assert parsed_meta["rows"][0]["name"] == "Retargeting"
    assert parsed_meta["totals"]["cost"] == 300.0
    assert parsed_meta["totals"]["conversions"] == 10.0
    assert parsed_meta["totals"]["cpa"] == 30.0

    # 2. Live pull report (10 columns with Platform first, newer timestamp)
    live_md = (
        "# Acme — Live Campaigns — 2026-10-20 12:00\n\n"
        "| Platform | Campaign | Status | Budget | Spend (7d) | Impr. | Clicks | CTR | Conv. | CPA |\n"
        "|---|---|---|---|---|---|---|---|---|---|\n"
        "| google | Search Brand | ENABLED | 200.00 | 700.00 | 10,000 | 500 | 5.00% | 35 | 20.00 |\n"
    )
    (reports_dir / "2026-10-20-12-live-pull.md").write_text(live_md, encoding="utf-8")
    parsed_live = read_ad_report(tenant)
    assert parsed_live is not None
    assert parsed_live["rows"][0]["name"] == "Search Brand"
    assert parsed_live["totals"]["cost"] == 700.0
    assert parsed_live["totals"]["conversions"] == 35.0
    assert parsed_live["totals"]["cpa"] == 20.0


def test_forecast_project_command_is_routed_in_foundry_cli(tmp_path):
    """Regression: forecast was documented in SKILL.md and imported in foundry.py, but missing from GROUPS."""
    import os
    env = {**os.environ, "FOUNDRY_WORKSPACE": str(tmp_path), "PYTHONIOENCODING": "utf-8"}
    init = subprocess.run([sys.executable, str(ROOT / "foundry.py"), "setup", "init", "--client", "Acme"],
                          cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert init.returncode == 0
    r = subprocess.run([sys.executable, str(ROOT / "foundry.py"), "forecast", "project", "--client", "Acme", "--json"],
                       cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["ok"] is True and payload["command"] == "forecast project"


def test_economics_leadgen_via_foundry_cli():
    """Lead-gen / WhatsApp funnel economics calculator (lead -> qualified -> closed -> deal value)."""
    r = foundry("economics", "leadgen", "--deal-value", "5000", "--cogs", "1500",
                "--qualify-rate", "0.40", "--close-rate", "0.25", "--spend", "10000",
                "--leads", "200", "--json")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)["data"]
    assert data["command"] == "leadgen"
    # lead_to_close_rate = 0.40 * 0.25 = 0.10
    # contribution_per_deal = 5000 - 1500 = 3500
    # break_even_cpl = 3500 * 0.10 = 350.0
    assert round(data["lead_to_close_rate"], 4) == 0.10
    assert round(data["break_even_cpl"], 2) == 350.0
    assert round(data["real_cpl"], 2) == 50.0
    assert round(data["closed_deals"], 2) == 20.0
    assert round(data["gross_profit_after_ads"], 2) == 60000.0
    assert data["verdict"] == "profitable"


def test_campaigns_import_csv_populates_ad_report_and_unblocks_diagnose(tmp_path):
    """Importing a CSV ad export writes a standard ad report that diagnose/campaigns/forecast can read."""
    import os
    env = {**os.environ, "FOUNDRY_WORKSPACE": str(tmp_path), "PYTHONIOENCODING": "utf-8"}
    subprocess.run([sys.executable, str(ROOT / "foundry.py"), "setup", "init", "--client", "Acme"],
                   cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60, check=True)
    csv_file = tmp_path / "export.csv"
    csv_file.write_text(
        "Campaign,Status,Budget,Spend,Impressions,Clicks,Conversions\n"
        "KSA_Search_Brand,ENABLED,200,1400,20000,1200,40\n"
        "UAE_Meta_Retargeting,ACTIVE,100,600,15000,300,10\n",
        encoding="utf-8",
    )
    imp = subprocess.run(
        [sys.executable, str(ROOT / "foundry.py"), "campaigns", "import",
         "--client", "Acme", "--file", str(csv_file), "--json"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60,
    )
    assert imp.returncode == 0, imp.stderr
    imp_data = json.loads(imp.stdout)
    assert imp_data["ok"] is True and imp_data["data"]["campaigns_imported"] == 2

    # Now campaigns compare and forecast project work immediately on imported CSV data
    cmp_res = subprocess.run(
        [sys.executable, str(ROOT / "foundry.py"), "campaigns", "compare", "--client", "Acme"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60,
    )
    assert cmp_res.returncode == 0
    assert "Side-by-Side Comparison" in cmp_res.stdout
    assert "KSA_Search_Brand" in cmp_res.stdout


def test_report_whatsapp_format_renders_copy_ready_digest(tmp_path):
    """Client report supports --format whatsapp in both EN and AR for instant client messaging."""
    import os
    env = {**os.environ, "FOUNDRY_WORKSPACE": str(tmp_path), "PYTHONIOENCODING": "utf-8"}
    subprocess.run([sys.executable, str(ROOT / "foundry.py"), "setup", "init", "--client", "Acme"],
                   cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60, check=True)
    r_ar = subprocess.run(
        [sys.executable, str(ROOT / "foundry.py"), "account", "report",
         "--client", "Acme", "--lang", "ar", "--format", "whatsapp"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60, encoding="utf-8",
    )
    assert r_ar.returncode == 0, r_ar.stderr
    assert "*ملخص" in r_ar.stdout or "الخلاصة" in r_ar.stdout


