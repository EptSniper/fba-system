"""
scoring.py — transparent, rule-based product scoring (0-100).

No machine learning here. This is the explainable baseline the whole system can
run on with ZERO labeled data. Every point is traceable to a research criterion,
and `score_product` also returns a human-readable reason string.

The criteria thresholds come from config.CRITERIA; the fee assumptions for the
margin estimate come from config (2026 values). All of it is tunable in .env.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import re

import config
import brands

# How many points each criterion can contribute. They sum to 100.
WEIGHTS = {
    "price": 18,        # in the $15-$50 sweet spot
    "sales": 18,        # >= ~200 units/mo
    "reviews": 16,      # beatable review moat
    "rating": 12,       # weak incumbents (<= 4.3 stars)
    "weight": 12,       # small & light (<= 1 lb)
    "offers": 8,        # not a crowded Buy Box
    "margin": 16,       # healthy estimated net margin
}


# ----------------------------------------------------------------------------
# FBA fulfillment fee estimate (2026 schedule, US, standard-size).
# Approximation by shipping weight only. Verify EVERY SKU in Amazon's Revenue
# Calculator — real fees also depend on dimensions/size tier, not just weight.
# ----------------------------------------------------------------------------
def estimate_fulfillment_fee(weight_lb: Optional[float]) -> float:
    if weight_lb is None:
        weight_lb = 1.0  # neutral assumption when weight is unknown
    w = float(weight_lb)
    if w <= 0.75:
        return 3.22      # small/large standard, up to 12 oz
    if w <= 1.0:
        return 4.65      # large standard, 12-16 oz
    if w <= 1.5:
        return 5.50
    if w <= 2.0:
        return 6.10
    if w <= 2.5:
        return 6.63      # most common tier (2026)
    if w <= 3.0:
        return 6.75
    # +$0.16 per half-pound above 3 lb (standard), capped roughly
    extra_half_lbs = (w - 3.0) / 0.5
    return 6.75 + 0.16 * extra_half_lbs


def estimate_margin(price: Optional[float], weight_lb: Optional[float]) -> Optional[float]:
    """
    Rough NET margin after Amazon's take + assumed COGS + assumed PPC.

        net = price - referral - fulfillment*(1+fuel) - cogs - ppc
        margin = net / price

    COGS and PPC are ASSUMPTIONS from config (defaults 30% and 10% of price).
    Returns a fraction (e.g. 0.28 == 28%) or None if price is unknown.
    """
    if not price or price <= 0:
        return None
    referral = price * config.REFERRAL_RATE
    fulfillment = estimate_fulfillment_fee(weight_lb) * (1 + config.FUEL_SURCHARGE)
    cogs = price * config.COGS_FRACTION
    ppc = price * config.PPC_FRACTION
    net = price - referral - fulfillment - cogs - ppc
    return net / price


def _band_score(value, lo, hi, full_points) -> float:
    """Full points inside [lo, hi]; linear-ish partial credit just outside."""
    if value is None:
        return full_points * 0.25  # unknown -> small benefit of the doubt
    if lo <= value <= hi:
        return float(full_points)
    # graceful decay outside the band
    span = (hi - lo) or 1
    if value < lo:
        miss = (lo - value) / span
    else:
        miss = (value - hi) / span
    return max(0.0, full_points * (1 - min(miss, 1)))


def _le_score(value, threshold, full_points, soft=0.5) -> float:
    """Full points if value <= threshold; partial as it overshoots."""
    if value is None:
        return full_points * 0.25
    if value <= threshold:
        return float(full_points)
    over = (value - threshold) / (threshold or 1)
    return max(0.0, full_points * (1 - min(over * soft, 1)))


def _ge_score(value, threshold, full_points) -> float:
    """Full points if value >= threshold; partial credit below it."""
    if value is None:
        return full_points * 0.25
    if value >= threshold:
        return float(full_points)
    return max(0.0, full_points * (value / threshold))


def score_product(p: Dict[str, Any],
                  criteria: Optional[Dict[str, Any]] = None) -> Tuple[float, float, str]:
    """
    Score one enriched product dict.

    Expects keys: price, est_sales, reviews, rating, weight_lb, offers.
    Returns (score_0_100, margin_estimate_fraction_or_None, reason_string).
    """
    c = criteria or config.CRITERIA
    price = p.get("price")
    sales = p.get("est_sales")
    reviews = p.get("reviews")
    rating = p.get("rating")
    weight = p.get("weight_lb")
    offers = p.get("offers")
    margin = estimate_margin(price, weight)

    parts = {
        "price": _band_score(price, c["price_min"], c["price_max"], WEIGHTS["price"]),
        "sales": _ge_score(sales, c["min_monthly_sales"], WEIGHTS["sales"]),
        "reviews": _le_score(reviews, c["max_reviews"], WEIGHTS["reviews"]),
        "rating": _le_score(rating, c["max_rating"], WEIGHTS["rating"], soft=2.0),
        "weight": _le_score(weight, c["max_weight_lb"], WEIGHTS["weight"]),
        "offers": _le_score(offers, c["max_offers"], WEIGHTS["offers"]),
        "margin": _ge_score(margin, config.TARGET_NET_MARGIN, WEIGHTS["margin"])
        if margin is not None else WEIGHTS["margin"] * 0.25,
    }
    score = round(sum(parts.values()), 1)

    # ---- human-readable reasoning ----
    def ok(cond): return "✓" if cond else "✗"
    bits = []
    bits.append(f"${_fmt(price)} {ok(price is not None and c['price_min'] <= price <= c['price_max'])} band")
    bits.append(f"~{_fmt(sales,0)} sales/mo {ok(sales is not None and sales >= c['min_monthly_sales'])}")
    bits.append(f"{_fmt(reviews,0)} reviews {ok(reviews is not None and reviews <= c['max_reviews'])}")
    bits.append(f"{_fmt(rating)}★ {ok(rating is not None and rating <= c['max_rating'])}")
    bits.append(f"{_fmt(weight)}lb {ok(weight is not None and weight <= c['max_weight_lb'])}")
    bits.append(f"{_fmt(offers,0)} offers {ok(offers is not None and offers <= c['max_offers'])}")
    if margin is not None:
        bits.append(f"~{margin*100:.0f}% est. net margin {ok(margin >= config.TARGET_NET_MARGIN)}")
    else:
        bits.append("margin n/a")
    reason = " · ".join(bits) + f"  →  {score}/100"
    return score, margin, reason


def _fmt(v, decimals: int = 2) -> str:
    if v is None:
        return "?"
    try:
        return f"{float(v):.{decimals}f}"
    except (TypeError, ValueError):
        return str(v)


def risk_flags(p: Dict[str, Any],
               criteria: Optional[Dict[str, Any]] = None) -> list:
    """
    Transparent, rule-derived risk tags for a candidate (mirrors the blueprint's
    risk taxonomy as far as the available Keepa fields allow). These are heuristic
    warnings, not guarantees — always confirm on the Keepa chart.
    """
    c = criteria or config.CRITERIA
    flags = []
    price, sales = p.get("price"), p.get("est_sales")
    reviews, rating = p.get("reviews"), p.get("rating")
    weight, offers = p.get("weight_lb"), p.get("offers")
    oos, margin = p.get("oos_90"), p.get("margin_est")

    if offers is not None and offers > c["max_offers"]:
        flags.append("Offer crowding → price-war risk")
    if reviews is not None and reviews > c["max_reviews"]:
        flags.append("Entrenched review moat")
    if rating is not None and rating >= 4.6:
        flags.append("Strong incumbent ratings (hard to beat)")
    if weight is not None and weight > c["max_weight_lb"]:
        flags.append("Heavy → higher FBA/size-tier fees")
    if price is not None and not (c["price_min"] <= price <= c["price_max"]):
        flags.append("Price outside $15–$50 band")
    if sales is not None and sales < c["min_monthly_sales"]:
        flags.append("Thin demand vs target")
    if isinstance(oos, (int, float)) and oos > 30:
        flags.append("Stockout history (out-of-stock often)")
    if margin is not None and margin < config.TARGET_NET_MARGIN:
        flags.append("Estimated margin below target")
    # data-completeness warning
    if any(v is None for v in (price, sales, reviews, rating, weight)):
        flags.append("Incomplete Keepa data — verify manually")
    return flags


# ============================================================================
# Online-Arbitrage scoring (MODE="OA")
# Criteria source: ../learning-hub/playbooks/sourcing-playbook.md + transcript
# insights. OA differs from private label: you JOIN an existing healthy listing
# and compete for the Buy Box, so we score BSR, the seller-count band, ROI, $
# profit, and whether Amazon dominates the Buy Box — NOT review/rating "weak
# incumbent" signals (those are for PL).
# ============================================================================
OA_WEIGHTS = {
    "bsr": 20,        # BSR <= max (sells fast enough)
    "sales": 18,      # >= ~50/mo (Keepa "yellow line")
    "offers": 16,     # inside the [min, max] seller band
    "roi": 22,        # >= 30% after fees
    "profit": 12,     # >= $3/unit
    "buybox": 12,     # Amazon NOT dominating the Buy Box
}


def estimate_oa_profit_roi(price, weight_lb, cogs_fraction=None, category=None):
    """Estimate per-unit $ profit and ROI for an OA buy (no PPC; ROI = profit/buy-cost).
    Buy cost is ASSUMED = price * OA_COGS_FRACTION since Keepa has no real cost. Referral
    fee is CATEGORY-AWARE (config.referral_rate_for) with Amazon's $0.30 floor when a
    category is known/provided; otherwise falls back to the flat config.REFERRAL_RATE.
    Returns (profit_per_unit, roi) or (None, None). Confirm in SellerAmp."""
    if not price or price <= 0:
        return None, None
    cf = config.OA_COGS_FRACTION if cogs_fraction is None else cogs_fraction
    if category:
        referral = max(price * config.referral_rate_for(category), config.MIN_REFERRAL_FEE)
    else:
        referral = price * config.REFERRAL_RATE
    fulfillment = estimate_fulfillment_fee(weight_lb) * (1 + config.FUEL_SURCHARGE)
    cogs = price * cf
    prep = config.OA_PREP_COST  # seller now preps/labels FBA in the US (2026) — real per-unit cost
    profit = price - referral - fulfillment - cogs - prep
    roi = (profit / cogs) if cogs > 0 else None
    return round(profit, 2), (round(roi, 3) if roi is not None else None)


def triage_score(p: Dict[str, Any], category: Optional[str] = None) -> Optional[float]:
    """Review-queue ranking (Scout Agent Build Plan sec 3.2): expected payback SPEED at a
    STRESSED (competed-down) price, not headline ROI — `expected_profit * monthly_velocity /
    buy_cost`, with price knocked down by TRIAGE_STRESSED_PRICE_FACTOR (default 0.90) to
    simulate sellers piling in before you can act. A RANKING SIGNAL ONLY: it orders which
    survivors deserve review time first; it never touches oa_hard_reject, score, or gates.
    Returns None (not 0.0) when there isn't enough data to rank — an unranked candidate must
    never look like "worst candidate" by sorting to the bottom on a fabricated zero."""
    price = p.get("price")
    sales = p.get("est_sales")
    weight = p.get("weight_lb")
    if not price or price <= 0 or sales is None:
        return None
    stressed_price = price * config.TRIAGE_STRESSED_PRICE_FACTOR
    stressed_profit, _ = estimate_oa_profit_roi(stressed_price, weight, category=category)
    if stressed_profit is None:
        return None
    buy_cost = stressed_price * config.OA_COGS_FRACTION
    if buy_cost <= 0:
        return None
    return round(stressed_profit * sales / buy_cost, 3)


def _amazon_has_buybox(p) -> bool:
    seller = p.get("buybox_seller")
    return isinstance(seller, str) and seller == config.AMAZON_SELLER_ID


def _amazon_share(p: Dict[str, Any]) -> Optional[float]:
    """Amazon's Buy-Box win share (0-1) over the period, or None if unknown."""
    s = p.get("amazon_bb_share")
    return s if isinstance(s, (int, float)) and s >= 0 else None


