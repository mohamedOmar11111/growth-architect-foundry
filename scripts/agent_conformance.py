"""Drive the REAL agent CLIs (OpenCode, Codex) to prove Foundry is discoverable (conformance level L0).

    python scripts/agent_conformance.py            # skips agents that are not installed
    python scripts/agent_conformance.py --require  # fail if an agent is missing (CI)

Everything runs in throwaway folders with a throwaway HOME, so your real agent
configs are never touched. It does not call any model.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILL = "growth-architect-foundry"
TIMEOUT = 180


def _run(cmd: list[str], cwd: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, timeout=TIMEOUT, encoding="utf-8",
                          errors="replace", check=False)


def _sandbox_env(home: Path) -> dict:
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home), "CI": "1"}
    env.pop("FOUNDRY_WORKSPACE", None)
    return env


def check_opencode(workspace: Path, home: Path) -> str:
    exe = shutil.which("opencode")
    if not exe:
        return "SKIP: opencode not installed"
    env = _sandbox_env(home)
    done = _run([exe, "debug", "skill"], workspace, env)
    if done.returncode != 0:
        return f"FAIL: `opencode debug skill` exited {done.returncode}: {done.stderr[-200:]}"
    try:
        skills = json.loads(done.stdout)
    except ValueError:
        return "FAIL: `opencode debug skill` did not print JSON"
    found = [s for s in skills if s.get("name") == SKILL]
    if not found:
        return f"FAIL: skill not discovered among {len(skills)} skills"
    if str(workspace.resolve()).lower() not in str(found[0].get("location", "")).lower():
        return f"FAIL: skill found at unexpected location {found[0].get('location')}"
    return "PASS: skill discovered from .agents/skills"


def check_codex(workspace: Path, home: Path) -> str:
    """`codex debug prompt-input` prints the model-visible prompt as JSON without calling a model."""
    exe = shutil.which("codex")
    if not exe:
        return "SKIP: codex not installed"
    env = _sandbox_env(home)
    done = _run([exe, "debug", "prompt-input", "hello"], workspace, env)
    text = done.stdout + done.stderr
    if done.returncode != 0 and SKILL not in text:
        return f"FAIL: `codex debug prompt-input` exited {done.returncode}: {text[-200:]}"
    for needle, what in ((SKILL, "skill"), ("Section 0: Foundry", "AGENTS.md block")):
        if needle not in text:
            return f"FAIL: {what} missing from Codex's model-visible prompt"
    return "PASS: skill listed and AGENTS.md block loaded in Codex's prompt"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", maxsplit=1)[0])
    parser.add_argument("--require", action="store_true", help="fail when an agent is not installed")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="foundry_conf_") as tmp:
        base = Path(tmp)
        workspace, home = base / "ws", base / "home"
        workspace.mkdir()
        home.mkdir()
        installer = REPO / "scripts" / "install_agent.py"
        installed = subprocess.run([sys.executable, str(installer), "--workspace", str(workspace)],
                                   capture_output=True, text=True, check=False)
        if installed.returncode != 0:
            print(f"FAIL: installer: {installed.stderr[-300:]}")
            return 1
        results = {"opencode": check_opencode(workspace, home),
                   "codex": check_codex(workspace, home)}

    failed = False
    for name, result in results.items():
        print(f"[{name}] {result}")
        failed |= result.startswith("FAIL") or (args.require and result.startswith("SKIP"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
