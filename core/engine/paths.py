"""growth_engine.paths — the ONE place that decides where things live.

Two roots, never conflated:
  ENGINE_ROOT — where the Foundry code ships (plugin cache, read-only; replaced
                on every plugin update). Holds the vault, domain contracts.
  WORKSPACE   — the user's own folder: tenants, signals, tasks, log.md, drafts.
                $FOUNDRY_WORKSPACE if set, else the current directory. Never
                inside ENGINE_ROOT when running as a plugin, so updates can't
                wipe client data.
"""

from __future__ import annotations

import os
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = Path(os.environ.get("FOUNDRY_WORKSPACE") or Path.cwd()).resolve()
CLIENTS_ROOT = WORKSPACE / "02_Active_Clients"
LOG_PATH = WORKSPACE / "log.md"
SIGNALS_DIR = WORKSPACE / "signals"
TASKS_DIR = WORKSPACE / "tasks"
DOMAIN_WORKSPACE = WORKSPACE / "domain"       # drafts / STATE written here
DOMAIN_CONTRACTS = ENGINE_ROOT / "domain"     # shipped README contracts
