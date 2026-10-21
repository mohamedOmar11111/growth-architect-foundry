"""growth_engine.calc — deterministic media math, zero dependencies.

Why this exists: an LLM doing break-even arithmetic is a coin flip dressed
as a number. Every money-critical figure this kernel quotes comes from here,
in code, and can be re-run by the operator (or a buyer) to verify it.

Usage:
    python calc.py breakeven --price 499 --cogs 150 --shipping 45 --fees 3 \
        --confirm 0.85 --deliver 0.78 --return-cost 30
    python calc.py cod --spend 20000 --orders 400 --aov 499 --confirm 0.85 \
        --deliver 0.78 --cogs 150 --ship-out 45 --fees 3 --return-cost 30
    python calc.py learning --cpa 120
    python calc.py vat --budget 10000 --country SA
    # + --json on any subcommand for machine-readable output

COD model assumptions (stated, not hidden — recalibrate after ~90 days of
this account's own history):
  - Rates multiply: delivered rate = confirm x deliver.
  - COGS + fees + outbound shipping are paid per DELIVERED order.
  - A confirmed-but-undelivered order costs outbound shipping + return cost
    (stock comes back; the shipping does not).
  - Break-even CPA is quoted per PLACED order, which is what ad platforms
    bill against.

Honest limits: VAT rates change — verify before relying on them. Nothing
here is tax advice, and every projection is an estimate with its assumptions
printed alongside it.
"""

from __future__ import annotations

import argparse
import json
import sys

# Last verified against official sources: 2026-10. Rates change — verify.
VAT_RATES = {
    "SA": 0.15, "AE": 0.05, "KW": 0.05, "BH": 0.10, "OM": 0.05,
    "QA": 0.00, "EG": 0.14, "JO": 0.16, "MA": 0.20, "IQ": 0.00,
}

# How many optimization events per week a platform needs to exit learning —
# a heuristic shared across the industry, not a guarantee. Override with --events.
LEARNING_EVENTS_PER_WEEK = 50


class CalcError(ValueError):
    """Raised on inputs that make the math meaningless (zero denominators,
    rates outside 0-1). Surfaced as a clean message, not a traceback."""


def _unit_economics(price: float, cogs: float, shipping: float, fees: float,
                    confirm: float, deliver: float, return_cost: float) -> dict:
    if not 0 < confirm <= 1 or not 0 < deliver <= 1:
        raise CalcError("confirm and deliver must be in (0, 1] — they are rates.")
    delivered_rate = confirm * deliver
    per_placed = {
        "delivered_revenue": delivered_rate * price,
        "delivered_cost": delivered_rate * (cogs + fees + shipping),
        "failed_cost": (confirm - delivered_rate) * (shipping + return_cost),
    }
    revenue = per_placed["delivered_revenue"]
    non_ad_cost = per_placed["delivered_cost"] + per_placed["failed_cost"]
    contribution = revenue - non_ad_cost
    if contribution <= 0:
        raise CalcError(
            f"Contribution per placed order is {contribution:.2f} — the unit "
            "economics lose money before any ad spend. No break-even exists."
        )
    return {
        "delivered_rate": delivered_rate,
        "revenue_per_placed": revenue,
        "non_ad_cost_per_placed": non_ad_cost,
        "contribution_per_placed": contribution,
        "break_even_cpa": contribution,
        "break_even_roas": revenue / contribution,
    }


def cmd_breakeven(args: argparse.Namespace) -> dict:
    unit = _unit_economics(args.price, args.cogs, args.shipping, args.fees,
                           args.confirm, args.deliver, args.return_cost)
    return {
        "command": "breakeven",
        "inputs": vars(args),
        "delivered_rate": unit["delivered_rate"],
        "revenue_per_placed_order": unit["revenue_per_placed"],
        "non_ad_cost_per_placed_order": unit["non_ad_cost_per_placed"],
        "contribution_per_placed_order": unit["contribution_per_placed"],
        "break_even_cpa_per_placed_order": unit["break_even_cpa"],
        "break_even_roas": unit["break_even_roas"],
        "working_target_cpa": unit["break_even_cpa"] / 1.2,
    }