def _amazon_rotates_buybox(p: Dict[str, Any]) -> bool:
    """True if Amazon wins the Buy Box at least OA_AMAZON_SHARE_MAX of the time
    (rotation) even when it isn't the current holder -> it keeps stealing sales."""
    s = _amazon_share(p)
    return bool(s is not None and s >= config.OA_AMAZON_SHARE_MAX)


# Keyword hints that a product may be FBA-restricted (from the FBA product-restrictions policy:
# hazmat / prohibited / expiration-dated / meltable). Heuristic on title+brand only — ALWAYS verify
# real eligibility (SP-API Listings Restrictions + "Look up an ASIN") before buying.
_RESTRICTION_KEYWORDS_FALLBACK = {
    "hazmat/flammable": ("battery", "batteries", "lithium", "spray", "aerosol", "flammable",
                         "paint", "bleach", "cleaner", "disinfect", "sanitizer", "nail polish",
                         "perfume", "cologne", "fragrance", "magnet", "lighter", "butane", "propane"),
    "prohibited": ("tire", "gift card", "alcohol", "beer", "wine", "vodka", "whiskey"),
    "expiration-dated": ("supplement", "vitamin", "protein", "snack", "coffee", "tea", "cereal",
                         "formula", "lotion", "cream", "shampoo", "soap", "sunscreen", "cosmetic",
                         "makeup", "serum", " point-after-opening", "pao"),
    "meltable": ("chocolate", "gummy", "gummies", "jelly", "wax", "candle", "lip balm", "crayon"),
}
# SINGLE SOURCE OF TRUTH: ai-brain.json's guards.restrictionKeywords (read by config.py) is
# preferred so the scout and the control-center Find page use the IDENTICAL list; falls back
# to the hardcoded copy above if the brain is absent or doesn't define this block.
_RESTRICTION_KEYWORDS = config.RESTRICTION_KEYWORDS or _RESTRICTION_KEYWORDS_FALLBACK


