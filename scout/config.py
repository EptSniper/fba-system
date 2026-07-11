"""
config.py — central configuration for the Product Scout.

All secrets and tunable thresholds live here, loaded from a `.env` file
(see .env.example). Nothing in this repo hard-codes a key.

Required credentials (set in .env):
    KEEPA_KEY            -> a PAID Keepa subscription key (Premium ~$19+/mo unlocks
                           sales-rank data, Product Finder, and API access).
    DISCORD_WEBHOOK_URL  -> a Discord channel webhook (Server Settings ->
                           Integrations -> Webhooks -> New Webhook -> Copy URL).
                           No bot token is required for webhooks.

Everything else has a sane default and can be overridden in .env.
"""
from __future__ import annotations

import os

try:
    # python-dotenv is optional at import time; if missing we just read os.environ
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # pragma: no cover - dotenv simply not installed
    pass


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return float(default)


def _i(name: str, default: int) -> int:
    try:
        return int(float(os.getenv(name, default)))
    except (TypeError, ValueError):
        return int(default)


# ----------------------------------------------------------------------------
# Credentials
# ----------------------------------------------------------------------------
KEEPA_KEY: str | None = os.getenv("KEEPA_KEY") or None
DISCORD_WEBHOOK_URL: str | None = os.getenv("DISCORD_WEBHOOK_URL") or None

# Keepa marketplace domain. "US" is the Amazon.com marketplace.
KEEPA_DOMAIN: str = os.getenv("KEEPA_DOMAIN", "US")

# ----------------------------------------------------------------------------
# File paths
# ----------------------------------------------------------------------------
DB_PATH: str = os.getenv("DB_PATH", "scout.db")
MODEL_PATH: str = os.getenv("MODEL_PATH", "scout_model.joblib")

# ----------------------------------------------------------------------------
# Product-research criteria (the rule-based filter + scorer reads these).
# These mirror the sourced research baseline; tune them in .env.
# ----------------------------------------------------------------------------
CRITERIA = {
    "price_min": _f("PRICE_MIN", 15.0),          # $ lower bound of sweet spot
    "price_max": _f("PRICE_MAX", 50.0),          # $ upper bound
    "min_monthly_sales": _i("MIN_MONTHLY_SALES", 200),   # ~10-15 sales/day
    "max_reviews": _i("MAX_REVIEWS", 500),       # "beatable" review moat
    "max_rating": _f("MAX_RATING", 4.3),         # weak incumbents = opportunity
    "max_weight_lb": _f("MAX_WEIGHT_LB", 1.0),   # small & light keeps FBA fees low
    "max_offers": _i("MAX_OFFERS", 15),          # crowded Buy Box = price war
}

# Pipeline behaviour
SCORE_THRESHOLD: float = _f("SCORE_THRESHOLD", 70.0)  # only send picks >= this
TOP_N: int = _i("TOP_N", 5)                           # max picks per run
CANDIDATE_LIMIT: int = _i("CANDIDATE_LIMIT", 200)     # Product Finder result cap

# ----------------------------------------------------------------------------
# Margin-estimate assumptions (used by scoring.estimate_margin).
# These are ASSUMPTIONS, not facts about a specific product. Tune to your reality.
# ----------------------------------------------------------------------------
REFERRAL_RATE: float = _f("REFERRAL_RATE", 0.15)      # most categories ~15%
FUEL_SURCHARGE: float = _f("FUEL_SURCHARGE", 0.035)   # 3.5% on fulfillment (2026)
COGS_FRACTION: float = _f("COGS_FRACTION", 0.30)      # assumed landed cost as % of price
PPC_FRACTION: float = _f("PPC_FRACTION", 0.10)        # assumed ad cost as % of price
TARGET_NET_MARGIN: float = _f("TARGET_NET_MARGIN", 0.25)  # 25% net = healthy

# ----------------------------------------------------------------------------
# Sourcing MODE + Online-Arbitrage criteria
# ----------------------------------------------------------------------------
# "OA" = online arbitrage (what we actually do). "PL" = private label (the old
# default). OA criteria are distilled from the transcripts —
# see ../learning-hub/playbooks/sourcing-playbook.md. Switch via SCOUT_MODE in .env.
MODE: str = (os.getenv("SCOUT_MODE", "OA") or "OA").upper()

# Amazon's own seller id (US marketplace). If Amazon holds the Buy Box, an OA
# reseller can't realistically win sales -> we reject/penalize those.
AMAZON_SELLER_ID: str = os.getenv("AMAZON_SELLER_ID", "ATVPDKIKX0DER")

