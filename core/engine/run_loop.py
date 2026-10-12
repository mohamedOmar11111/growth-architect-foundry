"""growth_engine.run_loop — scheduler-agnostic CLI entrypoint for every Growth
Engine loop and command.

Nothing in this file is Windows-specific. Callable today from Windows Task
Scheduler exactly like the old single-account cron script; callable
tomorrow from cron or GCP Cloud Scheduler + Cloud Run with zero changes here —
only the trigger changes, not this script.

Usage:
    python run_loop.py ad-intel --client Acme_Store        (Tenant Bus)
    python run_loop.py lead-qualify                        (Root Bus — no --client)
    python run_loop.py audit --client Aurora_Skincare      (Command)
    python run_loop.py report --client Aurora_Skincare --lang ar --period month

Two buses, per the Dual-Bus ruling:
  - Tenant Bus loops (TENANT_LOOP_MODULES) run against one tenant folder under
    02_Active_Clients/ — `run(tenant: TenantContext) -> int`, --client required.
  - Root Bus loops (ROOT_LOOP_MODULES) run against the operator's shared root
    signals/tasks/log.md — `run() -> int`, no --client, and passing one is an
    error (a root-bus loop reading across every business is the point).

Commands (COMMAND_MODULES) sit alongside Tenant Bus loops: same --client
contract, same containment, but on-demand verbs that READ state and produce a
decision (audit / diagnose / report) instead of scheduled jobs that WRITE it.
A command takes `run(tenant, opts) -> int`, where opts carries only its own
declared flags — each module lists its accepted keys in COMMAND_OPTION_KEYS.

Add a new loop by adding one entry to the relevant dict. Nothing else in this
file needs to change per loop, per tenant, or per bus.
"""

from __future__ import annotations

import argparse
from importlib import import_module

from tenant import TenantConfigError, TenantContext
from commands import COMMAND_MODULES

TENANT_LOOP_MODULES = {
    "ad-intel": "loops.ad_intel",
    "meta-ads": "loops.meta_ads",
    "content-engine": "loops.content_engine",
    "social-calendar": "loops.social_calendar",
    "creative-brief": "loops.creative_brief",
}
ROOT_LOOP_MODULES = {
    "lead-qualify": "loops.lead_qualify",
}
ALL_LOOPS = sorted(set(TENANT_LOOP_MODULES) | set(ROOT_LOOP_MODULES))

# Optional flags a command can consume. Pass-through is opt-in per key so a
# stray flag can never silently change a loop's behavior.
COMMAND_OPTION_KEYS = ("lang", "period", "target_cpa")
ALL_VERBS = ALL_LOOPS + sorted(COMMAND_MODULES)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one Growth Engine loop or command — Tenant Bus or Root Bus."
    )
    parser.add_argument("loop", choices=ALL_VERBS, help="Which loop or command to run.")
    parser.add_argument(
        "--client", default=None,
        help="Tenant folder name under 02_Active_Clients/ — required for "
             "Tenant Bus loops and commands, must be omitted for Root Bus loops.",
    )
    parser.add_argument("--lang", default=None,
                        help="Report language (en|ar) — consumed by the report command.")
    parser.add_argument("--period", default=None,
                        help="Report period (week|month) — consumed by the report command.")
    parser.add_argument("--target-cpa", dest="target_cpa", default=None,
                        help="Target CPA override — consumed by the diagnose command.")
    args = parser.parse_args()

    is_tenant_loop = args.loop in TENANT_LOOP_MODULES
    is_root_loop = args.loop in ROOT_LOOP_MODULES
    is_command = args.loop in COMMAND_MODULES

    if (is_tenant_loop or is_command) and not args.client:
        kind = "command" if is_command else "Tenant Bus loop"
        print(f"ERROR: '{args.loop}' is a {kind} — --client is required.")
        return 1
    if is_root_loop and args.client:
        print(f"ERROR: '{args.loop}' is a Root Bus loop — --client must be omitted "
              "(it reads across every business by design).")
        return 1

    if is_command:
        module = import_module(COMMAND_MODULES[args.loop])
    else:
        module_path = TENANT_LOOP_MODULES.get(args.loop) or ROOT_LOOP_MODULES[args.loop]
        module = import_module(module_path)

    try:
        if is_tenant_loop or is_command:
            try:
                tenant = TenantContext(args.client)
            except TenantConfigError as e:
                print(f"ERROR: {e}")
                return 1
            if is_command:
                opts = {k: getattr(args, k) for k in COMMAND_OPTION_KEYS
                        if getattr(args, k) is not None}
                return module.run(tenant, opts)
            return module.run(tenant)
        return module.run()
    except Exception as e:  # noqa: BLE001 — top-level runner, must not crash silently
        target = f"tenant '{args.client}'" if (is_tenant_loop or is_command) else "root bus"
        print(f"ERROR: {args.loop} failed for {target}: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
