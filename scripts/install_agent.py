"""Install Foundry into a coding agent's workspace.

Works for any agent that reads Agent Skills from `.agents/skills/` (OpenCode,
Freebuff/Codebuff, ...) and/or `AGENTS.md` (OpenCode, Codex, Cursor, ...).

    python scripts/install_agent.py                  # install into the current folder
    python scripts/install_agent.py --scope user     # skill for every project (~/.agents/skills)
    python scripts/install_agent.py --workspace DIR

Copies files (no symlinks, so it works on Windows) and patches the Foundry home
path into the installed skill, so the agent knows where `foundry.py` lives.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILL = "growth-architect-foundry"
SENTINEL = "@@FOUNDRY_HOME@@"
BEGIN, END = "<!-- foundry:begin -->", "<!-- foundry:end -->"


def _patched(text: str) -> str:
    return text.replace(SENTINEL, REPO.as_posix())


def install_skill(base: Path) -> Path:
    """Copy the skill to <base>/.agents/skills/<name>/ with FOUNDRY_HOME filled in."""
    dest = base / ".agents" / "skills" / SKILL
    if dest.exists():
        if not (dest / "SKILL.md").is_file():
            raise SystemExit(f"{dest} exists and is not a Foundry skill; refusing to overwrite.")
        shutil.rmtree(dest)
    shutil.copytree(REPO / "skills" / SKILL, dest)
    skill_md = dest / "SKILL.md"
    skill_md.write_text(_patched(skill_md.read_text(encoding="utf-8")), encoding="utf-8")
    return dest


def _managed_block() -> str:
    """The Foundry section of the repo's AGENTS.md: the single source of truth."""
    text = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    start, end = text.index(BEGIN), text.index(END) + len(END)
    return _patched(text[start:end])


def upsert_agents_md(workspace: Path) -> Path:
    """Add or refresh the managed block in <workspace>/AGENTS.md, keeping user content."""
    path = workspace / "AGENTS.md"
    block = _managed_block()
    if not path.exists():
        path.write_text(block + "\n", encoding="utf-8")
        return path
    text = path.read_text(encoding="utf-8")
    if BEGIN in text and END in text:
        start, end = text.index(BEGIN), text.index(END) + len(END)
        text = text[:start] + block + text[end:]
    else:
        text = text.rstrip("\n") + "\n\n" + block + "\n"
    path.write_text(text, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", maxsplit=1)[0])
    parser.add_argument("--scope", choices=("project", "user"), default="project")
    parser.add_argument("--workspace", type=Path, default=Path.cwd(),
                        help="Your project folder (default: current directory).")
    args = parser.parse_args(argv)

    workspace = args.workspace.resolve()
    if workspace == REPO:
        print("Run this from YOUR project folder (the workspace), not from the Foundry folder.",
              file=sys.stderr)
        return 2

    base = Path.home() if args.scope == "user" else workspace
    skill_dir = install_skill(base)
    print(f"Installed skill: {skill_dir}")
    if args.scope == "project":
        print(f"Updated context: {upsert_agents_md(workspace)}")
    print(f"Foundry home: {REPO}\nNext: open your agent in {workspace} and say 'run foundry setup doctor'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
