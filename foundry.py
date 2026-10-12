"""foundry.py — the single entry point for the Growth Architect Foundry.

Usage:
    python foundry.py <group> <verb> [--client <tenant>] [options]

Groups and verbs:

  Account:
    foundry audit --client <t>              0-100 health score + grade + fixes
    foundry diagnose --client <t>           single biggest constraint
    foundry report --client <t> --lang ar   decision-first client readout

  Economics:
    foundry calc breakeven --price 499 ...  break-even CPA / ROAS
    foundry calc cod --spend 20000 ...      real ROAS on COD account
    foundry calc learning --cpa 120         budget to exit learning
    foundry calc vat --budget 10000 ...     VAT split by country

  Campaigns:
    foundry campaigns list --client <t>     all campaigns with status
    foundry campaigns status --client <t>   live vs paused vs zero-spend
    foundry campaigns compare --client <t>  side-by-side performance

  Content:
    foundry content pipeline --client <t>   briefs + calendar overview
    foundry content calendar --client <t>   upcoming publish schedule

  Tracking:
    foundry tracking check --client <t>     credential readiness
    foundry tracking events --client <t>    optimization event audit

  Leads:
    foundry leads score --client <t>        lead task scoring breakdown

  Creative:
    foundry creative hooks --client <t>     angle + hook ideas from signals
    foundry creative angles --client <t>    winning angle matrix

  Competitive:
    foundry competitive audit --client <t>  competitive positioning

  Seasonal:
    foundry season plan --client <t>        season-aware content plan

  Ops:
    foundry ops status --client <t>         engine health + cadence
    foundry ops cadence --client <t>        loop schedule compliance

  Multi-tenant:
    foundry tenants list                    list all configured tenants

  Setup:
    foundry setup init --client <Name>      scaffold a tenant in your workspace
    foundry setup doctor                    check Python, deps, workspace

Workspace: the folder you run from (or $FOUNDRY_WORKSPACE) holds 02_Active_Clients/,
log.md, signals/ and tasks/. The Foundry code itself is never written to.

Every verb is deterministic Python over this tenant's kernel state. No LLM
calls — judgment work belongs to the AI interface layer (skills and agents);
numbers belong to code. Reports write to 04_Reports/ and log.md.
"""

from __future__ import annotations

import argparse
import sys
from importlib import import_module
from pathlib import Path

# Ensure the engine directory is on sys.path so `from commands import ...`
# and `from tenant import ...` resolve without installation.
ENGINE_DIR = Path(__file__).resolve().parent / "core" / "engine"
sys.path.insert(0, str(ENGINE_DIR))

from tenant import TenantConfigError, TenantContext  # noqa: E402
from commands import COMMAND_MODULES  # noqa: E402

# ── calc: standalone, no tenant ────────────────────────────────────────────
from commands import calc_commands  # noqa: E402

# ── additional command modules ─────────────────────────────────────────────
from commands import (  # noqa: E402
    campaigns, content, tracking, ops, tenants, creative,
    leads, competitive, season, forecast, setup,
)

# ── Group → verb → module mapping ──────────────────────────────────────────
# Each module exposes: run(tenant, opts) -> int   (tenant commands)
#                      or: run(opts) -> int        (root commands like tenants list)
# Every module has a DESCRIPTION for --help.

GROUPS: dict[str, dict[str, dict]] = {
    "account": {
        "audit":    {"module": COMMAND_MODULES["audit"],    "tenant": True},
        "diagnose": {"module": COMMAND_MODULES["diagnose"], "tenant": True},
        "report":   {"module": COMMAND_MODULES["report"],   "tenant": True},
    },
    "economics": {
        "breakeven": {"module": "calc_commands", "tenant": False, "func": "cmd_breakeven"},
        "cod":       {"module": "calc_commands", "tenant": False, "func": "cmd_cod"},
        "learning":  {"module": "calc_commands", "tenant": False, "func": "cmd_learning"},
        "vat":       {"module": "calc_commands", "tenant": False, "func": "cmd_vat"},
    },
    "campaigns": {
        "list":    {"module": "campaigns", "tenant": True},
        "status":  {"module": "campaigns", "tenant": True},
        "compare": {"module": "campaigns", "tenant": True},
    },
    "live": {
        "pull":    {"module": "live", "tenant": True},
        "optimize": {"module": "live", "tenant": True},
        "pause":   {"module": "live", "tenant": True},
        "budget":  {"module": "live", "tenant": True},
    },
    "content": {
        "pipeline": {"module": "content", "tenant": True},
        "calendar": {"module": "content", "tenant": True},
    },
    "tracking": {
        "check":  {"module": "tracking", "tenant": True},
        "events": {"module": "tracking", "tenant": True},
    },
    "leads": {
        "score": {"module": "leads", "tenant": True},
    },
    "creative": {
        "hooks":  {"module": "creative", "tenant": True},
        "angles": {"module": "creative", "tenant": True},
    },
    "competitive": {
        "audit": {"module": "competitive", "tenant": True},
    },
    "season": {
        "plan": {"module": "season", "tenant": True},
    },
    "ops": {
        "status":  {"module": "ops", "tenant": True},
        "cadence": {"module": "ops", "tenant": True},
    },
    "tenants": {
        "list": {"module": "tenants", "tenant": False},
    },
    "setup": {
        "init":   {"module": "setup", "tenant": False, "func": "cmd_init", "accepts_client": True},
        "doctor": {"module": "setup", "tenant": False, "func": "cmd_doctor"},
    },
}

