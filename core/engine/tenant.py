"""growth_engine.tenant — Multi-tenant context loader for Growth Engine loops.

Core rule: loop code (growth_engine/loops/*.py) must contain ZERO references to
a specific tenant. All tenant-specific values — credentials, STRATEGY.md
directives, brand voice, signals/tasks paths — flow through the TenantContext
object built here. See projects/growth-engine/PLANNING.md for the full
architecture rationale (Engine vs Tenant separation, dual signal bus).

Fails loud by design: a missing .env or STRATEGY.md stops the run. There is no
fallback to root/shared credentials — that fallback is exactly what the
multi-tenant mandate forbids.
"""

from __future__ import annotations

import os
from pathlib import Path

from envfile import dotenv_values

from paths import CLIENTS_ROOT  # noqa: E402

REQUIRED_FILES = (".env", "STRATEGY.md")


class TenantConfigError(RuntimeError):
    """Raised when a tenant folder is missing required config."""


class TenantContext:
    """Everything a loop needs to run for exactly one tenant, and nothing else."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.root = self._resolve_root(name)
        self._validate()
        self.env: dict[str, str] = self._load_env()
        self.strategy_md: str = self._inside_root(self.root / "STRATEGY.md").read_text(encoding="utf-8")
        self.claude_md: str = self._read_optional("CLAUDE.md")
        self.signals_dir = self._ensure_dir("signals")
        self.tasks_dir = self._ensure_dir("tasks")
        self.reports_dir = self._ensure_dir("04_Reports")

    @staticmethod
    def _resolve_root(name: str) -> Path:
        """Security-critical: `name` is untrusted (comes straight from --client
        on the CLI, or an LLM-influenced value via agent_shim.py). pathlib's
        `/` operator silently DISCARDS the left side when the right side is an
        absolute path — `CLIENTS_ROOT / "C:\\Windows"` returns `C:\\Windows`,
        not an error. A bare '..' has the same problem one level up. Reject
        both before they ever reach a real path join, then re-check the
        resolved result actually landed inside CLIENTS_ROOT as defense in
        depth (e.g. against a future refactor of this function)."""
        if not name or "/" in name or "\\" in name or name in (".", ".."):
            raise TenantConfigError(
                f"Invalid tenant name '{name}' — must be a plain folder name "
                f"directly under {CLIENTS_ROOT}, no path separators or '..'."
            )
        raw = CLIENTS_ROOT / name
        candidate = raw.resolve()
        clients_root_resolved = CLIENTS_ROOT.resolve()
        if clients_root_resolved not in candidate.parents:
            raise TenantConfigError(
                f"Tenant '{name}' resolves outside {CLIENTS_ROOT} — refusing."
            )
        # Exact, case-sensitive match on the real directory entry. Windows and
        # macOS are case-insensitive and Windows strips trailing dots/spaces,
        # so 'good', 'Good.' and 'Good ' would all alias the tenant 'Good'.
        # A symlinked tenant dir could alias another tenant entirely.
        # Path.resolve() canonicalises case on Windows but NOT on macOS, so compare
        # against the real directory listing: an exact, case-sensitive string match.
        exact = CLIENTS_ROOT.is_dir() and name in os.listdir(CLIENTS_ROOT)
        if (CLIENTS_ROOT.is_dir() and not exact) or candidate.name != name or raw.is_symlink():
            raise TenantConfigError(
                f"Tenant '{name}' must match the folder name exactly "
                "(case-sensitive, no symlinks) — refusing."
            )
        return candidate

    def _inside_root(self, path: Path) -> Path:
        """Refuse symlinks / anything resolving outside this tenant's folder, so a
        planted STRATEGY.md -> ~/.ssh/id_rsa can't be read into prompts or reports."""
        if path.is_symlink() or (path.exists() and self.root not in path.resolve().parents):
            raise TenantConfigError(
                f"Tenant '{self.name}': '{path.name}' is a symlink or resolves outside "
                "the tenant folder — refusing."
            )
        return path

    def _validate(self) -> None:
        if not self.root.is_dir():
            raise TenantConfigError(
                f"No tenant folder at {self.root}. Valid tenants are subfolders "
                f"of {CLIENTS_ROOT} — check spelling/casing exactly."
            )
        missing = [f for f in REQUIRED_FILES if not (self.root / f).exists()]
        if missing:
            raise TenantConfigError(
                f"Tenant '{self.name}' is missing required file(s): {missing}. "
                "Growth Engine will not run a loop against an incomplete tenant "
                "— no silent fallback to shared/root credentials."
            )

    def _load_env(self) -> dict[str, str]:
        values = dotenv_values(self._inside_root(self.root / ".env"))
        clean = {k: v for k, v in values.items() if v}
        if not clean:
            raise TenantConfigError(
                f"Tenant '{self.name}'s .env exists but is empty or unreadable."
            )
        return clean

    def _read_optional(self, filename: str) -> str:
        path = self._inside_root(self.root / filename)
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def _ensure_dir(self, subpath: str) -> Path:
        path = self._inside_root(self.root / subpath)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def require(self, *keys: str) -> tuple[str, ...]:
        """Fetch required env keys for a loop; fails loud listing exactly what's
        missing instead of raising a bare KeyError deep inside API client init."""
        missing = [k for k in keys if k not in self.env]
        if missing:
            raise TenantConfigError(
                f"Tenant '{self.name}' .env is missing required key(s) for this "
                f"loop: {missing}"
            )
        return tuple(self.env[k] for k in keys)

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.env.get(key, default)