# Assumed OA buy cost as a fraction of the Amazon sell price (Keepa has no real
# cost). A typical OA target buys around half the resale price; ROI = profit /
# buy-cost. This is an ESTIMATE for pre-filtering only — always confirm the true
# cost + ROI in SellerAmp before buying.
OA_COGS_FRACTION: float = _f("OA_COGS_FRACTION", 0.50)

# Per-unit PREP cost (poly bag + label + your labor). Learned from Amazon's SP-API Fulfillment
# Inbound doc: as of Jan 1, 2026 Amazon NO LONGER preps or labels FBA items in the US — the seller
# must, so every OA buy now carries this cost. Subtracted from the profit/ROI estimate. Tune in .env.
OA_PREP_COST: float = _f("OA_PREP_COST", 0.50)

# Inbound shipping: getting the bought unit FROM the source (retail store/online) TO the Amazon
# FBA warehouse. fba-selleramp-analyst's documented cost stack puts this at ~$0.60/lb (range
# $0.50-0.80) — re-check after each real shipment. Was previously omitted from the profit/ROI
# estimate and the backtest's would_have_profited labels entirely (Full-crew audit, 2026-07-11:
# fba-selleramp-analyst finding — live-proven +$0.59-3.00/unit optimistic drift).
OA_INBOUND_SHIP_PER_LB: float = _f("OA_INBOUND_SHIP_PER_LB", 0.60)

CRITERIA_OA = {
    "price_min": _f("OA_PRICE_MIN", 8.0),            # include cheap grocery
    "price_max": _f("OA_PRICE_MAX", 60.0),
    "bsr_max": _i("OA_BSR_MAX", 200000),             # sells fast enough (top ~1%)
    "min_monthly_sales": _i("OA_MIN_SALES", 50),     # Keepa "yellow line" floor
    "min_offers": _i("OA_MIN_OFFERS", 3),            # <3 often = private-label/wholesale
    "max_offers": _i("OA_MAX_OFFERS", 25),           # too crowded = price war
    "max_weight_lb": _f("OA_MAX_WEIGHT_LB", 5.0),
    "min_roi": _f("OA_MIN_ROI", 0.30),               # >=30% after fees (returns buffer)
    "min_profit_per_unit": _f("OA_MIN_PROFIT", 3.0), # >= $3/unit
}

# Price-spike guard (a learned red flag): if the current price is far above its 90-day
# average, it's likely to revert — brutal with FBA's ~2-week check-in delay.
OA_PRICE_SPIKE_RATIO: float = _f("OA_PRICE_SPIKE_RATIO", 1.5)
# Rising-offers guard (the "seller spike" red flag): if the current new-offer count is far
# above its 90-day average, more sellers are piling in -> the price is about to tank.
OA_OFFERS_RISE_RATIO: float = _f("OA_OFFERS_RISE_RATIO", 1.4)
# Amazon Buy-Box SHARE guard (Buy-Box "rotation"): even when Amazon isn't the CURRENT
# Buy-Box holder, if it wins the Buy Box at least this fraction of the time it keeps
# stealing your sales -> hard reject. Below this (but > 0) we penalize + flag instead.
# The videos tell beginners to skip listings Amazon is on at all; 0.20 is a forgiving floor.
OA_AMAZON_SHARE_MAX: float = _f("OA_AMAZON_SHARE_MAX", 0.20)

# Non-returnable grocery can clear the ROI gate at a lower bar than other categories
# (profit is locked once sold, no return risk). From ai-brain.json criteria.exceptions.
OA_GROCERY_MIN_ROI: float = _f("OA_GROCERY_MIN_ROI", 0.25)

# Category -> referral-fee-rate map (replaces the flat 15% REFERRAL_RATE assumption for OA
# math when a candidate's category is known). "default" covers unlisted categories. From
# ai-brain.json `fees.referralRates` (sourced from Amazon's real fee table). $0.30 floor
# applies to every category per Amazon policy.
REFERRAL_RATES: dict = {"default": 0.15}
MIN_REFERRAL_FEE: float = _f("MIN_REFERRAL_FEE", 0.30)

