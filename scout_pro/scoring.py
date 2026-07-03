"""
scoring.py — transparent rule score (0-100) + reason.

This is the explainable baseline the system always has, even with zero labels and
no trained model. The production blended score = mix of this rule score and the
calibrated classifier probability (models.blended_score).
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import brands
import config
import gates

WEIGHTS = {"price": 18, "sales": 18, "reviews": 16, "rating": 12,
           "weight": 12, "offers": 8, "margin": 16}


def _band(v, lo, hi, pts):
    if v is None:
        return pts * 0.25
    if lo <= v <= hi:
        return float(pts)
    span = (hi - lo) or 1
    miss = (lo - v) / span if v < lo else (v - hi) / span
    return max(0.0, pts * (1 - min(miss, 1)))


def _le(v, thr, pts, soft=0.5):
    if v is None:
        return pts * 0.25
    if v <= thr:
        return float(pts)
    return max(0.0, pts * (1 - min((v - thr) / (thr or 1) * soft, 1)))


def _ge(v, thr, pts):
    if v is None:
        return pts * 0.25
    if v >= thr:
        return float(pts)
    return max(0.0, pts * (v / thr))


def rule_score(f: Dict[str, Any], criteria: Optional[Dict[str, Any]] = None) -> Tuple[float, str]:
    """Score a feature row against the research criteria. Returns (score, reason)."""
    c = criteria or config.CRITERIA
    price = f.get("price")
    sales = f.get("est_sales")
    reviews = f.get("review_count")
    rating = f.get("rating")
    weight = f.get("weight_lb")
    offers = f.get("offer_count")
    margin = f.get("margin_est")

    parts = {
        "price": _band(price, c["price_min"], c["price_max"], WEIGHTS["price"]),
        "sales": _ge(sales, c["min_monthly_sales"], WEIGHTS["sales"]),
        "reviews": _le(reviews, c["max_reviews"], WEIGHTS["reviews"]),
        "rating": _le(rating, c["max_rating"], WEIGHTS["rating"], soft=2.0),
        "weight": _le(weight, c["max_weight_lb"], WEIGHTS["weight"]),
        "offers": _le(offers, c["max_offers"], WEIGHTS["offers"]),
        "margin": _ge(margin, config.TARGET_NET_MARGIN, WEIGHTS["margin"]) if margin is not None
        else WEIGHTS["margin"] * 0.25,
    }
    score = round(sum(parts.values()), 1)

    def ok(b):
        return "✓" if b else "✗"
    reason = " · ".join([
        f"${_f(price)} {ok(price is not None and c['price_min'] <= price <= c['price_max'])}",
        f"~{_f(sales,0)} sales/mo {ok(sales is not None and sales >= c['min_monthly_sales'])}",
        f"{_f(reviews,0)} reviews {ok(reviews is not None and reviews <= c['max_reviews'])}",
        f"{_f(rating)}★ {ok(rating is not None and rating <= c['max_rating'])}",
        f"{_f(weight)}lb {ok(weight is not None and weight <= c['max_weight_lb'])}",
        f"{_f(offers,0)} offers {ok(offers is not None and offers <= c['max_offers'])}",
        (f"~{margin*100:.0f}% margin {ok(margin >= config.TARGET_NET_MARGIN)}" if margin is not None else "margin n/a"),
    ]) + f"  →  {score}/100"
    return score, reason


def _f(v, d=2):
    if v is None:
        return "?"
    try:
        return f"{float(v):.{d}f}"
    except (TypeError, ValueError):
        return str(v)


# ============================================================================
# Online-Arbitrage (OA) scoring — additive OA mode alongside rule_score() above.
# Mirrors scout/scoring.py::score_product_oa() exactly, including point values,
# so ai-brain.json stays the single source of truth for the RULES even though
# the two codebases implement them separately. Does not touch rule_score() or
# its callers/tests.
# ============================================================================
OA_WEIGHTS = {
    "bsr": 20,
    "sales": 18,
    "offers": 16,
    "roi": 22,
    "profit": 12,
    "buybox": 12,
}


def estimate_fulfillment_fee(weight_lb: Optional[float]) -> float:
    """FBA fulfillment fee estimate (2026 schedule, US, standard-size). Approximation
    by shipping weight only — verify every SKU in Amazon's Revenue Calculator."""
    if weight_lb is None:
        weight_lb = 1.0
    w = float(weight_lb)
    if w <= 0.75:
        return 3.22
    if w <= 1.0:
        return 4.65
    if w <= 1.5:
        return 5.50
    if w <= 2.0:
        return 6.10
    if w <= 2.5:
        return 6.63
    if w <= 3.0:
        return 6.75
    extra_half_lbs = (w - 3.0) / 0.5
    return 6.75 + 0.16 * extra_half_lbs


