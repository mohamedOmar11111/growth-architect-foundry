"""growth_engine.utils — shared helpers for every loop.

Kept separate from tenant.py (context loading) and from individual loops
(business logic) so each stays focused. Client-agnostic — nothing here reads a
tenant name except as a passed-in argument.
"""

from __future__ import annotations

import datetime
import subprocess
from pathlib import Path

from paths import WORKSPACE, LOG_PATH


def append_log(tenant_name: str, loop_name: str, summary: str, report_path: Path) -> None:
    """Appends one entry to the root log.md — the operator's global
    cross-business run log, unchanged from the pre-Growth-Engine convention."""
    now = datetime.datetime.now()
    rel = report_path.relative_to(WORKSPACE).as_posix()
    entry = (
        f"\n## {now.strftime('%Y-%m-%d %H:%M')} — {tenant_name} / {loop_name} (Growth Engine)\n"
        f"- {summary}. Report: `{rel}`\n"
    )
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(entry)


def refresh_graph(tenant_root: Path) -> None:
    """Headless incremental graphify refresh for one tenant's own corpus.
    Non-fatal — a graphify failure never breaks the loop that called it."""
    try:
        extract = subprocess.run(
            ["graphify", "extract", ".", "--backend", "gemini"],
            cwd=str(tenant_root), capture_output=True, text=True, timeout=300,
        )
        if extract.returncode != 0:
            print(f"[graphify] extract non-zero exit: {extract.stderr[-300:]}")
            return
        subprocess.run(
            ["graphify", "cluster-only", ".", "--no-label"],
            cwd=str(tenant_root), capture_output=True, text=True, timeout=180,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        print(f"[graphify] refresh skipped — {e}")
