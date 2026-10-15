"""Build the ChatGPT (Custom GPT) pack: an offline engine zip + instructions + knowledge files.

    python scripts/build_chatgpt_pack.py              # writes dist/foundry-chatgpt/ and a .zip

The engine runs inside ChatGPT's Code Interpreter, which has no network, so live
ad-account writes are impossible there by construction. Only the standard library is needed.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "skills" / "growth-architect-foundry"
INSTRUCTIONS = REPO / "integrations" / "chatgpt" / "GPT_INSTRUCTIONS.md"
SANDBOX_HOME = "/mnt/data/foundry"
INSTRUCTION_LIMIT = 8000                      # Custom GPT builder cap (characters)
ENGINE_FILES = ("foundry.py", "LICENSE")
ENGINE_DIRS = ("core/engine", "02_Active_Clients/Aurora_Skincare", "domain")
SKIP = {"__pycache__", ".pytest_cache", ".env"}

SETUP = """# Set up the Foundry Custom GPT (about 5 minutes)

Needs a ChatGPT plan that can create GPTs, with Code Interpreter on.

1. ChatGPT, Explore GPTs, Create. Open the Configure tab.
2. Name: Foundry. Description: growth-ops analyst for ad agencies.
3. Instructions: paste the whole of GPT_INSTRUCTIONS.md (it is under 8,000 characters).
4. Capabilities: tick Code Interpreter & Data Analysis. Untick Web Browsing (the engine is offline
   on purpose, and a browsing GPT can be steered by web pages).
5. Knowledge: upload foundry-engine.zip and every file in the knowledge/ folder.
6. Do NOT add Actions or API keys. Live ad accounts are intentionally out of reach here.
7. Save as "Only me" first and test with the checklist below.

## Smoke test
- "Run setup doctor." Expect python OK and optional packages listed.
- "Create a client called Acme and audit it." Expect a score out of 100 and a report file.
- "Break-even for price 499, cogs 150, shipping 45, 85% confirmed, 78% delivered."
- "Pause my worst Meta campaign." Expect a refusal that points you to the local install.

## Honest limits
- The sandbox resets between conversations: download the workspace zip at the end, re-upload next time.
- Nothing here talks to Google or Meta. For live pulls and changes use the Claude Code, OpenCode or Codex install.
- The GPT builder cannot be automated, so this pack was tested by running the engine exactly as the
  GPT would (stdlib only, no network libraries); the ChatGPT UI side must be checked by you.
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


def build_engine_zip(out: Path) -> Path:
    stage = out / "_stage"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    for name in ENGINE_FILES:
        shutil.copyfile(REPO / name, stage / name)
    for rel in ENGINE_DIRS:
        _copy_tree(REPO / rel, stage / rel)
    zip_path = out / "foundry-engine.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(stage).as_posix())
    shutil.rmtree(stage)
    return zip_path


def build(out: Path) -> Path:
    text = INSTRUCTIONS.read_text(encoding="utf-8")
    if len(text) > INSTRUCTION_LIMIT:
        raise SystemExit(f"GPT_INSTRUCTIONS.md is {len(text)} chars; the builder cap is {INSTRUCTION_LIMIT}.")
    shutil.rmtree(out, ignore_errors=True)
    (out / "knowledge").mkdir(parents=True)
    (out / "GPT_INSTRUCTIONS.md").write_text(text, encoding="utf-8")
    (out / "SETUP.md").write_text(SETUP, encoding="utf-8")
    knowledge = {"SKILL.md": SKILL / "SKILL.md"}
    knowledge |= {f"ref-{p.name}": p for p in sorted((SKILL / "references").glob("*.md"))}
    for name, src in knowledge.items():
        body = src.read_text(encoding="utf-8").replace("@@FOUNDRY_HOME@@", SANDBOX_HOME)
        (out / "knowledge" / name).write_text(body, encoding="utf-8")
    build_engine_zip(out)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", maxsplit=1)[0])
    parser.add_argument("--out", type=Path, default=REPO / "dist" / "foundry-chatgpt")
    out = build(parser.parse_args(argv).out.resolve())
    archive = shutil.make_archive(str(out), "zip", out)
    print(f"Built {out}\nZipped {archive}\nNext: open {out / 'SETUP.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
