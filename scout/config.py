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

# SINGLE SOURCE OF TRUTH: ai-brain.json's `criteria` override the defaults above (same
# file the control center reads). Feed Claude new guidance -> brain updates -> the rater's
# thresholds change too. Falls back to defaults/.env if the brain is absent.
def _load_oa_criteria_from_brain() -> None:
    global OA_PRICE_SPIKE_RATIO, OA_OFFERS_RISE_RATIO, OA_AMAZON_SHARE_MAX
    global OA_GROCERY_MIN_ROI, REFERRAL_RATES, MIN_REFERRAL_FEE, PREFERRED_OFFERS
    global RESTRICTION_KEYWORDS, OA_PRICE_CAUTION_RATIO, OPERATIONS, POLICY_2026
    global TRIAGE_STRESSED_PRICE_FACTOR
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
        # Preferred-offer-band bonus (scoring.preferredOffers).
        pref = brain.get("scoring", {}).get("preferredOffers", {}) or {}
        if isinstance(pref, dict) and pref:
            PREFERRED_OFFERS = {
                "min": int(pref.get("min", PREFERRED_OFFERS["min"])),
                "max": int(pref.get("max", PREFERRED_OFFERS["max"])),
                "bonus": float(pref.get("bonus", PREFERRED_OFFERS["bonus"])),
            }
    except Exception:
        pass


_load_oa_criteria_from_brain()


def referral_rate_for(category: str | None) -> float:
    """Category-aware referral rate; falls back to REFERRAL_RATES['default']."""
    if category:
        key = str(category).strip().lower().replace(" ", "_").replace("&", "")
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
MODEL_BLEND_WEIGHT: float = _f("MODEL_BLEND_WEIGHT", 0.5)
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
