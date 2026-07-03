"""
fees.py — 2026 Amazon fee math, shared by gates / labels / features / scoring.

Approximations from the 2026 US FBA schedule (standard-size, by shipping weight),
including the 3.5% fuel surcharge. Real fees depend on dimensions/size tier too —
always confirm a real SKU in Amazon's Revenue Calculator before buying.
"""
from __future__ import annotations

from typing import Optional

import config


def fulfillment_fee(weight_lb: Optional[float]) -> float:
    w = 1.0 if weight_lb is None else float(weight_lb)
    if w <= 0.75:
        base = 3.22
    elif w <= 1.0:
        base = 4.65
    elif w <= 1.5:
        base = 5.50
    elif w <= 2.0:
        base = 6.10
    elif w <= 2.5:
        base = 6.63
    elif w <= 3.0:
        base = 6.75
    else:
        base = 6.75 + 0.16 * ((w - 3.0) / 0.5)
    return base * (1 + config.FUEL_SURCHARGE)


def net_margin(price: Optional[float], weight_lb: Optional[float],
               cogs_fraction: Optional[float] = None,
               ppc_fraction: Optional[float] = None) -> Optional[float]:
    """Rough NET margin fraction after referral + FBA(+fuel) + assumed COGS + PPC."""
    if not price or price <= 0:
        return None
    cogs_fraction = config.COGS_FRACTION if cogs_fraction is None else cogs_fraction
    ppc_fraction = config.PPC_FRACTION if ppc_fraction is None else ppc_fraction
    referral = price * config.REFERRAL_RATE
    fba = fulfillment_fee(weight_lb)
    cogs = price * cogs_fraction
    ppc = price * ppc_fraction
    return (price - referral - fba - cogs - ppc) / price


def contribution_margin_dollars(price: Optional[float], weight_lb: Optional[float],
                                cogs_fraction: Optional[float] = None) -> Optional[float]:
    """Per-unit contribution margin in $ after Amazon's take + assumed COGS (pre-ads)."""
    if not price or price <= 0:
        return None
    cogs_fraction = config.COGS_FRACTION if cogs_fraction is None else cogs_fraction
    referral = price * config.REFERRAL_RATE
    fba = fulfillment_fee(weight_lb)
    cogs = price * cogs_fraction
    return price - referral - fba - cogs