ECON_KEYS = ("price", "cogs", "shipping", "fees", "deliver", "return_cost", "spend",
             "orders", "aov", "ship_out", "cpa", "events", "budget", "country", "basis")

# Flat command count for --version display
TOTAL_COMMANDS = sum(len(verbs) for verbs in GROUPS.values())


def _resolve_module(module_name: str):
    """Import a command module by name.

    COMMAND_MODULES values already include the 'commands.' prefix
    (e.g. 'commands.audit'), so import them directly. calc_commands
    is imported at the top of this file."""
    if module_name == "calc_commands":
        return calc_commands
    # Short names like 'campaigns' need the prefix; full names like
    # 'commands.audit' from COMMAND_MODULES are imported as-is.
    if module_name.startswith("commands."):
        return import_module(module_name)
    return import_module(f"commands.{module_name}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="foundry",
        description=(
            f"Growth Architect Foundry — {TOTAL_COMMANDS} deterministic commands. "
            "Groups: " + ", ".join(GROUPS)
        ),
    )
    parser.add_argument("group", choices=GROUPS,
                        help="Command group.")
    parser.add_argument("verb", help="Verb within the group.")
    parser.add_argument("--client", default=None,
                        help="Tenant folder name under 02_Active_Clients/.")
    parser.add_argument("--lang", default=None, help="Report language (en|ar).")
    parser.add_argument("--period", default=None, help="Report period (week|month).")
    parser.add_argument("--target-cpa", dest="target_cpa", default=None,
                        help="Target CPA override.")
    parser.add_argument("--json", dest="as_json", action="store_true",
                        help="Machine-readable JSON output.")
    parser.add_argument("--campaign-id", dest="campaign_id", default=None,
                        help="Campaign ID for live operations (e.g., 'google:12345').")
    parser.add_argument("--new-budget", dest="new_budget", default=None,
                        help="New daily budget for budget changes.")
    parser.add_argument("--confirm", nargs="?", const=True, default=False,
                        help="Live writes: bare flag required (pause, budget). "
                             "Economics: confirmation rate, e.g. --confirm 0.85.")
    for flag in ("price", "cogs", "shipping", "fees", "deliver", "return-cost",
                 "spend", "orders", "aov", "ship-out", "cpa", "events",
                 "budget", "country", "basis"):
        parser.add_argument(f"--{flag}", dest=flag.replace("-", "_"), default=None,
                            help=f"Economics input ({flag}).")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    group = args.group
    verb = args.verb
    group_map = GROUPS.get(group)
    if group_map is None:
        print(f"ERROR: unknown group '{group}'", file=sys.stderr)
        return 1

    spec = group_map.get(verb)
    if spec is None:
        available = ", ".join(group_map)
        print(f"ERROR: unknown verb '{verb}' for group '{group}'. "
              f"Available: {available}", file=sys.stderr)
        return 1

    mod = _resolve_module(spec["module"])

    # Determine if this verb needs a tenant
    needs_tenant = spec.get("tenant", True)
    if needs_tenant and not args.client:
        print(f"ERROR: '{group} {verb}' requires --client.", file=sys.stderr)
        return 1
    if not needs_tenant and args.client and not spec.get("accepts_client"):
        print(f"ERROR: '{group} {verb}' does not accept --client.", file=sys.stderr)
        return 1

    # Build options dict for the command
    opts = {
        "lang": args.lang,
        "period": args.period,
        "target_cpa": args.target_cpa,
        "campaign_id": args.campaign_id,
        "new_budget": args.new_budget,
        "confirm": args.confirm,
        "as_json": args.as_json,
        "verb": verb,
        "client": args.client,
    }
    for key in ECON_KEYS:
        opts[key] = getattr(args, key)

    try:
        if needs_tenant:
            try:
                tenant = TenantContext(args.client)
            except TenantConfigError as e:
                print(f"ERROR: {e}", file=sys.stderr)
                return 1
            return mod.run(tenant, opts)
        else:
            # Root commands (calc, tenants list)
            func_name = spec.get("func")
            if func_name:
                return getattr(mod, func_name)(opts)
            return mod.run(opts)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {group} {verb} failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())