def cmd_cod(args: argparse.Namespace) -> dict:
    unit = _unit_economics(args.aov, args.cogs, args.ship_out, args.fees,
                           args.confirm, args.deliver, args.return_cost)
    if args.spend < 0 or args.orders <= 0:
        raise CalcError("spend must be >= 0 and orders must be > 0.")

    delivered_orders = args.orders * unit["delivered_rate"]
    revenue = delivered_orders * args.aov
    non_ad_cost = args.orders * unit["non_ad_cost_per_placed"]
    profit = revenue - args.spend - non_ad_cost
    real_cpa = args.spend / args.orders
    return {
        "command": "cod",
        "inputs": vars(args),
        "delivered_orders": delivered_orders,
        "delivered_revenue": revenue,
        "real_roas": revenue / args.spend if args.spend else None,
        "real_cpa_per_placed_order": real_cpa,
        "break_even_cpa_per_placed_order": unit["break_even_cpa"],
        "gross_profit_after_ads": profit,
        "verdict": (
            "profitable" if profit > 0 else
            "break-even" if profit == 0 else
            "losing money — cut spend before scaling anything"
        ),
    }


def cmd_learning(args: argparse.Namespace) -> dict:
    if args.cpa <= 0 or args.events <= 0:
        raise CalcError("cpa and events must both be > 0.")
    weekly = args.events * args.cpa
    return {
        "command": "learning",
        "inputs": vars(args),
        "events_per_week_needed": args.events,
        "weekly_budget": weekly,
        "daily_budget": weekly / 7,
    }


def cmd_vat(args: argparse.Namespace) -> dict:
    country = args.country.upper()
    if country not in VAT_RATES:
        raise CalcError(
            f"No VAT rate known for '{country}'. Known: {', '.join(sorted(VAT_RATES))}."
        )
    rate = VAT_RATES[country]
    if args.budget < 0:
        raise CalcError("budget must be >= 0.")
    if args.basis == "inclusive":
        net = args.budget / (1 + rate)
        vat = args.budget - net
    else:
        net = args.budget
        vat = args.budget * rate
    return {
        "command": "vat",
        "inputs": vars(args),
        "country": country,
        "rate": rate,
        "net": net,
        "vat": vat,
        "gross": net + vat,
    }


def cmd_leadgen(args: argparse.Namespace) -> dict:
    if not 0 < args.qualify_rate <= 1 or not 0 < args.close_rate <= 1:
        raise CalcError("qualify-rate and close-rate must be in (0, 1].")
    if args.deal_value <= 0:
        raise CalcError("deal-value must be > 0.")
    contribution = args.deal_value - args.cogs
    if contribution <= 0:
        raise CalcError(
            f"Contribution per closed deal is {contribution:.2f} — the unit "
            "economics lose money before any ad spend. No break-even exists."
        )
    lead_to_close_rate = args.qualify_rate * args.close_rate
    break_even_cpl = contribution * lead_to_close_rate
    break_even_cpql = contribution * args.close_rate
    out: dict = {
        "command": "leadgen",
        "inputs": vars(args),
        "lead_to_close_rate": lead_to_close_rate,
        "contribution_per_deal": contribution,
        "break_even_cpl": break_even_cpl,
        "break_even_cpql": break_even_cpql,
        "working_target_cpl": break_even_cpl / 1.2,
    }
    if args.spend is not None and args.leads is not None:
        if args.spend < 0 or args.leads <= 0:
            raise CalcError("spend must be >= 0 and leads must be > 0.")
        closed_deals = args.leads * lead_to_close_rate
        revenue = closed_deals * args.deal_value
        non_ad_cost = closed_deals * args.cogs
        profit = revenue - args.spend - non_ad_cost
        real_cpl = args.spend / args.leads
        out.update({
            "closed_deals": closed_deals,
            "revenue": revenue,
            "real_roas": revenue / args.spend if args.spend else None,
            "real_cpl": real_cpl,
            "gross_profit_after_ads": profit,
            "verdict": (
                "profitable" if profit > 0 else
                "break-even" if profit == 0 else
                "losing money — cut spend or improve lead qualification/closing"
            ),
        })
    return out


