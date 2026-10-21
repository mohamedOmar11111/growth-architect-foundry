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
import contextlib
import io
import json
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

# Command modules are imported lazily by _resolve_module, so a minimal Python (no
# PyYAML / requests / google-ads) can still run every read-only command.

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
        "leadgen":   {"module": "calc_commands", "tenant": False, "func": "cmd_leadgen"},
        "learning":  {"module": "calc_commands", "tenant": False, "func": "cmd_learning"},
        "vat":       {"module": "calc_commands", "tenant": False, "func": "cmd_vat"},
    },
    "campaigns": {
        "list":    {"module": "campaigns", "tenant": True},
        "status":  {"module": "campaigns", "tenant": True},
        "compare": {"module": "campaigns", "tenant": True},
        "import":  {"module": "campaigns", "tenant": True},
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
    "forecast": {
        "project": {"module": "forecast", "tenant": True},
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
             "orders", "aov", "ship_out", "cpa", "events", "budget", "country", "basis",
             "deal_value", "qualify_rate", "close_rate", "leads")

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
    parser.add_argument("--format", dest="report_format", default=None,
                        help="Report format (markdown|whatsapp).")
    parser.add_argument("--file", dest="file", default=None,
                        help="CSV file path for `campaigns import`.")
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
                 "budget", "country", "basis", "deal-value", "qualify-rate",
                 "close-rate", "leads"):
        parser.add_argument(f"--{flag}", dest=flag.replace("-", "_"), default=None,
                            help=f"Economics input ({flag}).")
    return parser


# ── machine contract ───────────────────────────────────────────────────────
# Exit codes: 0 ok · 1 failure · 2 bad input/usage · 3 refused by a safety gate.
# With --json every command prints ONE JSON object (see _envelope). schema_version
# bumps only on breaking changes to these keys.
SCHEMA_VERSION = 1
EXIT_OK, EXIT_FAILURE, EXIT_USAGE, EXIT_REFUSED = 0, 1, 2, 3


def _envelope(command: str, code: int, out: str, err: str, data: object) -> dict:
    """Stable result shape for agents. `data` is structured when the command has it
    (audit, diagnose, live pull, economics); `output` is the human-readable text."""
    try:
        parsed = json.loads(out)
    except ValueError:
        parsed = None
    report_path = None
    for line in reversed(out.splitlines()):
        if "written -> " in line:
            report_path = line.split("written -> ", 1)[1].strip()
            break
    return {
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "ok": code == EXIT_OK,
        "exit_code": code,
        "data": parsed if parsed is not None else data,
        "output": None if parsed is not None else out,
        "report_path": report_path,
        "stderr": err or None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.as_json:
        return _execute(args, {})

    out, err, extra = io.StringIO(), io.StringIO(), {}
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = _execute(args, extra)
    print(json.dumps(_envelope(f"{args.group} {args.verb}", code, out.getvalue(),
                               err.getvalue(), extra.get("_data")), indent=2, default=str))
    return code


def _execute(args: argparse.Namespace, extra: dict) -> int:
    group = args.group
    verb = args.verb
    group_map = GROUPS.get(group)
    if group_map is None:
        print(f"ERROR: unknown group '{group}'", file=sys.stderr)
        return EXIT_USAGE

    spec = group_map.get(verb)
    if spec is None:
        available = ", ".join(group_map)
        print(f"ERROR: unknown verb '{verb}' for group '{group}'. "
              f"Available: {available}", file=sys.stderr)
        return EXIT_USAGE

    mod = _resolve_module(spec["module"])

    # Determine if this verb needs a tenant
    needs_tenant = spec.get("tenant", True)
    if needs_tenant and not args.client:
        print(f"ERROR: '{group} {verb}' requires --client.", file=sys.stderr)
        return EXIT_USAGE
    if not needs_tenant and args.client and not spec.get("accepts_client"):
        print(f"ERROR: '{group} {verb}' does not accept --client.", file=sys.stderr)
        return EXIT_USAGE

    # Build options dict for the command
    opts = {
        "lang": args.lang,
        "period": args.period,
        "format": args.report_format,
        "file": args.file,
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
    opts["_extra"] = extra  # commands put structured results in extra["_data"]
    if group == "economics" and opts["confirm"] is False:
        opts["confirm"] = None  # unset flag means "use the default rate", not 0%

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
        return EXIT_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())