def _fba_restriction_hint(p: Dict[str, Any]) -> Optional[str]:
    """Heuristic: does the title/brand hint at an FBA-restricted category? Returns the label(s) or None.
    Word-boundary matching so 'jelly' doesn't match 'Jellycat' and 'tire' doesn't match 'entire'."""
    text = ((p.get("title") or "") + " " + (p.get("brand") or "")).lower()

    def _has(w: str) -> bool:
        return re.search(r"\b" + re.escape(w) + r"\b", text) is not None

    hits = [label for label, words in _RESTRICTION_KEYWORDS.items() if any(_has(w) for w in words)]
    return ", ".join(hits) if hits else None


def _price_spike(p: Dict[str, Any]) -> bool:
    """True if the current price is far above its 90-day average (likely to revert)."""
    price, avg = p.get("price"), p.get("avg_price_90")
    return bool(price and avg and avg > 0 and price > avg * config.OA_PRICE_SPIKE_RATIO)


def _price_caution(p: Dict[str, Any]) -> bool:
    """Scout Agent Build Plan sec 4.1: a SOFTER, earlier-warning band — price above its 90-day
    average by at least OA_PRICE_CAUTION_RATIO (default 1.15x) but not yet at the harder
    OA_PRICE_SPIKE_RATIO (1.5x). A smaller point penalty than the spike flag, never a gate, and
    mutually exclusive with _price_spike (checked via elif in _score_oa_impl) so a genuine spike
    is never double-penalized as a caution too."""
    price, avg = p.get("price"), p.get("avg_price_90")
    if not (price and avg and avg > 0):
        return False
    ratio = price / avg
    return config.OA_PRICE_CAUTION_RATIO <= ratio < config.OA_PRICE_SPIKE_RATIO


