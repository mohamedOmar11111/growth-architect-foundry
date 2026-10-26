"""The claude.ai pack must be self-contained: the engine runs from the extracted zip with only the
standard library, and the skill points at its bundled engine instead of CLAUDE_PLUGIN_ROOT."""
import importlib.util
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = "growth-architect-foundry"


@pytest.fixture(scope="module")
def pack(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("web_pack", ROOT / "scripts/build_claude_web_pack.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build(tmp_path_factory.mktemp("web") / "foundry-claude-web")


def test_plugin_zip_layout(pack, tmp_path):
    with zipfile.ZipFile(pack / "foundry-plugin.zip") as z:
        names = z.namelist()
        manifest = json.loads(z.read(".claude-plugin/plugin.json"))
    assert f"skills/{SKILL}/SKILL.md" in names
    assert f"skills/{SKILL}/engine/foundry.py" in names
    assert manifest["name"] == "foundry" and "commands" not in manifest
    assert not any(n.endswith(".env") or "__pycache__" in n for n in names)


def test_skill_zip_has_single_named_folder_and_web_home(pack, tmp_path):
    with zipfile.ZipFile(pack / f"{SKILL}-skill.zip") as z:
        assert {n.split("/")[0] for n in z.namelist()} == {SKILL}
        z.extractall(tmp_path)
    skill_md = (tmp_path / SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "@@FOUNDRY_HOME@@" not in skill_md
    assert "`engine/` folder next to this SKILL.md" in skill_md
    assert skill_md.startswith("---") and f"name: {SKILL}" in skill_md


def test_engine_runs_stdlib_only_from_extracted_skill(pack, tmp_path):
    with zipfile.ZipFile(pack / f"{SKILL}-skill.zip") as z:
        z.extractall(tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    env = {**os.environ, "FOUNDRY_WORKSPACE": str(ws), "PYTHONPATH": ""}
    block = (
        "import sys, runpy\n"
        "for m in ('dotenv', 'yaml', 'requests', 'google', 'pandas'):\n"
        "    sys.modules[m] = None\n"
        "sys.argv = sys.argv[1:]\n"
        "runpy.run_path(sys.argv[0], run_name='__main__')\n"
    )
    run = lambda *a: subprocess.run(  # noqa: E731
        [sys.executable, "-I", "-c", block, str(tmp_path / SKILL / "engine" / "foundry.py"), *a],
        cwd=ws, env=env, capture_output=True, text=True, check=False)
    assert run("setup", "init", "--client", "Acme").returncode == 0
    result = run("economics", "breakeven", "--price", "499", "--cogs", "150", "--shipping", "45", "--json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ok"] is True
