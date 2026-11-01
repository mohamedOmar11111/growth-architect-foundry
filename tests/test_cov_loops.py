"""In-process coverage for loops/content_engine, social_calendar and lead_qualify (offline: Telegram stubbed)."""
import datetime

import pytest
import requests

from cov_helpers import make_tenant, patch_workspace
from loops import content_engine, social_calendar, lead_qualify
from signals import write_signal, read_signals
from commands.state import read_tasks
from telegram import TelegramConfigError


# ---- content_engine -------------------------------------------------------------------------------
def idea(t, summary="Winning angle: free shipping", priority="high"):
    return write_signal(t, loop="ad-intel", source="ads-platform", type_="content-idea", priority=priority,
                        action_needed=True, summary=summary, detail="CTR 6% on shipping hook",
                        suggested_action="Expand into a blog post", slug=summary)


def test_content_engine_turns_idea_into_brief_task_and_links_signal(monkeypatch, tmp_path, capsys):
    t = make_tenant(monkeypatch, tmp_path, env="OPERATOR_NAME=Sam\n")
    sig = idea(t)
    assert content_engine.run(t) == 0
    briefs = list((t.root / "02_Content").glob("*-brief.md"))
    assert len(briefs) == 1 and "winning-angle-free-shipping" in briefs[0].name
    text = briefs[0].read_text(encoding="utf-8")
    assert "Winning angle: free shipping" in text and "CTR 6% on shipping hook" in text
    assert "Expand into a blog post" in text and "Sam must review" in text
    tasks = read_tasks(t)
    assert len(tasks) == 1 and tasks[0]["domain"] == "content-engine" and tasks[0]["priority"] == "high"
    assert tasks[0]["linked-signal"] == sig.name
    assert read_signals(t, unprocessed_only=True) == []
    assert "1 signal(s) processed, 0 skipped" in capsys.readouterr().out
    assert "content-engine (Growth Engine)" in (tmp_path / "log.md").read_text(encoding="utf-8")


def test_content_engine_is_idempotent_and_ignores_other_types(monkeypatch, tmp_path, capsys):
    t = make_tenant(monkeypatch, tmp_path)
    idea(t)
    write_signal(t, loop="manual", source="manual", type_="risk", priority="low", action_needed=False,
                 summary="not content", detail="d", suggested_action="a", slug="risk")
    content_engine.run(t)
    content_engine.run(t)
    assert len(list((t.root / "02_Content").glob("*-brief.md"))) == 1
    assert len(read_tasks(t)) == 1
    assert "0 signal(s) processed" in capsys.readouterr().out


def test_content_engine_empty_bus_writes_nothing(monkeypatch, tmp_path):
    t = make_tenant(monkeypatch, tmp_path)
    assert content_engine.run(t) == 0
    assert not list((t.root / "02_Content").glob("*")) and not (tmp_path / "log.md").exists()


def test_content_engine_helpers_fall_back():
    assert content_engine._extract_section("no headers", "## Summary", "dflt") == "dflt"
    assert content_engine._slugify("A  B!!c") == "a-b-c"


def test_brief_without_strategy_asks_to_confirm_voice(monkeypatch, tmp_path):
    t = make_tenant(monkeypatch, tmp_path, strategy="   \n")
    idea(t)
    sig = read_signals(t)[0]
    _, content = content_engine._draft_brief(t, sig, "x")
    assert "No STRATEGY.md content loaded" in content


# ---- social_calendar ------------------------------------------------------------------------------
def brief(t, name):
    d = t.root / "02_Content"
    d.mkdir(exist_ok=True)
    p = d / name
    p.write_text("# brief\n", encoding="utf-8")
    return p


def test_strategy_directives_and_platform_choice():
    avoid, prefer = social_calendar._strategy_directives(
        "AVOID: TikTok — off brand\nPREFER: LinkedIn — B2B\nrandom line\nAVOID reddit")
    assert avoid == {"tiktok", "reddit"} and prefer == {"linkedin"}
    assert social_calendar._pick_platform(avoid, prefer, {p: 0 for p in social_calendar.PLATFORMS}) == "linkedin"
    freq = {"twitter": 3, "linkedin": 0, "instagram": 1, "tiktok": 0, "reddit": 0}
    assert social_calendar._pick_platform({"linkedin"}, set(), freq) in ("tiktok", "reddit")
    # every platform avoided -> falls back instead of crashing
    assert social_calendar._pick_platform(set(social_calendar.PLATFORMS), set(), {}) in social_calendar.PLATFORMS
    assert social_calendar._format_target("tiktok") == "short-form video script"
    assert social_calendar._format_target("mastodon") == "post"