def _offers_rising(p: Dict[str, Any]) -> bool:
    """True if the new-offer count is far above its 90-day average (seller spike -> price tank)."""
    cur, avg = p.get("offers"), p.get("avg_offers_90")
    return bool(cur and avg and avg > 0 and cur > avg * config.OA_OFFERS_RISE_RATIO)


def _ip_cliff(p: Dict[str, Any]) -> bool:
    """Approximate the IP-complaint 'cliff' (fba-keepa-analyst instant-reject fingerprint):
    a healthy listing whose offer count has COLLAPSED — e.g. 56 sellers -> 1 — and not recovered.
    Per oa-criteria that usually means the brand filed IP complaints; it's WORSE than a price
    drop because it dents account health. Heuristic from the fields we have (current offers far
    below a once-crowded 90-day average); always confirm on Keepa's all-time offer-count chart."""
    cur, avg = p.get("offers"), p.get("avg_offers_90")
    return bool(cur is not None and avg and avg >= 8 and cur <= 2)


def _no_featured_offer(p: Dict[str, Any]) -> bool:
    """No Buy Box / no featured offer -> buyers must open 'see all buying options', so the ASIN
    sells far slower. Uses an explicit `has_buybox` signal when Keepa provides it; otherwise infers
    it only when there are real offers but no Buy-Box seller/price at all (conservative)."""
    if p.get("has_buybox") is False:
        return True
    offers = p.get("offers")
    has_seller = bool(p.get("buybox_seller"))
    bb_price = p.get("buybox_price")
    return bool(offers and offers >= 3 and not has_seller and not bb_price)


