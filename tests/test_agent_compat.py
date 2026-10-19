"""Every agent integration must stay valid: Agent Skills spec (OpenCode, Codebuff/Freebuff,
Codex), plugin manifests, and the cross-platform installer."""
import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _frontmatter(path):
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path} has no frontmatter"
    import yaml
    return yaml.safe_load(text.split("---\n", 2)[1])


def _skills():
    return sorted((ROOT / "skills").glob("*/SKILL.md"))


@pytest.mark.parametrize("skill", _skills(), ids=lambda p: p.parent.name)
def test_skill_follows_agent_skills_spec(skill):
    meta = _frontmatter(skill)
    assert meta["name"] == skill.parent.name          # OpenCode/Codebuff reject a mismatch
    assert 1 <= len(meta["name"]) <= 64 and NAME_RE.match(meta["name"])
    assert 1 <= len(meta["description"]) <= 1024
    assert all(isinstance(v, str) for v in meta.get("metadata", {}).values())


def test_versions_agree_across_plugin_formats():
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    codex = json.loads((ROOT / ".codex-plugin/plugin.json").read_text())
    assert plugin["version"] == market["plugins"][0]["version"] == codex["version"]


def test_agents_md_has_one_managed_block_and_sentinel():
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert text.count("<!-- foundry:begin -->") == text.count("<!-- foundry:end -->") == 1
    assert "@@FOUNDRY_HOME@@" in text
    assert "live pause" in text and "--confirm" in text    # safety rule must ship to every agent


def _installer():
    spec = importlib.util.spec_from_file_location("install_agent", ROOT / "scripts/install_agent.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_install_patches_home_and_leaves_no_sentinel(tmp_path):
    inst = _installer()
    dest = inst.install_skill(tmp_path)
    text = (dest / "SKILL.md").read_text(encoding="utf-8")
    assert dest == tmp_path / ".agents" / "skills" / "growth-architect-foundry"
    assert inst.REPO.as_posix() in text
    assert "Foundry home (the folder holding `foundry.py`): `@@" not in text
    assert (dest / "references").is_dir()


def test_agents_md_upsert_is_idempotent_and_keeps_user_content(tmp_path):
    inst = _installer()
    (tmp_path / "AGENTS.md").write_text("# My project\nKeep me.\n", encoding="utf-8")
    inst.upsert_agents_md(tmp_path)
    inst.upsert_agents_md(tmp_path)
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert text.count("<!-- foundry:begin -->") == 1
    assert text.startswith("# My project\nKeep me.\n")
    assert "@@FOUNDRY_HOME@@" not in text and inst.REPO.as_posix() in text


def test_install_refuses_foreign_directory(tmp_path):
    inst = _installer()
    foreign = tmp_path / ".agents" / "skills" / "growth-architect-foundry"
    foreign.mkdir(parents=True)
    (foreign / "mine.txt").write_text("user data")
    with pytest.raises(SystemExit):
        inst.install_skill(tmp_path)
    assert (foreign / "mine.txt").exists()


def test_installer_refuses_to_run_inside_foundry_repo(capsys):
    inst = _installer()
    assert inst.main(["--workspace", str(inst.REPO)]) == 2
    assert "YOUR project folder" in capsys.readouterr().err


def test_codex_plugin_manifest_is_complete_and_assets_exist():
    manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    assert NAME_RE.match(manifest["name"]) and manifest["license"] == "MIT"
    ui = manifest["interface"]
    assert len(ui["shortDescription"]) <= 120 and ui["defaultPrompt"]
    paths = [manifest["skills"], ui["composerIcon"], ui["logo"], *ui["screenshots"]]
    for rel in paths:
        assert rel.startswith("./") and ".." not in rel
        assert (ROOT / rel).exists(), rel
    for url in (ui["websiteURL"], ui["privacyPolicyURL"], ui["termsOfServiceURL"]):
        assert url.startswith("https://")


def test_codex_marketplace_points_at_this_plugin():
    market = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
    entry = market["plugins"][0]
    assert entry["name"] == "foundry" and entry["source"]["path"] == "./"
    assert entry["policy"]["installation"] and entry["policy"]["authentication"]


def test_no_credential_shaped_placeholders_in_bundled_personas():
    import re
    pattern = re.compile(r"password\s*[:=]\s*['\"][^'\"]+['\"]", re.IGNORECASE)
    for path in (ROOT / "01_Context_Vault").rglob("*.md"):
        assert not pattern.search(path.read_text(encoding="utf-8", errors="ignore")), path
