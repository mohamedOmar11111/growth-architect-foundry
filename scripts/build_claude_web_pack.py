"""Build the claude.ai (web/desktop) pack: a plugin zip and a standalone skill zip.

    python scripts/build_claude_web_pack.py            # writes dist/foundry-claude-web/

claude.ai runs skills in a code-execution sandbox, so the engine ships *inside* the skill folder
(`engine/` next to SKILL.md) and the skill finds it by relative path. Nothing depends on
CLAUDE_PLUGIN_ROOT, slash commands or hooks. The engine needs only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILL_NAME = "growth-architect-foundry"
SKILL = REPO / "skills" / SKILL_NAME
ENGINE_FILES = ("foundry.py", "LICENSE")
ENGINE_DIRS = ("core/engine", "02_Active_Clients/Aurora_Skincare", "domain")
SKIP = {"__pycache__", ".pytest_cache", ".env"}
DESCRIPTION_LIMIT = 1024  # Agent Skills spec

HOME_BLOCK = re.compile(r"Foundry home \(the folder holding `foundry\.py`\): `@@FOUNDRY_HOME@@`\n.*?\n", re.S)
WEB_HOME = (
    "Foundry home (the folder holding `foundry.py`): the `engine/` folder next to this SKILL.md.\n"
    "If unsure where that is, run `find / -name foundry.py -path '*engine*' 2>/dev/null | head -1`.\n"
    "**claude.ai sandbox rules:** run from a scratch workspace (`export FOUNDRY_WORKSPACE=/tmp/foundry-ws`); "
    "it resets between chats, so hand the user the report files at the end. There is no live ad-account access "
    "here (no credentials, restricted network), so `live` commands are unavailable: audit, diagnose, reports, "
    "`campaigns import` and `economics` all work offline. For live pulls use the Claude Code install.\n"
)
SETUP = """# Use Foundry in claude.ai (web or desktop)

Option A, plugin (also appears in Cowork and Claude Code for your account):
1. claude.ai, Customize, Plugins, Add, Upload plugin, choose foundry-plugin.zip.
Option B, skill only:
1. claude.ai, Customize, Skills, Upload, choose growth-architect-foundry-skill.zip.

Turn on "Code execution and file creation" in Settings, Capabilities, or the skill cannot run the engine.

## Smoke test (new chat)
- "Run Foundry setup doctor." Expect python OK.
- "Create a client called Acme and audit it." Expect a score out of 100 and a report file.
- "Break-even for price 499, cogs 150, shipping 45, 85% confirmed, 78% delivered."
- "Pause my worst Meta campaign." Expect a refusal pointing to the local install.

## Limits
- Confirmed by the author: the plugin uploads and runs in claude.ai. The engine was also checked outside it,
  running exactly as it would there (stdlib only, separate workspace).
- Live Google/Meta access is intentionally out of reach on the web; use the Claude Code install.
"""


def _copy_tree(src: Path, dst: Path) -> None:
    for path in sorted(src.rglob("*")):
        if any(part in SKIP for part in path.parts) or path.suffix == ".pyc":
            continue
        target = dst / path.relative_to(src)
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)


def _stage_skill(dest: Path) -> None:
    """Skill folder with the engine bundled in engine/ and the home line rewritten for the web."""
    _copy_tree(SKILL, dest)
    engine = dest / "engine"
    for name in ENGINE_FILES:
        engine.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / name, engine / name)
    for rel in ENGINE_DIRS:
        _copy_tree(REPO / rel, engine / rel)
    skill_md = dest / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8").replace("\r\n", "\n")
    text, count = HOME_BLOCK.subn(WEB_HOME, text)
    if count != 1:
        raise SystemExit("SKILL.md home block not found; update HOME_BLOCK in build_claude_web_pack.py")
    description = re.search(r"description:\s*>\s*\n((?:  .*\n)+)", text)
    if description and len(" ".join(description.group(1).split())) > DESCRIPTION_LIMIT:
        raise SystemExit(f"skill description exceeds {DESCRIPTION_LIMIT} characters")
    skill_md.write_text(text, encoding="utf-8")


def _zip_dir(root: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(root).as_posix())


def build(out: Path) -> Path:
    shutil.rmtree(out, ignore_errors=True)
    stage = out / "_stage"
    plugin_root = stage / "plugin"
    _stage_skill(plugin_root / "skills" / SKILL_NAME)
    manifest = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    manifest.pop("commands", None)  # slash commands call ${CLAUDE_PLUGIN_ROOT}; not used on the web
    (plugin_root / ".claude-plugin").mkdir(parents=True)
    (plugin_root / ".claude-plugin" / "plugin.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _zip_dir(plugin_root, out / "foundry-plugin.zip")

    skill_only = stage / "skill" / SKILL_NAME
    _stage_skill(skill_only)
    _zip_dir(stage / "skill", out / f"{SKILL_NAME}-skill.zip")
    (out / "SETUP.md").write_text(SETUP, encoding="utf-8")
    shutil.rmtree(stage)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", maxsplit=1)[0])
    parser.add_argument("--out", type=Path, default=REPO / "dist" / "foundry-claude-web")
    out = build(parser.parse_args(argv).out.resolve())
    print(f"Built {out}\nNext: open {out / 'SETUP.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
