#!/usr/bin/env python3
"""Deterministic Amazon FBA online-arbitrage profit math.

Defaults mirror amazon-fba-oa/references/oa-criteria.md (and ai-brain.json):
referral 15%, fuel surcharge 3.5% of the FBA fee, prep $0.50/unit, target ROI 30%.
Everything is an ESTIMATE until SellerAmp / Amazon's Revenue Calculator confirms the
real fees for the actual SKU. This script never recommends a purchase.

Example:
    python fba_calc.py --sell 29.99 --cost 20 --fba-fee 6.60
    python fba_calc.py --sell 24 --cost 9 --referral-pct 15   # FBA fee unknown -> shows both tiers
"""
import argparse


def compute(sell, cost, referral_pct, fba_fee, inbound, prep, fuel_pct):
    referral = max(sell * referral_pct / 100.0, 0.30)  # $0.30 minimum
    fuel = fba_fee * fuel_pct / 100.0
    fees = referral + fba_fee + fuel + prep + inbound
    profit = sell - cost - fees
    roi = (profit / cost * 100.0) if cost else float("nan")
    margin = (profit / sell * 100.0) if sell else float("nan")
    # breakeven sell price: sell such that profit == 0, holding referral as % of sell
    # sell - cost - (sell*r) - fba - fuel - prep - inbound = 0  -> sell(1-r) = cost+fba+fuel+prep+inbound
    r = referral_pct / 100.0
    fixed = cost + fba_fee + fuel + prep + inbound
    breakeven = fixed / (1 - r) if r < 1 else float("nan")
    return {
        "referral": referral, "fuel": fuel, "fba_fee": fba_fee, "prep": prep,
        "inbound": inbound, "fees": fees, "profit": profit, "roi": roi,
        "margin": margin, "breakeven": breakeven,
    }


def max_cost_for_roi(sell, referral_pct, fba_fee, inbound, prep, fuel_pct, target_roi):
    """Largest landed cost C such that (sell - C - fees) / C >= target_roi/100."""
    referral = max(sell * referral_pct / 100.0, 0.30)
    fuel = fba_fee * fuel_pct / 100.0
    non_cost_fees = referral + fba_fee + fuel + prep + inbound
    t = target_roi / 100.0
    # profit = sell - C - non_cost_fees ; profit/C = t -> sell - non_cost_fees = C(1+t)
    return (sell - non_cost_fees) / (1 + t)


def fmt(d, sell, target_roi, max_cost):
    lines = [
        f"  Referral fee:   -${d['referral']:.2f}",
        f"  FBA fee:        -${d['fba_fee']:.2f}",
        f"  Fuel surcharge: -${d['fuel']:.2f}",
        f"  Prep:           -${d['prep']:.2f}",
        f"  Inbound ship:   -${d['inbound']:.2f}",
        f"  Total fees:     -${d['fees']:.2f}",
        f"  ---",
        f"  Profit/unit:     ${d['profit']:.2f}",
        f"  ROI:             {d['roi']:.1f}%",
        f"  Margin:          {d['margin']:.1f}%",
        f"  Breakeven sell:  ${d['breakeven']:.2f}",
        f"  Max cost @ {target_roi:.0f}% ROI: ${max_cost:.2f}  (land below this to clear the bar)",
    ]
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description="FBA OA profit math (estimate only; never a buy instruction).")
    p.add_argument("--sell", type=float, required=True, help="Buy Box / sell price")
    p.add_argument("--cost", type=float, default=None, help="True landed cost incl. shipping")
    p.add_argument("--referral-pct", type=float, default=15.0)
    p.add_argument("--fba-fee", type=float, default=None, help="FBA fulfillment fee; omit to show both tiers")
    p.add_argument("--inbound", type=float, default=0.60, help="Inbound shipping $/unit")
    p.add_argument("--prep", type=float, default=0.50)
    p.add_argument("--fuel-pct", type=float, default=3.5)
    p.add_argument("--target-roi", type=float, default=30.0)
    a = p.parse_args()

    tiers = {a.fba_fee: ""} if a.fba_fee is not None else {3.20: "small-standard", 6.60: "large-standard"}
    print(f"DEAL MATH — sell ${a.sell:.2f}" + (f", landed cost ${a.cost:.2f}" if a.cost is not None else ", cost UNKNOWN"))
    for fee, label in tiers.items():
        if label:
            print(f"\n[{label} FBA fee ${fee:.2f}]")
        mc = max_cost_for_roi(a.sell, a.referral_pct, fee, a.inbound, a.prep, a.fuel_pct, a.target_roi)
        if a.cost is None:
            print(f"  Max cost @ {a.target_roi:.0f}% ROI: ${mc:.2f}  (land below this to clear the bar)")
        else:
            d = compute(a.sell, a.cost, a.referral_pct, fee, a.inbound, a.prep, a.fuel_pct)
            print(fmt(d, a.sell, a.target_roi, mc))
    print("\nEstimate only — confirm the exact FBA fee in SellerAmp / Amazon's Revenue Calculator before buying.")


if __name__ == "__main__":
    main()