# Price-banded referral rates for categories where a single flat rate is wrong (Code Review
# 2026-07-02, Finding CS6) — e.g. grocery is really 8% at/below $15 and 15% above it, and most
# of the $8-$60 OA price band sits above $15, so the old flat 0.08 overstated profit/ROI there.
# {category: {"priceThreshold": float, "atOrBelowThreshold": float, "aboveThreshold": float}}.
# Loaded from ai-brain.json's fees.bandedRates; empty (no banding) if the brain has none.
BANDED_REFERRAL_RATES: dict = {}

# The 5-7 seller "goldilocks" offer band: a scoring BONUS (not a gate — the hard band stays
# CRITERIA_OA["min_offers"]/["max_offers"], 3-25). From ai-brain.json scoring.preferredOffers.
PREFERRED_OFFERS: dict = {"min": 5, "max": 7, "bonus": 5}

# FBA-restriction keyword hints (guards.restrictionKeywords) — single-sourced so the scout AND
# the control-center Find page use the identical heuristic word list. Empty until the brain
# loads one; scoring.py keeps its own hardcoded copy as a fallback if the brain has none.
RESTRICTION_KEYWORDS: dict = {}

# Soft "price caution" guard (Scout Agent Build Plan sec 4.1, guards.currentVsAvg90PriceCaution):
# a smaller, earlier-warning point PENALTY at 1.15x the 90-day avg price — distinct from and
# evaluated separately from OA_PRICE_SPIKE_RATIO's 1.5x HARD flag. Never a gate.
OA_PRICE_CAUTION_RATIO: float = _f("OA_PRICE_CAUTION_RATIO", 1.15)

# Triage ranking (Scout Agent Build Plan sec 3.2, operations.triage): review-queue ordering by
# expected payback SPEED at a STRESSED (competed-down) price, not headline ROI. A ranking signal
# only — never a gate. 0.90 = assume the price gets competed down 10% before you can sell.
TRIAGE_STRESSED_PRICE_FACTOR: float = _f("TRIAGE_STRESSED_PRICE_FACTOR", 0.90)

# Operational doctrine blocks (Scout Agent Build Plan sec 3.5-3.8) — informational context for
# ops_report.py / the digest; not yet consumed by scoring math. Populated from ai-brain.json
# below; empty dict fallback if the brain has none.
OPERATIONS: dict = {}
POLICY_2026: dict = {}

# ----------------------------------------------------------------------------
# Scoring adjustment magnitudes, IP-cliff shape, worst-case-loss bar, and the assumed daily
# Keepa token budget — defaults match scoring.py's historical hardcoded values exactly.
# ai-brain.json's scoring.adjustments/ipCliffShape/worstCaseLossBarUsd/scoreThreshold/topN/
# assumedDailyTokens can override any of these (Code Review 2026-07-02, Finding S5) so a
# tuning change is a brain edit, not a code edit.
# ----------------------------------------------------------------------------
OA_ADJ_FRIENDLY_BRAND: float = _f("OA_ADJ_FRIENDLY_BRAND", 5.0)
OA_ADJ_PRICE_SPIKE: float = _f("OA_ADJ_PRICE_SPIKE", -15.0)
OA_ADJ_PRICE_CAUTION: float = _f("OA_ADJ_PRICE_CAUTION", -5.0)
OA_ADJ_OFFERS_RISING: float = _f("OA_ADJ_OFFERS_RISING", -12.0)
OA_ADJ_AMAZON_SHARES_BUYBOX: float = _f("OA_ADJ_AMAZON_SHARES_BUYBOX", -10.0)
OA_ADJ_IP_CLIFF: float = _f("OA_ADJ_IP_CLIFF", -20.0)
OA_ADJ_WORST_CASE_LOSS: float = _f("OA_ADJ_WORST_CASE_LOSS", -10.0)
OA_ADJ_NO_FEATURED_OFFER: float = _f("OA_ADJ_NO_FEATURED_OFFER", -8.0)
OA_ADJ_GENERIC_BRAND: float = _f("OA_ADJ_GENERIC_BRAND", -8.0)

# IP-cliff shape: a listing is "cliffed" when its 90-day avg offer count was once >= this
# (a real crowd existed) and its CURRENT offer count has collapsed to <= this.
OA_IP_CLIFF_MIN_AVG_OFFERS: float = _f("OA_IP_CLIFF_MIN_AVG_OFFERS", 8.0)
OA_IP_CLIFF_MAX_CURRENT_OFFERS: float = _f("OA_IP_CLIFF_MAX_CURRENT_OFFERS", 2.0)

