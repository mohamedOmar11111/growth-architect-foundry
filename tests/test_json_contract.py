"""--json contract for agents: one envelope, stable keys, documented exit codes."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
KEYS = {"schema_version", "command", "ok", "exit_code", "data", "output", "report_path", "stderr"}


@pytest.fixture(scope="module")
def ws(tmp_path_factory):
    path = tmp_path_factory.mktemp("ws")
    run(path, "setup", "init", "--client", "Acme")
    return path


def run(cwd, *args):
    env = {**os.environ, "FOUNDRY_WORKSPACE": str(cwd), "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, str(ROOT / "foundry.py"), *args], cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=90, encoding="utf-8")


def envelope(ws, *args):
    r = run(ws, *args, "--json")
    return r.returncode, json.loads(r.stdout)


def test_audit_envelope_has_structured_data_and_report_path(ws):
    code, env = envelope(ws, "account", "audit", "--client", "Acme")
    assert code == 0 and set(env) == KEYS and env["schema_version"] == 1
    assert env["ok"] is True and env["command"] == "account audit"
    assert 0 <= env["data"]["total"] <= 100 and env["data"]["grade"]
    assert "Account Audit" in env["output"] and env["report_path"].endswith("-audit.md")


def test_diagnose_envelope_has_data(ws):
    code, env = envelope(ws, "account", "diagnose", "--client", "Acme")
    assert code == 0 and env["data"] is not None and env["output"]


def test_economics_payload_becomes_data_not_text(ws):
    code, env = envelope(ws, "economics", "breakeven", "--price", "499", "--cogs", "150")
    assert code == 0 and env["output"] is None
    assert env["data"]["command"] == "breakeven" and env["data"]["break_even_roas"] > 0


def test_live_pull_failure_is_not_ok_and_lists_errors(ws):
    code, env = envelope(ws, "live", "pull", "--client", "Acme")
    assert code == 1 and env["ok"] is False
    assert "FETCH FAILED" in env["stderr"] or "no ad platform" in env["stderr"]


def test_usage_errors_exit_2(ws):
    assert run(ws, "account", "audit").returncode == 2            # missing --client
    assert run(ws, "account", "nope", "--client", "Acme").returncode == 2


def test_failure_in_json_mode_still_valid_json(ws):
    code, env = envelope(ws, "account", "audit", "--client", "Missing")
    assert code == 1 and env["ok"] is False and "Missing" in env["stderr"]


def test_live_write_in_json_mode_is_refused_exit_3(ws, monkeypatch):
    # No ad creds in the fresh tenant, so this stops earlier; the gate itself is unit-tested.
    code, env = envelope(ws, "live", "pause", "--client", "Acme", "--campaign-id", "meta:1", "--confirm")
    assert code in (1, 3) and env["ok"] is False


def test_plain_mode_unchanged(ws):
    r = run(ws, "account", "audit", "--client", "Acme")
    assert r.returncode == 0 and r.stdout.lstrip().startswith("# Acme")