def estimate_oa_profit_roi(price, weight_lb, cogs_fraction=None):
    """Estimate per-unit $ profit and ROI for an OA buy (no PPC; ROI = profit/buy-cost).
    Buy cost is ASSUMED = price * OA_COGS_FRACTION since Keepa has no real cost.
    Returns (profit_per_unit, roi) or (None, None). Confirm in SellerAmp."""
    if not price or price <= 0:
        return None, None
    cf = config.OA_COGS_FRACTION if cogs_fraction is None else cogs_fraction
    referral = price * config.REFERRAL_RATE
    fulfillment = estimate_fulfillment_fee(weight_lb) * (1 + config.FUEL_SURCHARGE)
    cogs = price * cf
    prep = config.OA_PREP_COST
    profit = price - referral - fulfillment - cogs - prep
    roi = (profit / cogs) if cogs > 0 else None
    return round(profit, 2), (round(roi, 3) if roi is not None else None)


def _price_spike(p: Dict[str, Any]) -> bool:
    """True if the current price is far above its 90-day average (likely to revert)."""
    price, avg = p.get("price"), p.get("avg_price_90")
    return bool(price and avg and avg > 0 and price > avg * config.OA_PRICE_SPIKE_RATIO)


def _offers_rising(p: Dict[str, Any]) -> bool:
    """True if the new-offer count is far above its 90-day average (seller spike -> price tank)."""
    cur, avg = p.get("offers"), p.get("avg_offers_90")
    return bool(cur and avg and avg > 0 and cur > avg * config.OA_OFFERS_RISE_RATIO)


def _ip_cliff(p: Dict[str, Any]) -> bool:
    """Offer-count collapse fingerprint (e.g. 56 -> 1) → likely brand IP complaints.
    Same logic as gates._ip_cliff; duplicated here (no import of gates needed for
    this check alone) so scoring can flag/penalize it independent of the hard gate."""
    cur, avg = p.get("offers"), p.get("avg_offers_90")
    return bool(cur is not None and avg and avg >= 8 and cur <= 2)


def _no_featured_offer(p: Dict[str, Any]) -> bool:
    """No Buy Box / no featured offer -> buyers must open 'see all buying options', so
    the ASIN sells far slower. Uses an explicit `has_buybox` signal when provided;
    otherwise infers it only when there are real offers but no Buy-Box seller/price
    at all (conservative)."""
    if p.get("has_buybox") is False:
        return True
    offers = p.get("offers")
    has_seller = bool(p.get("buybox_seller"))
    bb_price = p.get("buybox_price")
    return bool(offers and offers >= 3 and not has_seller and not bb_price)


def _worst_case_loss(p: Dict[str, Any]) -> Optional[float]:
    """Only buy if, at the 90-day LOW Buy-Box price, you break even or lose <= ~$1-2/unit.
    Returns the estimated per-unit LOSS ($, positive) at that historical low, 0.0 if
    safe, or None when the historical low isn't available."""
    low = p.get("price_low_90")
    if not low or low <= 0:
        return None
    profit, _ = estimate_oa_profit_roi(low, p.get("weight_lb"))
    if profit is None:
        return None
    return round(max(0.0, -profit), 2)