# A loss <= this ($/unit) at the 90-day low Buy-Box price is tolerated without penalty; above
# it applies OA_ADJ_WORST_CASE_LOSS.
OA_WORST_CASE_LOSS_BAR: float = _f("OA_WORST_CASE_LOSS_BAR", 2.0)

# System Blueprint's assumed daily Keepa token budget — propose_updates.py flags a real drift
# against this in the weekly brain-proposal report.
ASSUMED_DAILY_TOKENS: int = _i("ASSUMED_DAILY_TOKENS", 7500)

# SINGLE SOURCE OF TRUTH: ai-brain.json's `criteria` override the defaults above (same
# file the control center reads). Feed Claude new guidance -> brain updates -> the rater's
# thresholds change too. Falls back to defaults/.env if the brain is absent.
def _load_oa_criteria_from_brain() -> None:
    global OA_PRICE_SPIKE_RATIO, OA_OFFERS_RISE_RATIO, OA_AMAZON_SHARE_MAX
    global OA_GROCERY_MIN_ROI, REFERRAL_RATES, MIN_REFERRAL_FEE, PREFERRED_OFFERS
    global RESTRICTION_KEYWORDS, OA_PRICE_CAUTION_RATIO, OPERATIONS, POLICY_2026
    global TRIAGE_STRESSED_PRICE_FACTOR
    global OA_ADJ_FRIENDLY_BRAND, OA_ADJ_PRICE_SPIKE, OA_ADJ_PRICE_CAUTION, OA_ADJ_OFFERS_RISING
    global OA_ADJ_AMAZON_SHARES_BUYBOX, OA_ADJ_IP_CLIFF, OA_ADJ_WORST_CASE_LOSS
    global OA_ADJ_NO_FEATURED_OFFER, OA_ADJ_GENERIC_BRAND
    global OA_IP_CLIFF_MIN_AVG_OFFERS, OA_IP_CLIFF_MAX_CURRENT_OFFERS, OA_WORST_CASE_LOSS_BAR
    global SCORE_THRESHOLD, TOP_N, ASSUMED_DAILY_TOKENS
    global FUEL_SURCHARGE, OA_PREP_COST, OA_INBOUND_SHIP_PER_LB
    global BANDED_REFERRAL_RATES
    import json
    import os as _os
    path = _os.path.join(_os.path.dirname(__file__), "..", "learning-hub", "data", "ai-brain.json")
    mapping = {
        "bsrMax": "bsr_max", "minMonthlySales": "min_monthly_sales",
        "minOffers": "min_offers", "maxOffers": "max_offers",
        "minRoi": "min_roi", "minProfitPerUnit": "min_profit_per_unit",
        "priceMin": "price_min", "priceMax": "price_max",
    }
    try:
        with open(path, "r", encoding="utf-8") as f:
            brain = json.load(f) or {}
        c = brain.get("criteria", {}) or {}
        for bk, sk in mapping.items():
            if c.get(bk) is not None:
                CRITERIA_OA[sk] = c[bk]
        exc = c.get("exceptions", {}) or {}
        if isinstance(exc.get("groceryMinRoi"), (int, float)):
            OA_GROCERY_MIN_ROI = float(exc["groceryMinRoi"])
        # Learned red-flag guards are also single-sourced from the brain (`guards` block).
        g = brain.get("guards", {}) or {}
        if isinstance(g.get("priceSpikeRatio"), (int, float)):
            OA_PRICE_SPIKE_RATIO = float(g["priceSpikeRatio"])
        if isinstance(g.get("offersRiseRatio"), (int, float)):
            OA_OFFERS_RISE_RATIO = float(g["offersRiseRatio"])
        if isinstance(g.get("amazonBuyBoxShareMax"), (int, float)):
            OA_AMAZON_SHARE_MAX = float(g["amazonBuyBoxShareMax"])
        rk = g.get("restrictionKeywords")
        if isinstance(rk, dict) and rk:
            RESTRICTION_KEYWORDS = {label: tuple(words) for label, words in rk.items() if isinstance(words, list)}
        if isinstance(g.get("currentVsAvg90PriceCaution"), (int, float)):
            OA_PRICE_CAUTION_RATIO = float(g["currentVsAvg90PriceCaution"])
        # Operational doctrine + policy facts (Scout Agent Build Plan) — informational blocks,
        # loaded as-is for ops_report.py/the digest; no per-key validation needed since nothing
        # here drives a gate or a score.
        ops = brain.get("operations")
        if isinstance(ops, dict):
            OPERATIONS = ops
            triage = ops.get("triage", {}) or {}
            if isinstance(triage.get("stressedPriceFactor"), (int, float)):
                TRIAGE_STRESSED_PRICE_FACTOR = float(triage["stressedPriceFactor"])
        pol = brain.get("policy2026")
        if isinstance(pol, dict):
            POLICY_2026 = pol
        # Category referral-fee map (fees.referralRates) and floor (fees.minReferralFee).
        fees = brain.get("fees", {}) or {}
        rates = fees.get("referralRates", {}) or {}
        if isinstance(rates, dict) and rates:
            REFERRAL_RATES = {k: float(v) for k, v in rates.items() if isinstance(v, (int, float))}
            REFERRAL_RATES.setdefault("default", 0.15)
        if isinstance(fees.get("minReferralFee"), (int, float)):
            MIN_REFERRAL_FEE = float(fees["minReferralFee"])
        # Price-banded rates (Finding CS6) — categories where a flat rate is wrong (e.g. grocery:
        # 8% at/below a price threshold, 15% above it).
        banded = fees.get("bandedRates", {}) or {}
        if isinstance(banded, dict) and banded:
            parsed_bands = {}
            for cat, band in banded.items():
                if not isinstance(band, dict):
                    continue
                required = ("priceThreshold", "atOrBelowThreshold", "aboveThreshold")
                if all(isinstance(band.get(k), (int, float)) for k in required):
                    parsed_bands[cat] = {k: float(band[k]) for k in required}
            if parsed_bands:
                BANDED_REFERRAL_RATES = parsed_bands
        # Fuel surcharge + prep cost (Finding S6) — single-sourced with the control-center's
        # deal-analyzer.tsx so a fee-schedule change is one brain edit, not two hardcoded
        # constants drifting apart.
        if isinstance(fees.get("fuelSurcharge"), (int, float)):
            FUEL_SURCHARGE = float(fees["fuelSurcharge"])
        if isinstance(fees.get("prepCost"), (int, float)):
            OA_PREP_COST = float(fees["prepCost"])
        if isinstance(fees.get("inboundShipPerLb"), (int, float)):
            OA_INBOUND_SHIP_PER_LB = float(fees["inboundShipPerLb"])
        scoring_block = brain.get("scoring", {}) or {}
        # Preferred-offer-band bonus (scoring.preferredOffers).
        pref = scoring_block.get("preferredOffers", {}) or {}
        if isinstance(pref, dict) and pref:
            PREFERRED_OFFERS = {
                "min": int(pref.get("min", PREFERRED_OFFERS["min"])),
                "max": int(pref.get("max", PREFERRED_OFFERS["max"])),
                "bonus": float(pref.get("bonus", PREFERRED_OFFERS["bonus"])),
            }
        # Scoring adjustment magnitudes (Finding S5) — each key is optional; only overrides the
        # ones the brain actually sets, everything else keeps its .env/hardcoded default.
        adj = scoring_block.get("adjustments", {}) or {}
        _adj_map = {
            "friendlyBrand": "OA_ADJ_FRIENDLY_BRAND", "priceSpike": "OA_ADJ_PRICE_SPIKE",
            "priceCaution": "OA_ADJ_PRICE_CAUTION", "offersRising": "OA_ADJ_OFFERS_RISING",
            "amazonSharesBuybox": "OA_ADJ_AMAZON_SHARES_BUYBOX", "ipCliff": "OA_ADJ_IP_CLIFF",
            "worstCaseLoss": "OA_ADJ_WORST_CASE_LOSS", "noFeaturedOffer": "OA_ADJ_NO_FEATURED_OFFER",
            "genericBrand": "OA_ADJ_GENERIC_BRAND",
        }
        if isinstance(adj, dict):
            for bk, var_name in _adj_map.items():
                if isinstance(adj.get(bk), (int, float)):
                    globals()[var_name] = float(adj[bk])
        # IP-cliff shape + worst-case-loss bar.
        shape = scoring_block.get("ipCliffShape", {}) or {}
        if isinstance(shape.get("minAvgOffers"), (int, float)):
            OA_IP_CLIFF_MIN_AVG_OFFERS = float(shape["minAvgOffers"])
        if isinstance(shape.get("maxCurrentOffers"), (int, float)):
            OA_IP_CLIFF_MAX_CURRENT_OFFERS = float(shape["maxCurrentOffers"])
        if isinstance(scoring_block.get("worstCaseLossBarUsd"), (int, float)):
            OA_WORST_CASE_LOSS_BAR = float(scoring_block["worstCaseLossBarUsd"])
        # Pipeline behaviour + assumed token budget.
        if isinstance(scoring_block.get("scoreThreshold"), (int, float)):
            SCORE_THRESHOLD = float(scoring_block["scoreThreshold"])
        if isinstance(scoring_block.get("topN"), (int, float)):
            TOP_N = int(scoring_block["topN"])
        if isinstance(scoring_block.get("assumedDailyTokens"), (int, float)):
            ASSUMED_DAILY_TOKENS = int(scoring_block["assumedDailyTokens"])
    except Exception as e:
        # Never fatal (the .env/hardcoded defaults still apply), but never silent either — a
        # malformed ai-brain.json quietly ignored would mean thresholds silently reverting.
        print(f"[config] WARNING: could not load overrides from ai-brain.json: {e}")