def test_schedules_briefs_once_with_cadence_balance(monkeypatch, tmp_path, capsys):
    t = make_tenant(monkeypatch, tmp_path, strategy="PREFER: linkedin — B2B\nPREFER: twitter — reach\n")
    brief(t, "a-brief.md")
    brief(t, "b-brief.md")
    assert social_calendar.run(t) == 0
    cal = (t.root / "02_Content" / "calendar" / "content_calendar.md").read_text(encoding="utf-8")
    rows = [ln for ln in cal.splitlines() if ln.startswith("| 20")]
    assert len(rows) == 2 and all("DRAFT" in r for r in rows)
    platforms = [r.split("|")[2].strip() for r in rows]
    assert sorted(platforms) == ["linkedin", "twitter"]                  # second brief goes to the less-used one
    dates = [r.split("|")[1].strip() for r in rows]
    assert datetime.date.fromisoformat(dates[1]) - datetime.date.fromisoformat(dates[0]) == datetime.timedelta(days=1)
    assert social_calendar.SCHEDULED_MARKER in (t.root / "02_Content" / "a-brief.md").read_text(encoding="utf-8")
    assert [x["domain"] for x in read_tasks(t)] == ["social-calendar"] * 2
    assert "2 brief(s) scheduled, 0 skipped" in capsys.readouterr().out
    # second run: nothing pending, calendar and tasks unchanged
    social_calendar.run(t)
    assert len(read_tasks(t)) == 2
    assert "0 brief(s) scheduled" in capsys.readouterr().out


def test_no_content_dir_creates_empty_calendar(monkeypatch, tmp_path):
    t = make_tenant(monkeypatch, tmp_path)
    assert social_calendar.run(t) == 0
    cal = t.root / "02_Content" / "calendar" / "content_calendar.md"
    assert cal.read_text(encoding="utf-8").startswith("# Content Calendar")
    assert read_tasks(t) == [] and not (tmp_path / "log.md").exists()


def test_platform_frequency_counts_only_recent_known_rows(tmp_path):
    cal = tmp_path / "c.md"
    today = datetime.date.today()
    old = today - datetime.timedelta(days=60)
    cal.write_text(f"| {today} | LinkedIn | x | b | DRAFT |\n| {old} | tiktok | x | b | DRAFT |\n"
                   f"| {today} | myspace | x | b | DRAFT |\n| 2026-99-99 | reddit | x | b | DRAFT |\n"
                   "garbage\n", encoding="utf-8")
    f = social_calendar._platform_frequency(cal)
    assert f["linkedin"] == 1 and f["tiktok"] == 0 and f["reddit"] == 0
    assert social_calendar._platform_frequency(tmp_path / "missing.md") == {p: 0 for p in social_calendar.PLATFORMS}


# ---- lead_qualify ---------------------------------------------------------------------------------
STATE_MD = ("last-run: never\nhot-leads-today: 0\n\n"
            "| Date | Name | Company | Score | Telegram Sent | Draft File | Status |\n|---|---|---|---|---|---|---|\n\n"
            "| Name | Company | Sector | Source | S-Score | Status | Draft | Last Touch | Notes |\n"
            "|---|---|---|---|---|---|---|---|---|\n")


def lead_signal(root, slug, name, company, body, company_size="unknown", icp="unknown"):
    d = root / "signals"
    d.mkdir(exist_ok=True)
    p = d / f"2026-11-01-pipeline-{slug}.md"
    p.write_text(
        "---\ndate: '2026-11-01'\ntime: '09:00'\nsource: whatsapp\nbusiness: pipeline\nloop: manual\ntype: lead\n"
        f"priority: high\naction-needed: 'yes'\nlinked-task: none\nname: {name}\ncompany: {company}\n"
        f"company_size: {company_size}\nicp: {icp}\n---\n\n## Summary\n{body}\n", encoding="utf-8")
    return p


