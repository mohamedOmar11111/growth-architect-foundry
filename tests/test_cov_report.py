"""In-process coverage for report.py + perf_text.py: EN/AR, markdown/WhatsApp, CSV and queue modes."""
import pytest

from cov_helpers import make_tenant, import_csv
from commands import report, perf, perf_text
from signals import write_signal
from tasks import write_task


def queue_tenant(mp, tp):
    t = make_tenant(mp, tp)
    write_signal(t, loop="manual", source="manual", type_="risk", priority="high", action_needed=True,
                 summary="CPA doubled on KSA", detail="d", suggested_action="a", slug="cpa")
    write_task(t, domain="ads", priority="high", task_summary="Fix KSA bidding", context="c",
               acceptance_criteria=["a", "b"], linked_signal="none", slug="fix")
    (t.root / "02_Content").mkdir()
    (t.root / "02_Content" / "x-brief.md").write_text("b", encoding="utf-8")
    return t


def test_queue_report_english(monkeypatch, tmp_path, capsys):
    t = queue_tenant(monkeypatch, tmp_path)
    assert report.run(t, {}) == 0
    out = capsys.readouterr().out
    assert "2 decision(s) waiting on you this week" in out
    assert "Task: ads" in out
    assert "social-calendar (briefs exist, no calendar)" in out and "ad-intel (no captured report yet)" in out
    assert "Last engine run: never" in out
    assert list(t.reports_dir.glob("*-report-week-en.md"))
    assert "report generated (en)" in (tmp_path / "log.md").read_text(encoding="utf-8")


def test_queue_report_arabic_month(monkeypatch, tmp_path, capsys):
    t = queue_tenant(monkeypatch, tmp_path)
    assert report.run(t, {"lang": "ar", "period": "month"}) == 0
    out = capsys.readouterr().out
    assert "تقرير الشهر" in out and "**الخلاصة:**" in out and "## قرارات مطلوبة" in out
    assert "لم يُشغَّل بعد" in out
    assert list(t.reports_dir.glob("*-report-month-ar.md"))


def test_clean_queue_report(monkeypatch, tmp_path, capsys):
    t = make_tenant(monkeypatch, tmp_path)
    report.run(t, {})
    out = capsys.readouterr().out
    assert "queue is clean" in out and "No engine runs logged" in out
    report.run(t, {"lang": "ar"})
    assert "لا يوجد ما ينتظر قراراً" in capsys.readouterr().out


def test_whatsapp_digest_en_and_ar(monkeypatch, tmp_path, capsys):
    t = queue_tenant(monkeypatch, tmp_path)
    assert report.run(t, {"format": "whatsapp"}) == 0
    en = capsys.readouterr().out
    assert "Executive Digest" in en and "Reply OK to approve" in en and "1. " in en
    assert report.run(t, {"format": "whatsapp", "lang": "ar"}) == 0
    ar = capsys.readouterr().out
    assert "ملخص الأداء" in ar and "رد بـ OK للاعتماد" in ar and "1. " in ar
    assert list(t.reports_dir.glob("*-whatsapp.txt"))


def test_whatsapp_clean_queue_both_langs(monkeypatch, tmp_path, capsys):
    t = make_tenant(monkeypatch, tmp_path)
    report.run(t, {"format": "whatsapp"})
    assert "Queue is clean" in capsys.readouterr().out
    report.run(t, {"format": "whatsapp", "lang": "ar"})
    assert "لا توجد قرارات معلقة" in capsys.readouterr().out


@pytest.mark.parametrize("opts,code,msg", [
    ({"lang": "fr"}, 1, "unsupported --lang"),
    ({"period": "year"}, 1, "unsupported --period"),
    ({"format": "pdf"}, 2, "unsupported --format"),
])
def test_invalid_options(monkeypatch, tmp_path, capsys, opts, code, msg):
    t = make_tenant(monkeypatch, tmp_path)
    assert report.run(t, opts) == code
    cap = capsys.readouterr()
    assert msg in cap.out + cap.err


def test_csv_report_en_ar_whatsapp(monkeypatch, tmp_path, capsys):
    t = make_tenant(monkeypatch, tmp_path)
    import_csv(t, tmp_path)
    capsys.readouterr()
    assert report.run(t, {"lang": "en"}) == 0
    en = capsys.readouterr().out
    assert "Performance Report" in en and "| EGY_Broad |" in en and "Stop" in en and "Draft:" in en
    assert report.run(t, {"lang": "ar"}) == 0
    ar = capsys.readouterr().out
    assert "تقرير الأداء" in ar and "**الخلاصة:**" in ar and "أوقف" in ar and "مسودة" in ar
    assert report.run(t, {"lang": "ar", "format": "whatsapp"}) == 0
    wa = capsys.readouterr().out
    assert "ملخص الأداء" in wa and "*افعل اليوم:*" in wa
    assert report.run(t, {"format": "whatsapp"}) == 0
    assert "Performance Digest" in capsys.readouterr().out
    assert list(t.reports_dir.glob("*-report-ar-whatsapp.txt"))


# --- perf_text directly -------------------------------------------------------------------------
def row(name, cost, conv, impr=10000, clicks=300, **kw):
    return {"name": name, "cost": cost, "conversions": conv, "impressions": impr, "clicks": clicks, **kw}


def test_audit_text_scores_roles_and_fixes():
    a = perf.analyse([row("A", 500, 50), row("B", 300, 6), row("C", 200, 0)])
    out = perf_text.format_audit("Acme", "2026-11-01", a, "USD", "mobile_app_install")
    assert "Performance Audit" in out and "## Score components" in out
    assert "| C |" in out and "| Stop |" in out and "| Scale |" in out
    assert "Results counted as: mobile_app_install" in out
    assert "Confidence" in out


def test_no_conversions_withholds_score_in_both_languages():
    a = perf.analyse([row("A", 500, 0), row("B", 500, 0)])
    en = perf_text.format_report("Acme", "d", a, "USD", "en")
    ar = perf_text.format_report("Acme", "d", a, "USD", "ar")
    assert "No score: there are no conversions to judge." in en
    assert "لا توجد درجة" in ar
    assert perf_text.build_actions(a, "en")["today"] == [perf_text.T["en"]["today_track"]]
    assert perf_text.build_actions(a, "ar")["today"] == [perf_text.T["ar"]["today_track"]]


def test_actions_loser_winner_concentration_and_empty():
    a = perf.analyse([row("A", 1500, 150), row("B", 500, 20)], target_cpa=20)
    acts = perf_text.build_actions(a, "en")
    assert "Cut the budget of B by 20%." in acts["today"][0]
    assert any("Raise A" in x for x in acts["test"]) and any("second campaign" in x for x in acts["test"])
    assert acts["stop"][0].startswith("B:")
    ok = perf_text.build_actions(perf.analyse([row("A", 100, 50), row("B", 100, 45)], target_cpa=2.2), "ar")
    assert ok["stop"] == [perf_text.T["ar"]["stop_none"]]


def test_provisional_and_no_clicks_labels():
    a = perf.analyse([row("A", 100, 5)])
    assert "(provisional)" in perf_text._score_line(a, "en")
    assert "مبدئية" in perf_text._score_line(a, "ar")
    assert perf_text._basis_note("mixed", "en") == []
    assert perf_text._basis_note("leads", "ar") == ["المحتسب كنتيجة: leads"]
    a["has_clicks"] = False
    assert "| CTR | n/a |" in perf_text.format_report("T", "d", a, None, "en")