_load_oa_criteria_from_brain()


def referral_rate_for(category: str | None, price: float | None = None) -> float:
    """Category-aware referral rate; falls back to REFERRAL_RATES['default'].

    price: optional (Finding CS6) — when given AND the category has a price band in
    BANDED_REFERRAL_RATES (e.g. grocery: 8% at/below $15, 15% above), returns the banded rate
    instead of the flat REFERRAL_RATES value, which is wrong on either side of the threshold.
    Omitting price keeps the old flat-rate behavior exactly (backward compatible)."""
    if category:
        key = str(category).strip().lower().replace(" ", "_").replace("&", "")
        if price is not None and key in BANDED_REFERRAL_RATES:
            band = BANDED_REFERRAL_RATES[key]
            return band["atOrBelowThreshold"] if price <= band["priceThreshold"] else band["aboveThreshold"]
        rate = REFERRAL_RATES.get(key)
        if rate is not None:
            return rate
    return REFERRAL_RATES.get("default", REFERRAL_RATE)

# Knowledge-driven sourcing: seed the Keepa Product Finder toward the known-good
# brands in brands.py (the videos' "brand filter" method). Set
# SCOUT_USE_BRAND_SEEDS=0 to search broadly instead.
USE_BRAND_SEEDS: bool = os.getenv("SCOUT_USE_BRAND_SEEDS", "1") not in ("0", "false", "False", "")
BRAND_SEED_LIMIT: int = _i("BRAND_SEED_LIMIT", 25)


