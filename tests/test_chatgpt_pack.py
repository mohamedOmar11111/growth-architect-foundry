"""The ChatGPT pack must build within the GPT builder's limits and its engine must run from the
extracted zip the way Code Interpreter would run it: stdlib only, separate workspace."""
import importlib.util
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BLOCK = (
    "import importlib.abc, sys, runpy\n"
    "class B(importlib.abc.MetaPathFinder):\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name.split('.')[0] in {'dotenv', 'yaml', 'requests', 'google', 'pandas'}:\n"
    "            raise ImportError('blocked: ' + name)\n"
    "sys.meta_path.insert(0, B())\n"
    "script = sys.argv[1]\n"
    "sys.argv = sys.argv[1:]\n"
    "runpy.run_path(script, run_name='__main__')\n"
)


@pytest.fixture(scope="module")
def pack(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("build_pack", ROOT / "scripts/build_chatgpt_pack.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = tmp_path_factory.mktemp("pack") / "foundry-chatgpt"
    mod.build(out)
    return out


def test_instructions_fit_the_gpt_builder_limit(pack):
    text = (pack / "GPT_INSTRUCTIONS.md").read_text(encoding="utf-8")
    assert len(text) <= 8000
    for rule in ("no internet", "Never attempt live pause", "Never ask for, accept, or echo credentials",
                 "untrusted", "FOUNDRY_WORKSPACE"):
        assert rule in text


def test_knowledge_files_within_limits_and_home_patched(pack):
    files = sorted((pack / "knowledge").glob("*.md"))
    assert 1 <= len(files) + 1 <= 20            # +1 for the engine zip; GPTs allow 20 knowledge files
    joined = "".join(f.read_text(encoding="utf-8") for f in files)
    assert "@@FOUNDRY_HOME@@" not in joined and "/mnt/data/foundry" in joined


def test_engine_zip_has_what_it_needs_and_nothing_sensitive(pack):
    names = zipfile.ZipFile(pack / "foundry-engine.zip").namelist()
    assert "foundry.py" in names and "core/engine/paths.py" in names
    assert "02_Active_Clients/Aurora_Skincare/STRATEGY.md" in names
    assert not [n for n in names if n.endswith(".env") or "__pycache__" in n or n.endswith(".pyc")]
    assert not [n for n in names if n.startswith(("01_Context_Vault", "tests", ".git", "licenses"))]
    assert (pack / "foundry-engine.zip").stat().st_size < 5_000_000


@pytest.fixture(scope="module")
def sandbox(pack, tmp_path_factory):
    home = tmp_path_factory.mktemp("mnt_data") / "foundry"
    zipfile.ZipFile(pack / "foundry-engine.zip").extractall(home)
    workspace = tmp_path_factory.mktemp("mnt_data_ws")
    return home, workspace


def gpt_run(sandbox, *args):
    home, workspace = sandbox
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env.update(FOUNDRY_WORKSPACE=str(workspace), PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-c", BLOCK, str(home / "foundry.py"), *args, "--json"],
                          cwd=workspace, env=env, capture_output=True, text=True, timeout=90,
                          encoding="utf-8")


def test_gpt_workflow_runs_from_extracted_zip_offline(sandbox):
    assert gpt_run(sandbox, "setup", "init", "--client", "Acme").returncode in (0, 2)
    init = json.loads(gpt_run(sandbox, "setup", "init", "--client", "Acme2").stdout)
    assert init["ok"] is True
    audit = json.loads(gpt_run(sandbox, "account", "audit", "--client", "Acme2").stdout)
    assert audit["ok"] and 0 <= audit["data"]["total"] <= 100 and audit["report_path"]
    econ = json.loads(gpt_run(sandbox, "economics", "breakeven", "--price", "499", "--cogs", "150").stdout)
    assert econ["ok"] and econ["data"]["break_even_roas"] > 0
    report = json.loads(gpt_run(sandbox, "account", "report", "--client", "Acme2", "--lang", "ar").stdout)
    assert report["ok"]


def test_live_commands_cannot_act_inside_the_gpt_sandbox(sandbox):
    for verb in (("live", "pause", "--campaign-id", "meta:1", "--confirm"),
                 ("live", "budget", "--campaign-id", "meta:1", "--new-budget", "110", "--confirm")):
        r = gpt_run(sandbox, verb[0], verb[1], "--client", "Acme2", *verb[2:])
        env = json.loads(r.stdout)
        assert env["ok"] is False and r.returncode in (1, 3)