def _worst_case_loss(p: Dict[str, Any]) -> Optional[float]:
    """field-sops worst-case rule: only buy if, at the 90-day LOW Buy-Box price, you break even or
    lose <= ~$1-2/unit. Returns the estimated per-unit LOSS ($, positive) at that historical low,
    0.0 if safe, or None when the historical low isn't available. Activates once keepa_client
    populates `price_low_90`."""
    low = p.get("price_low_90")
    if not low or low <= 0:
        return None
    profit, _ = estimate_oa_profit_roi(low, p.get("weight_lb"))
    if profit is None:
        return None
    return round(max(0.0, -profit), 2)


def _score_oa_impl(p: Dict[str, Any], criteria: Optional[Dict[str, Any]] = None,
                   category: Optional[str] = None) -> Dict[str, Any]:
    """Shared core for score_product_oa() and explain_oa() — computed ONCE so the two
    public views (compact reason string vs structured explanation) can never drift apart.
    category: explicit override, else read from p['category']. Grocery gets the ROI
    exception (ai-brain.json criteria.exceptions.groceryMinRoi) applied to the ROI gate only.
    """
    c = dict(criteria or config.CRITERIA_OA)
    category = category or p.get("category")
    is_grocery = isinstance(category, str) and category.strip().lower() == "grocery"
    min_roi = config.OA_GROCERY_MIN_ROI if is_grocery else c["min_roi"]

    price = p.get("price")
    bsr = p.get("sales_rank")
    sales = p.get("est_sales")
    offers = p.get("offers")
    weight = p.get("weight_lb")
    profit = p.get("oa_profit")
    roi = p.get("oa_roi")
    if profit is None or roi is None:
        profit, roi = estimate_oa_profit_roi(price, weight, category=category)

    # Gate on the 90-day AVERAGE BSR when Keepa provides one (Scout Agent Build Plan sec 3.1:
    # veterans gate on avg90, not current — current BSR is stockout/spike-prone). Falls back to
    # the current value when avg90 isn't available (older keepa_client versions, missing data).
    avg_bsr_90 = p.get("avg_sales_rank_90")
    bsr_for_gate = avg_bsr_90 if avg_bsr_90 is not None else bsr
    bsr_source = "avg90" if avg_bsr_90 is not None else ("current" if bsr is not None else "none")

    bsr_pts = (_le_score(bsr_for_gate, c["bsr_max"], OA_WEIGHTS["bsr"], soft=1.0)
               if bsr_for_gate is not None else OA_WEIGHTS["bsr"] * 0.25)
    sales_pts = _ge_score(sales, c["min_monthly_sales"], OA_WEIGHTS["sales"])
    # offer band: penalize below min (PL/wholesale) AND above max (crowded)
    if offers is None:
        offers_pts = OA_WEIGHTS["offers"] * 0.25
    elif offers < c["min_offers"]:
        offers_pts = OA_WEIGHTS["offers"] * 0.3
    elif offers <= c["max_offers"]:
        offers_pts = OA_WEIGHTS["offers"]
    else:
        offers_pts = _le_score(offers, c["max_offers"], OA_WEIGHTS["offers"])
    roi_pts = (_ge_score(roi, min_roi, OA_WEIGHTS["roi"])
               if roi is not None else OA_WEIGHTS["roi"] * 0.25)
    profit_pts = (_ge_score(profit, c["min_profit_per_unit"], OA_WEIGHTS["profit"])
                  if profit is not None else OA_WEIGHTS["profit"] * 0.25)
    buybox_pts = 0.0 if _amazon_has_buybox(p) else OA_WEIGHTS["buybox"]

    score = round(bsr_pts + sales_pts + offers_pts + roi_pts + profit_pts + buybox_pts, 1)
    brand_tag = ""
    adjustments: list = []

    def _adj(name: str, points: float, reason: str):
        adjustments.append({"name": name, "points": points, "reason": reason})

    if brands.is_friendly(p.get("brand")):
        score = min(100.0, round(score + 5, 1))   # small nudge toward known-good brands
        brand_tag = " · ★known-good brand"
        _adj("friendly-brand", 5, "Known-good OA brand (ai-brain.json brands.friendly)")
    elif brands.is_avoided(p.get("brand")):
        brand_tag = " · ⚠avoid-brand"
        _adj("avoid-brand", 0, "Brand on the avoid list — informational only, hard gate is separate")
    # Preferred 5-7 offer "goldilocks" band: a BONUS only, never touches the 3-25 hard band.
    po = config.PREFERRED_OFFERS
    if offers is not None and po["min"] <= offers <= po["max"]:
        score = min(100.0, round(score + po["bonus"], 1))
        brand_tag += f" · ★{po['min']}-{po['max']}-offer band"
        _adj("preferred-offer-band", po["bonus"], f"{offers} offers is in the {po['min']}-{po['max']} goldilocks band")
    if _price_spike(p):
        score = max(0.0, round(score - 15, 1))   # learned red flag: price likely to revert
        brand_tag += " · ⚠price-spike"
        _adj("price-spike", -15, "Current price far above its 90-day average — likely to revert")
    elif _price_caution(p):
        score = max(0.0, round(score - 5, 1))    # softer, earlier warning — never a gate
        brand_tag += " · ⚠price-caution"
        _adj("price-caution", -5,
             f"Current price is {config.OA_PRICE_CAUTION_RATIO}-{config.OA_PRICE_SPIKE_RATIO}x "
             "its 90-day average — a softer early warning, not yet a spike")
    if _offers_rising(p):
        score = max(0.0, round(score - 12, 1))   # learned red flag: seller spike -> price tank
        brand_tag += " · ⚠offers-rising"
        _adj("offers-rising", -12, "Offer count far above its 90-day average — seller spike, price likely to tank")
    _share = _amazon_share(p)
    if _share and _share > 0 and not _amazon_has_buybox(p):
        score = max(0.0, round(score - 10, 1))   # Buy-Box rotation: Amazon steals a cut of sales
        brand_tag += f" · ⚠amazon-shares-BB({_share*100:.0f}%)"
        _adj("amazon-shares-buybox", -10, f"Amazon wins the Buy Box ~{_share*100:.0f}% of the time (rotation)")
    if _ip_cliff(p):
        score = max(0.0, round(score - 20, 1))   # offer-count collapse: likely brand IP complaints
        brand_tag += " · ⚠IP-cliff"
        _adj("ip-cliff", -20, "Offer count collapsed (e.g. 56→1) — likely brand IP complaints")
    _wc = _worst_case_loss(p)
    if _wc is not None and _wc > 2:
        score = max(0.0, round(score - 10, 1))   # loses money at the 90-day low Buy-Box price
        brand_tag += f" · ⚠worst-case -${_wc:.0f}"
        _adj("worst-case-loss", -10, f"Loses ~${_wc:.2f}/unit at the 90-day low Buy-Box price")
    if _no_featured_offer(p):
        score = max(0.0, round(score - 8, 1))    # no Buy Box → much slower sales
        brand_tag += " · ⚠no-BuyBox"
        _adj("no-featured-offer", -8, "No Buy Box / featured offer — buyers must dig, much slower sales")
    _brand = (p.get("brand") or "").strip().lower()
    if _brand in ("", "generic") or "generic" in _brand:
        score = max(0.0, round(score - 8, 1))    # brand-generic listing (Masterclass: avoid)
        brand_tag += " · ⚠generic-brand"
        _adj("generic-brand", -8, "Brand-generic / no real brand — avoid (Masterclass)")

    def ok(cond): return "✓" if cond else "✗"
    gates = [
        {"name": "bsr", "passed": bool(bsr_for_gate is not None and bsr_for_gate <= c["bsr_max"]),
         "actual": bsr_for_gate, "threshold": c["bsr_max"], "source": bsr_source},
        {"name": "sales", "passed": bool(sales is not None and sales >= c["min_monthly_sales"]),
         "actual": sales, "threshold": c["min_monthly_sales"]},
        {"name": "offers", "passed": bool(offers is not None and c["min_offers"] <= offers <= c["max_offers"]),
         "actual": offers, "threshold": [c["min_offers"], c["max_offers"]]},
        {"name": "roi", "passed": bool(roi is not None and roi >= min_roi),
         "actual": roi, "threshold": min_roi},
        {"name": "profit", "passed": bool(profit is not None and profit >= c["min_profit_per_unit"]),
         "actual": profit, "threshold": c["min_profit_per_unit"]},
        {"name": "buybox", "passed": not _amazon_has_buybox(p),
         "actual": _amazon_has_buybox(p), "threshold": False},
    ]
    bits = [
        f"BSR {_fmt(bsr_for_gate,0)}{'~avg90' if bsr_source == 'avg90' else ''} {ok(gates[0]['passed'])}",
        f"~{_fmt(sales,0)}/mo {ok(gates[1]['passed'])}",
        f"{_fmt(offers,0)} offers {ok(gates[2]['passed'])}",
        f"ROI {('%.0f%%' % (roi*100)) if roi is not None else '?'} {ok(gates[3]['passed'])}"
        + (f" (grocery {min_roi*100:.0f}% bar)" if is_grocery else ""),
        f"${_fmt(profit)}/u {ok(gates[4]['passed'])}",
        f"BuyBox {'Amazon✗' if _amazon_has_buybox(p) else '3P✓'}",
    ]
    reason = " · ".join(bits) + brand_tag + f"  →  {score}/100  (est.; confirm in SellerAmp)"
    return {"score": score, "profit": profit, "roi": roi, "gates": gates,
            "adjustments": adjustments, "reason": reason, "min_roi_applied": min_roi,
            "category": category}


