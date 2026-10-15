"""The read-only commands must run with ONLY the standard library (ChatGPT's code
interpreter and other minimal sandboxes). Blocks dotenv/yaml/requests/google at import."""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BLOCK = textwrap.dedent('''
    import importlib.abc, sys
    class _Block(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in {"dotenv", "yaml", "requests", "google", "pandas"}:
                raise ImportError(f"blocked for stdlib-only test: {name}")
    sys.meta_path.insert(0, _Block())
    sys.argv = ["foundry.py"] + sys.argv[1:]
    import runpy
    runpy.run_path(%r, run_name="__main__")
''') % str(ROOT / "foundry.py")


@pytest.fixture(scope="module")
def ws(tmp_path_factory):
    path = tmp_path_factory.mktemp("stdlib_ws")
    assert run(path, "setup", "init", "--client", "Acme").returncode == 0
    (path / "02_Active_Clients" / "Acme" / ".env").write_text(
        "# comment\nexport OPERATOR_NAME='Omar K'\nTARGET_CPA=120 # inline\nEMPTY=\n", encoding="utf-8")
    return path


def run(cwd, *args):
    env = {**os.environ, "FOUNDRY_WORKSPACE": str(cwd), "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, "-c", BLOCK, *args], cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=90, encoding="utf-8")


@pytest.mark.parametrize("args", [
    ("account", "audit", "--client", "Acme"),
    ("account", "diagnose", "--client", "Acme"),
    ("account", "report", "--client", "Acme", "--lang", "ar"),
    ("economics", "breakeven", "--price", "499", "--cogs", "150"),
    ("campaigns", "list", "--client", "Acme"),
    ("tenants", "list"),
    ("setup", "doctor"),
])
def test_command_runs_without_third_party_packages(ws, args):
    r = run(ws, *args)
    assert "blocked for stdlib-only" not in r.stderr, r.stderr
    assert r.returncode in (0, 1), r.stderr      # doctor reports missing optional deps as exit 1


def test_fallback_env_parser_matches_dotenv_semantics(ws):
    r = run(ws, "account", "audit", "--client", "Acme", "--json")
    data = json.loads(r.stdout)
    assert data["ok"] is True
    assert "operator=set" in data["output"] and "target CPA=set" in data["output"]


def test_live_ops_degrade_cleanly_without_network_libs(ws):
    r = run(ws, "live", "pull", "--client", "Acme")
    assert r.returncode != 0 and "Traceback" not in r.stderr
