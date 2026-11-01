"""In-process coverage for diagnose.py: ladder verdicts, ranked findings, CSV mode, edge paths."""
import pytest

from cov_helpers import make_tenant, import_csv
from commands import diagnose

READY_ENV = ("OPERATOR_NAME=Sam\nGOOGLE_ADS_CLIENT_ID=a1\nGOOGLE_ADS_CLIENT_SECRET=a2\nGOOGLE_ADS_REFRESH_TOKEN=a3\n"
             "GOOGLE_ADS_DEVELOPER_TOKEN=a4\nGOOGLE_ADS_CUSTOMER_ID=a5\nMETA_ACCESS_TOKEN=b1\nMETA_AD_ACCOUNT_ID=b2\n")


def csv_text(rows):
    return "Campaign name,Delivery,Results,Impressions,Clicks (all),Amount spent (USD)\n" + "".join(
        f"{n},active,{c},{i},{k},{s}\n" for n, c, i, k, s in rows)


def ladder(diag):
    return {r["layer"]: r["verdict"] for r in diag["ladder"]}


def live_tenant(mp, tp, rows, extra=""):
    t = make_tenant(mp, tp, env=READY_ENV + extra)
    import_csv(t, tp, csv_text(rows))
    return t


def test_no_data_placeholder_credentials(monkeypatch, tmp_path, capsys):
    t = make_tenant(monkeypatch, tmp_path)
    opts = {"_extra": {}}
    assert diagnose.run(t, opts) == 0
    out = capsys.readouterr().out
    diag = opts["_extra"]["_data"]
    assert ladder(diag) == {"Tracking / config": "fail", "Attention / traffic / conversion": "unknown"}
    assert diag["bottleneck"] in ("Tracking / config", "Attention / traffic / conversion")
    assert "Ad credentials are placeholders" in out and "No ad-intel report exists" in out
    assert "No target CPA configured" in out or "judged as unknown" in out
    assert list(t.reports_dir.glob("*-diagnose.md"))


def test_high_priority_signal_and_stuck_task_surface(monkeypatch, tmp_path):
    from signals import write_signal
    from tasks import write_task
    t = make_tenant(monkeypatch, tmp_path)
    write_signal(t, loop="manual", source="manual", type_="risk", priority="high", action_needed=True,
                 summary="s", detail="d", suggested_action="a", slug="x")
    p = write_task(t, domain="ads", priority="low", task_summary="t", context="c",
                   acceptance_criteria=["a", "b"], linked_signal="none", slug="y")
    p.write_text(p.read_text(encoding="utf-8").replace("attempts: 0", "attempts: 3"), encoding="utf-8")
    from commands.state import collect_snapshot
    diag = diagnose.build_diagnosis(collect_snapshot(t), None)
    texts = " ".join(f["finding"] for f in diag["findings"])
    assert "1 high-priority signal(s)" in texts and "1 task(s) are stuck" in texts


def test_cpa_over_target_is_failing_and_top_fix_named(monkeypatch, tmp_path, capsys):
    t = live_tenant(monkeypatch, tmp_path, [("A", 52, 50000, 2500, 500), ("B", 6, 30000, 600, 300)])
    opts = {"_extra": {}, "target_cpa": 5}
    assert diagnose.run(t, opts) == 0
    diag = opts["_extra"]["_data"]
    assert ladder(diag)["Conversion"] == "fail" and ladder(diag)["Traffic quality"] == "pass"
    assert diag["bottleneck"] == "Conversion"
    assert "x target" in diag["findings"][0]["finding"]
    assert "Target CPA used: 5.00" in capsys.readouterr().out


def test_no_target_means_conversion_unknown_not_passing(monkeypatch, tmp_path):
    t = live_tenant(monkeypatch, tmp_path, [("A", 52, 50000, 2500, 500)])
    opts = {"_extra": {}}
    assert diagnose.run(t, opts) == 0
    diag = opts["_extra"]["_data"]
    assert ladder(diag)["Conversion"] == "unknown"
    assert any("No target CPA" in f["finding"] for f in diag["findings"])


def test_cpa_within_target_passes_and_nothing_to_fix(monkeypatch, tmp_path):
    from commands.state import collect_snapshot
    t = live_tenant(monkeypatch, tmp_path, [("A", 52, 50000, 2500, 500)], extra="TARGET_CPA=20\n")
    snap = collect_snapshot(t)
    d = diagnose.build_diagnosis(snap, 20.0)
    assert ladder(d)["Conversion"] == "pass" and d["findings"] == []
    assert d["bottleneck"].startswith("none")
    assert "Nothing to fix" in diagnose.format_diagnosis(t, snap, d, 20.0)


def test_zero_conversions_with_target(monkeypatch, tmp_path):
    t = live_tenant(monkeypatch, tmp_path, [("A", 0, 50000, 2500, 500)])
    from commands.state import collect_snapshot
    d = diagnose.build_diagnosis(collect_snapshot(t), 10.0)
    assert ladder(d)["Conversion"] == "fail"
    assert "zero conversions" in d["findings"][0]["finding"]


def test_low_delivery_and_weak_ctr(monkeypatch, tmp_path):
    from commands.state import collect_snapshot
    t = live_tenant(monkeypatch, tmp_path, [("A", 3, 500, 20, 50)])
    d = diagnose.build_diagnosis(collect_snapshot(t), 100.0)
    assert ladder(d)["Attention"] == "weak"
    assert any("too low to judge" in f["finding"] for f in d["findings"])


def test_weak_ctr_finding(monkeypatch, tmp_path):
    from commands.state import collect_snapshot
    t = live_tenant(monkeypatch, tmp_path, [("A", 30, 100000, 2000, 500)])
    d = diagnose.build_diagnosis(collect_snapshot(t), 100.0)
    assert ladder(d)["Traffic quality"] == "weak"          # 2.0% CTR
    assert any("not earning the click" in f["finding"] for f in d["findings"])


@pytest.mark.parametrize("ctr,verdict", [(5.0, "strong"), (3.0, "pass"), (1.0, "weak"), (0.5, "fail")])
def test_ctr_verdict_bands(ctr, verdict):
    assert diagnose._ctr_verdict(ctr)[0] == verdict


def test_csv_mode_skips_credential_check_and_adds_campaign_findings(monkeypatch, tmp_path, capsys):
    t = make_tenant(monkeypatch, tmp_path)
    import_csv(t, tmp_path)
    capsys.readouterr()
    opts = {"_extra": {}}
    assert diagnose.run(t, opts) == 0
    diag = opts["_extra"]["_data"]
    assert ladder(diag)["Tracking / config"] == "n/a"
    assert not any("placeholders" in f["finding"] for f in diag["findings"])
    assert any("EGY_Broad" in f["finding"] + f["evidence"] for f in diag["findings"])
    assert "CSV mode" in capsys.readouterr().out


def test_run_without_opts(monkeypatch, tmp_path):
    t = make_tenant(monkeypatch, tmp_path)
    assert diagnose.run(t) == 0
