"""growth_engine.commands.setup — first-run helpers for plugin users.

  setup init --client <Name>   scaffold a new tenant in YOUR workspace
  setup doctor                 check Python, dependencies, workspace, tenants

Both are root commands (no existing tenant required). The workspace is the
folder you run Foundry from (or $FOUNDRY_WORKSPACE) — never the plugin cache,
so plugin updates cannot touch your client data.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import sys

from paths import CLIENTS_ROOT, ENGINE_ROOT, WORKSPACE

TEMPLATE_TENANT = ENGINE_ROOT / "02_Active_Clients" / "Aurora_Skincare"
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

# (import name, pip name, needed for)
DEPENDENCIES = (
    ("dotenv", "python-dotenv", "every command (tenant .env loading)"),
    ("yaml", "pyyaml", "loops / config"),
    ("requests", "requests", "Meta Ads + LLM shim"),
    ("google.ads.googleads", "google-ads", "Google Ads live operations (optional)"),
)


def _write_private(path, text: str) -> None:
    """Create a credentials file owner-read/write only (0o600) from the start,
    so there is no window where it is group/world readable. (No-op for the
    mode bits on Windows, where ACLs apply instead.)"""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)


def cmd_init(opts: dict) -> int:
    name = opts.get("client")
    if not name or not NAME_RE.match(name):
        print("ERROR: --client must be a plain folder name (letters, digits, _ or -), "
              "e.g. `setup init --client Acme_Store`.", file=sys.stderr)
        return 2
    if not TEMPLATE_TENANT.is_dir():
        print(f"ERROR: tenant template missing at {TEMPLATE_TENANT}.", file=sys.stderr)
        return 1

    target = CLIENTS_ROOT / name
    if target.exists():
        print(f"ERROR: {target} already exists — refusing to overwrite.", file=sys.stderr)
        return 1

    shutil.copytree(TEMPLATE_TENANT, target, ignore=shutil.ignore_patterns("signals", ".env"))
    (target / "signals").mkdir()
    _write_private(target / ".env", (target / ".env.example").read_text(encoding="utf-8"))

    print(f"Created tenant '{name}' in {target}\n")
    print("Next:")
    print(f"  1. Edit {target / 'STRATEGY.md'} — the client's goals, offer, constraints.")
    print(f"  2. Edit {target / '.env'} — OPERATOR_NAME, TARGET_CPA, and ad-platform "
          "credentials (leave placeholders for offline use).")
    print(f"  3. Run: foundry account audit --client {name}")
    print("\nThe .env holds secrets: keep it out of git (it is in the Foundry .gitignore; "
          "add `.env` to yours if this workspace is a repo).")
    return 0


def cmd_doctor(opts: dict) -> int:  # pylint: disable=unused-argument
    problems = 0
    print(f"Foundry doctor\n  engine:    {ENGINE_ROOT}\n  workspace: {WORKSPACE}\n")

    ok = sys.version_info >= (3, 10)
    problems += not ok
    print(f"[{'ok' if ok else 'FAIL'}] Python {sys.version.split()[0]} (need >= 3.10)")

    for module, pip_name, purpose in DEPENDENCIES:
        try:
            found = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            found = False
        optional = "optional" in purpose
        print(f"[{'ok' if found else ('warn' if optional else 'FAIL')}] {pip_name} — {purpose}"
              + ("" if found else f"   -> pip install {pip_name}"))
        problems += (not found) and not optional

    tenants = sorted(p.name for p in CLIENTS_ROOT.iterdir() if p.is_dir()) if CLIENTS_ROOT.is_dir() else []
    if tenants:
        print(f"[ok] {len(tenants)} tenant(s): {', '.join(tenants)}")
    else:
        print("[warn] no tenants yet -> foundry setup init --client <Name>")

    print("\nAll good." if not problems else f"\n{problems} problem(s) — fix the FAIL lines above.")
    return 1 if problems else 0