def _fmt(value: float) -> str:
    return f"{value:,.2f}"


def render_text(payload: dict) -> str:
    cmd = payload["command"]
    lines = [f"# calc {cmd}", ""]
    if cmd == "breakeven":
        lines += [
            f"Delivered rate (confirm x deliver): {payload['delivered_rate'] * 100:.1f}%",
            f"Revenue per placed order:           {_fmt(payload['revenue_per_placed_order'])}",
            f"Non-ad cost per placed order:       {_fmt(payload['non_ad_cost_per_placed_order'])}",
            f"Contribution per placed order:      {_fmt(payload['contribution_per_placed_order'])}",
            "",
            f"BREAK-EVEN CPA (per placed order):  {_fmt(payload['break_even_cpa_per_placed_order'])}",
            f"BREAK-EVEN ROAS:                    {payload['break_even_roas']:.4f}",
            f"Working target CPA (break-even/1.2): {_fmt(payload['working_target_cpa'])}",
            "",
            "Assumptions: COGS+fees+shipping paid per delivered order; failed "
            "deliveries cost shipping + return cost; CPA billed per placed order.",
        ]
    elif cmd == "cod":
        lines += [
            f"Delivered orders:      {payload['delivered_orders']:,.2f}",
            f"Delivered revenue:     {_fmt(payload['delivered_revenue'])}",
            f"Real ROAS (delivered): "
            f"{payload['real_roas']:.4f}" if payload["real_roas"] is not None
            else "Real ROAS (delivered): n/a (zero spend)",
            f"Real CPA (per placed): {_fmt(payload['real_cpa_per_placed_order'])}",
            f"Break-even CPA:        {_fmt(payload['break_even_cpa_per_placed_order'])}",
            f"Gross profit after ads: {_fmt(payload['gross_profit_after_ads'])}",
            "",
            f"VERDICT: {payload['verdict']}",
        ]
    elif cmd == "learning":
        lines += [
            f"Events needed per week: {payload['events_per_week_needed']}",
            f"Weekly budget:          {_fmt(payload['weekly_budget'])}",
            f"Daily budget:           {_fmt(payload['daily_budget'])}",
            "",
            f"Assumption: {payload['events_per_week_needed']} optimization events "
            "per week is a heuristic for exiting learning, not a guarantee — "
            "override with --events.",
        ]
    elif cmd == "vat":
        lines += [
            f"Country:   {payload['country']} (rate {payload['rate'] * 100:.0f}%)",
            f"Net:       {_fmt(payload['net'])}",
            f"VAT:       {_fmt(payload['vat'])}",
            f"Gross:     {_fmt(payload['gross'])}",
            "",
            f"Basis: budget treated as VAT-{payload['inputs']['basis']}. "
            "Rates last verified 2026-10 — verify before relying on them. "
            "Not tax advice.",
        ]
    elif cmd == "leadgen":
        lines += [
            f"Lead-to-close rate (qualify x close): {payload['lead_to_close_rate'] * 100:.1f}%",
            f"Contribution per closed deal:         {_fmt(payload['contribution_per_deal'])}",
            f"BREAK-EVEN CPL (per raw lead):        {_fmt(payload['break_even_cpl'])}",
            f"BREAK-EVEN CPQL (per qualified lead): {_fmt(payload['break_even_cpql'])}",
            f"Working target CPL (break-even/1.2):  {_fmt(payload['working_target_cpl'])}",
        ]
        if "real_cpl" in payload:
            lines += [
                "",
                f"Closed deals:           {payload['closed_deals']:,.2f}",
                f"Revenue:                {_fmt(payload['revenue'])}",
                f"Real CPL:               {_fmt(payload['real_cpl'])}",
                f"Gross profit after ads: {_fmt(payload['gross_profit_after_ads'])}",
                f"VERDICT: {payload['verdict']}",
            ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="calc.py",
        description="Deterministic media math — break-even, COD, learning budget, VAT.",
    )
    # --json belongs to every subcommand, not the root — so it can be passed
    # AFTER the subcommand's own args (`calc.py breakeven --price 1 --json`),
    # which is the order every other flag uses.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="Machine-readable output.")
    sub = parser.add_subparsers(dest="command", required=True)

    be = sub.add_parser("breakeven", parents=[common],
                        help="Break-even CPA and ROAS for a product.")
    be.add_argument("--price", type=float, required=True, help="Selling price (revenue per delivered order).")
    be.add_argument("--cogs", type=float, required=True, help="Cost of goods per delivered order.")
    be.add_argument("--shipping", type=float, default=0.0, help="Outbound shipping per delivered order.")
    be.add_argument("--fees", type=float, default=0.0, help="Payment/platform fees per delivered order.")
    be.add_argument("--confirm", type=float, default=1.0, help="COD confirmation rate (0-1].")
    be.add_argument("--deliver", type=float, default=1.0, help="Delivery rate on confirmed orders (0-1].")
    be.add_argument("--return-cost", type=float, default=0.0, dest="return_cost",
                    help="Return/failure cost per undelivered confirmed order.")
    be.set_defaults(func=cmd_breakeven)

    cod = sub.add_parser("cod", parents=[common], help="Real ROAS and profit on a COD account.")
    cod.add_argument("--spend", type=float, required=True, help="Ad spend for the period.")
    cod.add_argument("--orders", type=float, required=True, help="Placed orders for the period.")
    cod.add_argument("--aov", type=float, required=True, help="Average order value (price).")
    cod.add_argument("--confirm", type=float, default=1.0, help="COD confirmation rate (0-1].")
    cod.add_argument("--deliver", type=float, default=1.0, help="Delivery rate on confirmed orders (0-1].")
    cod.add_argument("--cogs", type=float, required=True, help="Cost of goods per delivered order.")
    cod.add_argument("--ship-out", type=float, default=0.0, dest="ship_out",
                     help="Outbound shipping per delivered order.")
    cod.add_argument("--fees", type=float, default=0.0, help="Payment/platform fees per delivered order.")
    cod.add_argument("--return-cost", type=float, default=0.0, dest="return_cost",
                     help="Return/failure cost per undelivered confirmed order.")
    cod.set_defaults(func=cmd_cod)

    learn = sub.add_parser("learning", parents=[common],
                           help="Budget needed to exit the learning phase.")
    learn.add_argument("--cpa", type=float, required=True, help="Expected or target CPA.")
    learn.add_argument("--events", type=int, default=LEARNING_EVENTS_PER_WEEK,
                       help="Optimization events per week (default 50).")
    learn.set_defaults(func=cmd_learning)

    vat = sub.add_parser("vat", parents=[common], help="Split a budget into net + VAT by country.")
    vat.add_argument("--budget", type=float, required=True, help="Budget amount.")
    vat.add_argument("--country", required=True, help=f"ISO code, one of: {', '.join(sorted(VAT_RATES))}.")
    vat.add_argument("--basis", choices=("inclusive", "exclusive"), default="inclusive",
                     help="Whether --budget already includes VAT (default: inclusive).")
    vat.set_defaults(func=cmd_vat)

    lg = sub.add_parser("leadgen", parents=[common],
                        help="Break-even CPL and funnel profit for lead-gen / WhatsApp funnels.")
    lg.add_argument("--deal-value", type=float, required=True, dest="deal_value",
                    help="Average revenue per closed deal.")
    lg.add_argument("--cogs", type=float, default=0.0,
                    help="Direct delivery/fulfillment cost per closed deal.")
    lg.add_argument("--qualify-rate", type=float, default=1.0, dest="qualify_rate",
                    help="Fraction of raw leads that qualify (0-1].")
    lg.add_argument("--close-rate", type=float, required=True, dest="close_rate",
                    help="Fraction of qualified leads that close (0-1].")
    lg.add_argument("--spend", type=float, default=None, help="Optional ad spend for period.")
    lg.add_argument("--leads", type=float, default=None, help="Optional raw leads generated.")
    lg.set_defaults(func=cmd_leadgen)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = args.func(args)
    except CalcError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(render_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
