"""CSV mode: an imported export with no credentials is judged on its data (score + ranked findings +
actions), in English and Arabic, instead of being graded on missing setup."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from commands.perf import analyse

ROOT = Path(__file__).resolve().parents[1]


def row(name, cost, conv, impr=10000, clicks=300):
    return {"name": name, "cost": cost, "conversions": conv, "impressions": impr, "clicks": clicks}


def test_roles_waste_winner_thin():
    got = analyse([row("A", 500, 50), row("B", 300, 6), row("C", 200, 0), row("D", 0, 0)])
    roles = {c["name"]: c["role"] for c in got["campaigns"]}
    assert roles == {"A": "winner", "B": "thin", "C": "waste"}
    assert got["skipped_no_spend"] == 1


def test_waste_lowers_score_and_zero_conversions_withhold_it():
    clean = analyse([row("A", 500, 50), row("B", 500, 50)])
    wasteful = analyse([row("A", 500, 50), row("B", 300, 30), row("C", 200, 0)])
    assert wasteful["score"]["total"] < clean["score"]["total"]
    none = analyse([row("A", 500, 0), row("B", 500, 0)])
    assert none["score"] is None
    assert none["findings"][0]["layer"] == "Conversion tracking"


def test_target_cpa_marks_loser_and_changes_conversion_score():
    got = analyse([row("A", 500, 50), row("B", 500, 20)], target_cpa=20)
    roles = {c["name"]: c["role"] for c in got["campaigns"]}
    assert roles["B"] == "loser" and roles["A"] == "winner"
    assert got["score"]["components"]["conversion"]["evidence"].startswith("blended CPA")


def test_low_conversions_make_score_provisional():
    assert analyse([row("A", 100, 5)])["score"]["confidence"] == "low"


def test_all_thin_campaigns_are_never_called_winners_or_losers():
    got = analyse([row("A", 100, 5), row("B", 100, 9)])
    assert {c["role"] for c in got["campaigns"]} == {"thin"}


@pytest.fixture(scope="module")
def csv_workspace(tmp_path_factory):
    ws = tmp_path_factory.mktemp("csvmode")
    env = {**os.environ, "FOUNDRY_WORKSPACE": str(ws), "PYTHONIOENCODING": "utf-8"}

    def run(*args):
        return subprocess.run([sys.executable, str(ROOT / "foundry.py"), *args, "--client", "Acme"],
                              cwd=ws, env=env, capture_output=True, text=True, encoding="utf-8", timeout=60, check=False)

    run("setup", "init")
    (ws / "export.csv").write_text(
        "Campaign name,Delivery,Results,Impressions,Clicks (all),Amount spent (USD)\n"
        "KSA_Prospecting,active,52,50000,2500,500\nUAE_Retargeting,active,6,30000,600,300\n"
        "EGY_Broad,active,0,20000,100,200\n", encoding="utf-8")
    assert run("campaigns", "import", "--file", str(ws / "export.csv")).returncode == 0
    return run


def test_audit_grades_the_data_not_the_credentials(csv_workspace):
    res = csv_workspace("account", "audit", "--json")
    data = json.loads(res.stdout)["data"]
    assert data["mode"] == "csv" and 0 <= data["total"] <= 100
    assert {c["name"]: c["role"] for c in data["campaigns"]}["EGY_Broad"] == "waste"
    assert "credentials" not in json.loads(res.stdout)["output"].split("## Campaigns")[0]


def test_diagnose_skips_credential_check_and_ranks_confirmed_waste_first(csv_workspace):
    out = json.loads(csv_workspace("account", "diagnose", "--json").stdout)
    assert "n/a" in out["output"] and "CSV mode" in out["output"]
    assert out["data"]["findings"][0]["layer"] == "Campaign efficiency"


def test_report_arabic_and_whatsapp_have_the_campaign_table_and_actions(csv_workspace):
    arabic = csv_workspace("account", "report", "--lang", "ar").stdout
    assert "KSA_Prospecting" in arabic and "افعل اليوم" in arabic and "أوقف" in arabic
    digest = csv_workspace("account", "report", "--lang", "en", "--format", "whatsapp").stdout
    assert "Do today" in digest and "EGY_Broad" in digest


def test_results_based_conversions_are_never_called_scale():
    rows = [row("Reach", 100, 400), row("Sales", 400, 40)]
    assert {c["role"] for c in analyse(rows)["campaigns"]} >= {"winner"}
    capped = analyse(rows, results_based=True)
    assert "winner" not in {c["role"] for c in capped["campaigns"]}
    assert any("Results column" in f["finding"] for f in capped["findings"])


def test_target_cpa_must_be_a_positive_finite_number():
    from types import SimpleNamespace
    from commands.state import resolve_target_cpa
    tenant = SimpleNamespace(env={})
    for bad in ("0", "-5", "nan", "inf", "abc"):
        assert resolve_target_cpa(tenant, {"target_cpa": bad}) is None
    assert resolve_target_cpa(tenant, {"target_cpa": "12.5"}) == 12.5


def test_tenant_with_connected_accounts_keeps_the_setup_audit(tmp_path):
    env = {**os.environ, "FOUNDRY_WORKSPACE": str(tmp_path), "PYTHONIOENCODING": "utf-8"}

    def run(*args):
        return subprocess.run([sys.executable, str(ROOT / "foundry.py"), *args, "--client", "Acme"],
                              cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8", timeout=60, check=False)

    run("setup", "init")
    with open(tmp_path / "02_Active_Clients" / "Acme" / ".env", "a", encoding="utf-8") as handle:
        handle.write("\nMETA_ACCESS_TOKEN=real_token_value_123\nMETA_AD_ACCOUNT_ID=111222333\n")
    (tmp_path / "e.csv").write_text("Campaign,Cost,Impressions,Clicks,Conversions\nA,10,1000,50,2\n", encoding="utf-8")
    run("campaigns", "import", "--file", str(tmp_path / "e.csv"))
    out = json.loads(run("account", "audit", "--json").stdout)
    assert out["data"].get("mode") != "csv"


def test_paused_rows_stay_in_totals_but_are_never_actioned():
    rows = [dict(row("Live", 500, 50), status="ENABLED"), dict(row("Old", 400, 4), status="PAUSED"),
            dict(row("Dead", 300, 0), status="PAUSED")]
    got = analyse(rows)
    assert got["totals"]["cost"] == 1200
    assert got["by_role"]["waste"] == [] and got["by_role"]["loser"] == []
    assert all(f["layer"] != "Campaign efficiency" for f in got["findings"])


def test_missing_clicks_column_drops_ctr_instead_of_reporting_zero():
    got = analyse([row("A", 500, 50, impr=100000, clicks=0), row("B", 500, 40, impr=90000, clicks=0)], has_clicks=False)
    assert "traffic" not in got["score"]["components"]
    assert abs(sum(c["weight"] for c in got["score"]["components"].values()) - 1.0) < 1e-9
    assert all(f["layer"] != "Traffic quality" for f in got["findings"])


def test_adset_export_without_clicks_like_a_real_meta_download(tmp_path):
    """Header copied from a real Meta ad-set export (generic names): no clicks column, repeated ad set names,
    campaign-budget text in the budget column, one result type."""
    from commands.csv_import import parse_export
    text = (
        '"Reporting starts","Reporting ends","Ad set name","Ad set delivery","Results","Result indicator",'
        '"Ad set budget","Ad set budget type","Amount spent (AED)",Impressions\n'
        '2026-09-27,2026-10-26,"Ad set A",active,10225,actions:mobile_app_install,70,Daily,2258,1180575\n'
        '2026-09-27,2026-10-26,"Ad set A",inactive,2796,actions:mobile_app_install,"Using campaign budget",0,1058.43,573724\n')
    path = tmp_path / "adsets.csv"
    path.write_text(text, encoding="utf-8")
    got = parse_export(path)
    assert [r["name"] for r in got["rows"]] == ["Ad set A", "Ad set A (2)"]
    assert got["level"] == "ad set" and got["period"] == "2026-09-27 to 2026-10-26"
    assert got["conversions_basis"] == "mobile_app_install" and got["currency"] == "AED"
    assert got["rows"][1]["status"] == "PAUSED" and got["rows"][1]["budget"] == 0
    assert any("No clicks column" in w for w in got["warnings"])