def score_product_oa(p: Dict[str, Any], criteria: Optional[Dict[str, Any]] = None,
                     category: Optional[str] = None):
    """OA rule score (0-100) + (profit, roi) + reason. Reads p: price, sales_rank,
    est_sales, offers, weight_lb, buybox_seller (uses oa_profit/oa_roi if present).
    category: optional (or read from p['category']) — drives the referral-rate lookup
    and, for 'grocery', the lower ROI-gate exception. Unchanged return signature."""
    r = _score_oa_impl(p, criteria, category)
    return r["score"], (r["profit"], r["roi"]), r["reason"]


def explain_oa(p: Dict[str, Any], criteria: Optional[Dict[str, Any]] = None,
              category: Optional[str] = None) -> Dict[str, Any]:
    """Structured explain-why verdict for one candidate: { verdict, score, gates, adjustments }.
    verdict mirrors the pipeline's vocabulary ("pass" on a hard reject, else "review"/"pass" by
    score threshold) — it does NOT authorize a buy; it's the same transparent gate/score logic
    as score_product_oa, just returned as data instead of a formatted string."""
    r = _score_oa_impl(p, criteria, category)
    hard_reject = oa_hard_reject(p)
    if hard_reject:
        verdict = "pass"
    else:
        verdict = "review" if r["score"] >= config.SCORE_THRESHOLD else "pass"
    return {
        "verdict": verdict,
        "score": r["score"],
        "profit": r["profit"],
        "roi": r["roi"],
        "gates": r["gates"],
        "adjustments": r["adjustments"],
        "hard_reject": hard_reject,
        "category": r["category"],
        "min_roi_applied": r["min_roi_applied"],
    }


