"""growth_engine.commands.calc_commands — thin adapter between foundry.py's
CLI dispatch and calc.py's standalone functions.

The math lives in calc.py (zero-deps, runnable standalone). This module
converts the foundry opts dict into the argparse.Namespace calc.py expects
and routes to the right function.
"""

from __future__ import annotations

import json
import sys

from calc import render_text


def _parse_numbers(opts: dict, *keys: str) -> dict:
    """Pull numeric values out of opts, converting strings as needed."""
    out = {}
    for key in keys:
        raw = opts.get(key)
        if raw is not None:
            try:
                out[key] = float(raw)
            except (TypeError, ValueError):
                raise ValueError(f"--{key.replace('_', '-')} must be a number, got '{raw}'")
    return out


def _run_variant(opts: dict, func, required: list[str], optional: dict[str, object] = None) -> int:
    """Generic runner: build an argparse.Namespace from opts, call calc func."""
    from argparse import Namespace

    # Merge required + optional with defaults
    ns_args = {}
    for key in required:
        val = opts.get(key)
        if val is None:
            # Try CLI-style key (e.g., target_cpa → target-cpa)
            cli_key = key.replace("_", "-")
            val = opts.get(cli_key)
        if val is None:
            print(f"ERROR: --{key.replace('_', '-')} is required for this command.", file=sys.stderr)
            return 2
        try:
            ns_args[key] = float(val) if key not in ("country", "basis", "platform") else str(val)
        except (TypeError, ValueError):
            print(f"ERROR: --{key.replace('_', '-')} must be a number, got '{val}'.", file=sys.stderr)
            return 2

    if optional:
        for key, default in optional.items():
            val = opts.get(key)
            ns_args[key] = float(val) if val is not None and isinstance(default, (int, float)) else (val or default)

    # Ensure func is present on namespace
    ns_args["func"] = func
    ns_args["as_json"] = opts.get("as_json", False)
    ns = Namespace(**{k: v for k, v in ns_args.items() if k != "func"})

    try:
        payload = func(ns)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if opts.get("as_json"):
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(render_text(payload))
    return 0


def cmd_breakeven(opts: dict) -> int:
    return _run_variant(opts, cmd_breakeven_impl, ["price", "cogs"],
                        {"shipping": 0.0, "fees": 0.0, "confirm": 1.0,
                         "deliver": 1.0, "return_cost": 0.0})


def cmd_breakeven_impl(ns):
    from calc import _unit_economics
    unit = _unit_economics(ns.price, ns.cogs, ns.shipping, ns.fees,
                           ns.confirm, ns.deliver, ns.return_cost)
    return {
        "command": "breakeven", "inputs": vars(ns),
        "delivered_rate": unit["delivered_rate"],
        "revenue_per_placed_order": unit["revenue_per_placed"],
        "non_ad_cost_per_placed_order": unit["non_ad_cost_per_placed"],
        "contribution_per_placed_order": unit["contribution_per_placed"],
        "break_even_cpa_per_placed_order": unit["break_even_cpa"],
        "break_even_roas": unit["break_even_roas"],
        "working_target_cpa": unit["break_even_cpa"] / 1.2,
    }


def cmd_cod(opts: dict) -> int:
    return _run_variant(opts, cmd_cod_impl, ["spend", "orders", "aov", "cogs"],
                        {"confirm": 1.0, "deliver": 1.0, "ship_out": 0.0,
                         "fees": 0.0, "return_cost": 0.0})


def cmd_cod_impl(ns):
    from calc import _unit_economics
    unit = _unit_economics(ns.aov, ns.cogs, ns.ship_out, ns.fees,
                           ns.confirm, ns.deliver, ns.return_cost)
    if ns.spend < 0 or ns.orders <= 0:
        raise ValueError("spend must be >= 0 and orders must be > 0.")
    delivered = ns.orders * unit["delivered_rate"]
    revenue = delivered * ns.aov
    non_ad = ns.orders * unit["non_ad_cost_per_placed"]
    profit = revenue - ns.spend - non_ad
    return {
        "command": "cod", "inputs": vars(ns),
        "delivered_orders": delivered,
        "delivered_revenue": revenue,
        "real_roas": revenue / ns.spend if ns.spend else None,
        "real_cpa_per_placed_order": ns.spend / ns.orders,
        "break_even_cpa_per_placed_order": unit["break_even_cpa"],
        "gross_profit_after_ads": profit,
        "verdict": ("profitable" if profit > 0 else "break-even" if profit == 0
                    else "losing money — cut spend before scaling anything"),
    }


def cmd_learning(opts: dict) -> int:
    return _run_variant(opts, cmd_learning_impl, ["cpa"],
                        {"events": 50})


def cmd_learning_impl(ns):
    import calc
    return calc.cmd_learning(ns)


def cmd_vat(opts: dict) -> int:
    return _run_variant(opts, cmd_vat_impl, ["budget", "country"],
                        {"basis": "inclusive"})


def cmd_vat_impl(ns):
    import calc
    return calc.cmd_vat(ns)


def cmd_leadgen(opts: dict) -> int:
    return _run_variant(opts, cmd_leadgen_impl, ["deal_value", "close_rate"],
                        {"cogs": 0.0, "qualify_rate": 1.0, "spend": None, "leads": None})


def cmd_leadgen_impl(ns):
    import calc
    if ns.spend is not None:
        ns.spend = float(ns.spend)
    if ns.leads is not None:
        ns.leads = float(ns.leads)
    return calc.cmd_leadgen(ns)