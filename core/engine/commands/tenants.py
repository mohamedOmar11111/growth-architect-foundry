"""growth_engine.commands.tenants — multi-tenant management.

One root verb (no --client required):
  list — every configured tenant with its readiness status

A tenant "exists" when it has both .env and STRATEGY.md in its folder. This
command reads from disk only — no hq.db dependency.
"""

from __future__ import annotations

from pathlib import Path

from tenant import CLIENTS_ROOT
from commands.state import config_status

try:
    from dotenv import dotenv_values
except ImportError:
    dotenv_values = None  # graceful: list still works, just no .env reading


def _scan_tenant(name: str) -> dict:
    root = CLIENTS_ROOT / name
    env_path = root / ".env"
    strategy = root / "STRATEGY.md"
    env = dotenv_values(env_path) if (dotenv_values and env_path.exists()) else {}
    has_content = (root / "02_Content").exists()
    reports = len(list((root / "04_Reports").glob("*.md"))) if (root / "04_Reports").exists() else 0
    signals = len(list((root / "signals").glob("*.md"))) if (root / "signals").exists() else 0
    return {
        "name": name,
        "has_env": env_path.exists(),
        "has_strategy": strategy.exists(),
        "config": config_status(env),
        "has_content": has_content,
        "reports": reports,
        "signals": signals,
    }


def run(opts: dict | None = None) -> int:
    if not CLIENTS_ROOT.exists():
        print(f"No clients folder at {CLIENTS_ROOT}.")
        return 0

    tenants = sorted(p.name for p in CLIENTS_ROOT.iterdir() if p.is_dir())
    if not tenants:
        print("No tenants configured yet. Copy Aurora_Skincare/ and rename it.")
        return 0

    configured_count = sum(1 for t in tenants if (CLIENTS_ROOT / t / ".env").exists())
    lines = [
        f"# Tenants — {configured_count} configured",
        "",
        "| Tenant | .env | Strategy | Integrations ready | Signals | Reports | Content |",
        "|---|---|---|---|---|---|---|",
    ]
    for name in tenants:
        t = _scan_tenant(name)
        integrations = sum(1 for g in t["config"]["groups"].values() if g["ready"])
        total_integrations = len(t["config"]["groups"])
        lines.append(
            f"| {name} | {'✓' if t['has_env'] else '✗'} | "
            f"{'✓' if t['has_strategy'] else '✗'} | "
            f"{integrations}/{total_integrations} | "
            f"{t['signals']} | {t['reports']} | "
            f"{'✓' if t['has_content'] else '✗'} |"
        )

    print("\n".join(lines))
    return 0