def risk_flags_oa(p: Dict[str, Any], criteria: Optional[Dict[str, Any]] = None) -> list:
    """OA red flags, mirroring the playbook's instant-reject signals."""
    c = criteria or config.CRITERIA_OA
    flags = []
    bsr, sales, offers = p.get("sales_rank"), p.get("est_sales"), p.get("offers")
    roi, profit, oos = p.get("oa_roi"), p.get("oa_profit"), p.get("oos_90")
    if _amazon_has_buybox(p):
        flags.append("Amazon holds the Buy Box → can't compete (reject)")
    _share = _amazon_share(p)
    if _share and _share > 0 and not _amazon_has_buybox(p):
        flags.append(f"Amazon rotates onto the Buy Box ~{_share*100:.0f}% of the time → it skims your sales")
    _restrict = _fba_restriction_hint(p)
    if _restrict:
        flags.append(f"May be FBA-restricted ({_restrict}) — verify eligibility/hazmat/expiration/meltable + prep before buying")
    if offers is not None and offers < c["min_offers"]:
        flags.append("Few sellers → may be private-label/wholesale, not OA")
    if offers is not None and offers > c["max_offers"]:
        flags.append("Crowded Buy Box → price-war risk")
    if bsr is not None and bsr > c["bsr_max"]:
        flags.append("High BSR → sells slowly")
    if sales is not None and sales < c["min_monthly_sales"]:
        flags.append("Under ~50 sales/mo (no Keepa yellow line)")
    if roi is not None and roi < c["min_roi"]:
        flags.append("Estimated ROI below 30%")
    if profit is not None and profit < c["min_profit_per_unit"]:
        flags.append("Under $3 estimated profit/unit")
    if isinstance(oos, (int, float)) and oos > 30:
        flags.append("Frequent stockouts")
    if _price_spike(p):
        flags.append("Price spike — current price >> 90-day avg; likely to revert")
    if _offers_rising(p):
        flags.append("Offers rising vs 90-day avg — seller spike, price likely to tank")
    if _ip_cliff(p):
        flags.append("Offer-count cliff (e.g. 56→1) → likely brand IP complaints; account-health risk")
    _wc = _worst_case_loss(p)
    if _wc is not None and _wc > 2:
        flags.append(f"Worst case: ~${_wc:.2f}/unit loss at the 90-day low Buy-Box price")
    if _no_featured_offer(p):
        flags.append("No Buy Box / featured offer → buyers must dig; much slower sales")
    brand = (p.get("brand") or "").strip().lower()
    if brand in ("", "generic") or "generic" in brand:
        flags.append("Brand-generic / no real brand → avoid (Masterclass)")
    # Not available from Keepa stats here — must be checked by hand:
    flags.append("Verify on Keepa: offer-count TREND (rising = avoid), Buy-Box rotation, gating/IP")
    if any(p.get(k) is None for k in ("price", "sales_rank", "est_sales", "offers")):
        flags.append("Incomplete Keepa data — verify manually")
    return flags


def oa_hard_reject(p: Dict[str, Any]) -> Optional[str]:
    """Hard gate — reasons to NEVER post an OA pick regardless of score.
    Mirrors the playbook's instant-reject rules we can actually detect from Keepa.
    Returns a reason string, or None if the candidate passes the gate."""
    if _amazon_has_buybox(p):
        return "Amazon holds the Buy Box → can't compete"
    if _amazon_rotates_buybox(p):
        share = _amazon_share(p) or 0
        return f"Amazon wins the Buy Box ~{share*100:.0f}% of the time → can't compete"
    if brands.is_avoided(p.get("brand")):
        return "Brand hard-gated / IP-risky for beginners"
    if _ip_cliff(p):
        return "Offer count collapsed (IP-complaint cliff) → account-health risk"
    price = p.get("price")
    if not price or price <= 0:
        return "No price data"
    return None