def active_criteria() -> dict:
    """The criteria dict for the current MODE (OA by default)."""
    return CRITERIA_OA if MODE == "OA" else CRITERIA


# ----------------------------------------------------------------------------
# Model blending
# ----------------------------------------------------------------------------
# Weight given to the ML model probability vs the transparent rule score when a
# trained model exists. 0.0 = ignore model, 1.0 = trust only the model.
# ML audit fix (2026-07-09): default 0.0, opt-in via env. At the old 0.5 default, the
# LEGACY sklearn model (scout_model.joblib, a separate artifact from the ranker) would
# have blended into blended_score at 50% weight the moment any such artifact appeared on
# disk — and blended_score gates threshold MEMBERSHIP (which candidates get posted), not
# just order, live-by-default with no shadow phase and no champion/challenger gate. The
# ranker path (scoring.rankingChampion) is the governed way to let a model influence
# anything; this stays 0 unless a human explicitly sets MODEL_BLEND_WEIGHT.
MODEL_BLEND_WEIGHT: float = _f("MODEL_BLEND_WEIGHT", 0.0)
MIN_LABELS_TO_TRAIN: int = _i("MIN_LABELS_TO_TRAIN", 20)  # need real data first

# DISABLED BY DEFAULT (Code Review 2026-07-02, Finding B4): this legacy SQLite-based retrain
# loop (storage.training_rows() -> model.py's FEATURES) is a separate, un-unified path from
# the leakage-safe Supabase loop (labels.py/calibration_report.py, System Blueprint Prompt
# 3.1), which enforces a real 30-label minimum and re-filters to PRE_DECISION_FEATURES on
# every read. It ran by default at only 20 SQLite labels. Set SCOUT_LEGACY_RETRAIN=1 to opt
# back in once you've reviewed model.py's FEATURES for leakage risk yourself.
LEGACY_RETRAIN_ENABLED: bool = os.getenv("SCOUT_LEGACY_RETRAIN", "0") in ("1", "true", "True")


def have_keepa() -> bool:
    return bool(KEEPA_KEY)


def have_discord() -> bool:
    return bool(DISCORD_WEBHOOK_URL)
