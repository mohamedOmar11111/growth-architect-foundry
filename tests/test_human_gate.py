"""Live writes need a person at a terminal, not just --confirm (agent-agnostic safety)."""
import builtins
import io
from types import SimpleNamespace
from unittest.mock import patch

from commands import live

META_ENV = {"META_ACCESS_TOKEN": "t", "META_AD_ACCOUNT_ID": "1"}


def _tenant(tmp_path):
    return SimpleNamespace(name="T", env=META_ENV, reports_dir=tmp_path,
                           require=lambda *k: tuple(META_ENV[x] for x in k))


def _camps():
    return {"meta:1": {"name": "c", "status": "ACTIVE", "cost": 1.0, "conversions": 0,
                       "budget": 100.0, "platform": "meta"}}


class _Tty(io.StringIO):
    def isatty(self):
        return True


def test_refused_without_terminal_even_with_confirm(tmp_path, capsys):
    """pytest (like an agent shell) has no TTY: --confirm alone must not write."""
    with patch.object(live, "_meta_pause_campaign") as pause:
        rc = live._cmd_pause(_tenant(tmp_path), _camps(), {"campaign_id": "meta:1", "confirm": True})
    assert rc == live.EXIT_REFUSED == 3
    pause.assert_not_called()
    assert "REFUSED" in capsys.readouterr().err


def test_budget_also_refused_without_terminal(tmp_path):
    with patch.object(live, "_meta_update_budget") as write:
        rc = live._cmd_budget(_tenant(tmp_path), _camps(),
                              {"campaign_id": "meta:1", "new_budget": 110, "confirm": True})
    assert rc == live.EXIT_REFUSED
    write.assert_not_called()


def test_typed_key_on_terminal_approves(monkeypatch):
    monkeypatch.setattr("sys.stdin", _Tty())
    monkeypatch.setattr("sys.stdout", _Tty())
    monkeypatch.setattr(builtins, "input", lambda *_: "meta:1")
    assert live._human_approved("meta:1") is True


def test_wrong_text_or_eof_on_terminal_refuses(monkeypatch):
    monkeypatch.setattr("sys.stdin", _Tty())
    monkeypatch.setattr("sys.stdout", _Tty())
    monkeypatch.setattr(builtins, "input", lambda *_: "yes")
    assert live._human_approved("meta:1") is False

    def eof(*_):
        raise EOFError
    monkeypatch.setattr(builtins, "input", eof)
    assert live._human_approved("meta:1") is False


def test_stdin_tty_but_stdout_piped_refuses(monkeypatch):
    monkeypatch.setattr("sys.stdin", _Tty())
    assert live._human_approved("meta:1") is False   # stdout is captured, not a tty


def test_preview_without_confirm_still_exits_zero_and_never_prompts(tmp_path):
    with patch.object(live, "_human_approved") as gate:
        rc = live._cmd_pause(_tenant(tmp_path), _camps(), {"campaign_id": "meta:1"})
    assert rc == 0
    gate.assert_not_called()