def oa_rule_score(p: Dict[str, Any], criteria: Optional[Dict[str, Any]] = None):
    """OA rule score (0-100) + (profit, roi) + reason. Reads p: price, sales_rank,
    est_sales, offers, weight_lb, buybox_seller, brand (uses oa_profit/oa_roi if
    present). Mirrors scout/scoring.py::score_product_oa() point-for-point."""
    c = criteria or config.CRITERIA_OA
    price = p.get("price")
    bsr = p.get("sales_rank")
    sales = p.get("est_sales")
    offers = p.get("offers")
    weight = p.get("weight_lb")
    profit = p.get("oa_profit")
    roi = p.get("oa_roi")
    if profit is None or roi is None:
        profit, roi = estimate_oa_profit_roi(price, weight)

    bsr_pts = (_le(bsr, c["bsr_max"], OA_WEIGHTS["bsr"], soft=1.0)
               if bsr is not None else OA_WEIGHTS["bsr"] * 0.25)
    sales_pts = _ge(sales, c["min_monthly_sales"], OA_WEIGHTS["sales"])
    if offers is None:
        offers_pts = OA_WEIGHTS["offers"] * 0.25
    elif offers < c["min_offers"]:
        offers_pts = OA_WEIGHTS["offers"] * 0.3
    elif offers <= c["max_offers"]:
        offers_pts = OA_WEIGHTS["offers"]
    else:
        offers_pts = _le(offers, c["max_offers"], OA_WEIGHTS["offers"])
    roi_pts = (_ge(roi, c["min_roi"], OA_WEIGHTS["roi"])
               if roi is not None else OA_WEIGHTS["roi"] * 0.25)
    profit_pts = (_ge(profit, c["min_profit_per_unit"], OA_WEIGHTS["profit"])
                  if profit is not None else OA_WEIGHTS["profit"] * 0.25)
    buybox_pts = 0.0 if gates._amazon_has_buybox(p) else OA_WEIGHTS["buybox"]

    score = round(bsr_pts + sales_pts + offers_pts + roi_pts + profit_pts + buybox_pts, 1)
    brand_tag = ""
    if brands.is_friendly(p.get("brand")):
        score = min(100.0, round(score + 5, 1))
        brand_tag = " · ★known-good brand"
    elif brands.is_avoided(p.get("brand")):
        brand_tag = " · ⚠avoid-brand"
    if _price_spike(p):
        score = max(0.0, round(score - 15, 1))
        brand_tag += " · ⚠price-spike"
    if _offers_rising(p):
        score = max(0.0, round(score - 12, 1))
        brand_tag += " · ⚠offers-rising"
    _share = gates._amazon_share(p)
    if _share and _share > 0 and not gates._amazon_has_buybox(p):
        score = max(0.0, round(score - 10, 1))
        brand_tag += f" · ⚠amazon-shares-BB({_share*100:.0f}%)"
    if _ip_cliff(p):
        score = max(0.0, round(score - 20, 1))
        brand_tag += " · ⚠IP-cliff"
    _wc = _worst_case_loss(p)
    if _wc is not None and _wc > 2:
        score = max(0.0, round(score - 10, 1))
        brand_tag += f" · ⚠worst-case -${_wc:.0f}"
    if _no_featured_offer(p):
        score = max(0.0, round(score - 8, 1))
        brand_tag += " · ⚠no-BuyBox"
    _brand = (p.get("brand") or "").strip().lower()
    if _brand in ("", "generic") or "generic" in _brand:
        score = max(0.0, round(score - 8, 1))
        brand_tag += " · ⚠generic-brand"

    def ok(cond):
        return "✓" if cond else "✗"
    bits = [
        f"BSR {_f(bsr,0)} {ok(bsr is not None and bsr <= c['bsr_max'])}",
        f"~{_f(sales,0)}/mo {ok(sales is not None and sales >= c['min_monthly_sales'])}",
        f"{_f(offers,0)} offers {ok(offers is not None and c['min_offers'] <= offers <= c['max_offers'])}",
        f"ROI {('%.0f%%' % (roi*100)) if roi is not None else '?'} {ok(roi is not None and roi >= c['min_roi'])}",
        f"${_f(profit)}/u {ok(profit is not None and profit >= c['min_profit_per_unit'])}",
        f"BuyBox {'Amazon✗' if gates._amazon_has_buybox(p) else '3P✓'}",
    ]
    reason = " · ".join(bits) + brand_tag + f"  →  {score}/100  (est.; confirm in SellerAmp)"
    return score, (profit, roi), reason