@pytest.fixture
def lq(monkeypatch, tmp_path):
    patch_workspace(monkeypatch, tmp_path)
    sent = []
    monkeypatch.setattr(lead_qualify, "send_message", sent.append)
    state = tmp_path / "domain" / "lead-qualify" / "STATE.md"
    state.parent.mkdir(parents=True)
    state.write_text(STATE_MD, encoding="utf-8")
    return tmp_path, sent, state


def test_score_lead_tiers():
    hot = lead_qualify._score_lead({"company_size": "Enterprise", "icp": "panicked-cto",
                                    "_body": "Need pricing and a proposal for ads"})
    assert (hot["budget_score"], hot["authority_score"], hot["intent_score"], hot["total"], hot["tier"]) == (40, 25, 35, 100, "HOT")
    warm = lead_qualify._score_lead({"company_size": "small", "icp": "marketing-director", "_body": "marketing help"})
    assert warm["total"] == 60 and warm["tier"] == "WARM"
    cold = lead_qualify._score_lead({"_body": "hi"})
    assert cold["total"] == 15 and cold["tier"] == "COLD" and "Engagement only" in cold["intent_reason"]
    assert lead_qualify._score_intent("x" * 41)[0] == 20
    assert lead_qualify._extract_summary("no header at all") == "no header at all"


def test_run_scores_routes_and_records(lq, capsys):
    root, sent, state = lq
    lead_signal(root, "hot", "Nour", "Acme Co", "Need pricing for ads and a proposal", "enterprise", "panicked-cto")
    lead_signal(root, "warm", "Omar", "Beta", "marketing help please", "small", "marketing-director")
    lead_signal(root, "cold", "Zed", "Gamma", "hi")
    assert lead_qualify.run() in (0, None)
    out = capsys.readouterr().out
    assert "1 HOT, 1 WARM, 1 COLD" in out
    assert len(sent) == 1 and "HOT LEAD: Nour @ Acme Co | Score: 100/100" in sent[0]
    drafts = root / "domain" / "lead-qualify" / "drafts"
    hot = next((drafts / "HOT").glob("*.md")).read_text(encoding="utf-8")
    assert "NOT SENT" in hot and "Nour @ Acme Co" in hot and "digital infrastructure" in hot
    assert next((drafts / "WARM").glob("*.md"))
    assert not (drafts / "COLD").exists()
    st = state.read_text(encoding="utf-8")
    assert "hot-leads-today: 1" in st and "| Nour | Acme Co | 100 | DELIVERED |" in st
    assert "| Omar | Beta |" in st
    log = (root / "log.md").read_text(encoding="utf-8")
    assert "lead-qualify" in log and "Items: 2 actioned, 1 skipped" in log
    # idempotent: everything linked now
    assert lead_qualify.read_signals(type_="lead", unprocessed_only=True) == []
    lead_qualify.run()
    assert len(sent) == 1


def test_hot_alert_failure_is_recorded_not_hidden(lq, monkeypatch, capsys):
    root, sent, state = lq

    def boom(_):
        raise TelegramConfigError("no token")
    monkeypatch.setattr(lead_qualify, "send_message", boom)
    lead_signal(root, "hot", "Nour", "Acme", "pricing proposal", "enterprise", "founder-ceo")
    lead_qualify.run()
    assert "Telegram HOT alert FAILED" in capsys.readouterr().out
    assert "FAILED — no token" in state.read_text(encoding="utf-8")


def test_network_error_also_recorded(lq, monkeypatch):
    root, _, state = lq

    def boom(_):
        raise requests.ConnectionError("offline")
    monkeypatch.setattr(lead_qualify, "send_message", boom)
    lead_signal(root, "hot", "Nour", "Acme", "pricing proposal", "enterprise", "founder-ceo")
    lead_qualify.run()
    assert "FAILED — offline" in state.read_text(encoding="utf-8")


def test_empty_bus_and_missing_state_file(monkeypatch, tmp_path, capsys):
    patch_workspace(monkeypatch, tmp_path)
    monkeypatch.setattr(lead_qualify, "send_message", lambda _t: None)
    lead_qualify.run()                                  # no signals dir, no STATE.md: must not crash
    assert "Scored 0 pending lead signal(s)" in capsys.readouterr().out
    lead_qualify._update_state(["| x |"], [], 1, 0)       # STATE.md absent -> silent no-op
    assert not (tmp_path / "domain" / "lead-qualify" / "STATE.md").exists()
