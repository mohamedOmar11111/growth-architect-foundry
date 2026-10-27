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
                              cwd=ws, env=env, capture_output=True, text=True, timeout=60, check=False)

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
