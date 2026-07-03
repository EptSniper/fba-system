"""
config.py — central configuration for the production FBA discovery system.

Design follows "Designing a Continuously Learning Amazon FBA Product Discovery
System": prefer official Amazon/Ads data for truth, Keepa for public-marketplace
history, third-party tools as enrichment; gated retraining (never uncontrolled
online learning); compliance gates first; weak (public proxy) vs strong (realized)
labels kept separate.

Everything is environment-driven (see .env.example). Sensible defaults let the
whole stack run locally on SQLite + scikit-learn with no external infrastructure.
"""
from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # pragma: no cover
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


def _b(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Data layer
# ---------------------------------------------------------------------------
# Postgres in production (e.g. postgresql+psycopg://user:pass@host:5432/fba).
# If unset, we fall back to a local SQLite file so the system runs with zero infra.
DATABASE_URL: str = os.getenv("DATABASE_URL") or "sqlite:///scout_pro.db"

# Raw history is also written to Parquet for cheap analytical backfills/training.
DATA_LAKE_DIR: str = os.getenv("DATA_LAKE_DIR", "data_lake")          # parquet root
MODEL_REGISTRY_DIR: str = os.getenv("MODEL_REGISTRY_DIR", "model_registry")

# ---------------------------------------------------------------------------
# Credentials (only Keepa + Discord are needed to run discovery)
# ---------------------------------------------------------------------------
KEEPA_KEY: str | None = os.getenv("KEEPA_KEY") or None
KEEPA_DOMAIN: str = os.getenv("KEEPA_DOMAIN", "US")
DISCORD_WEBHOOK_URL: str | None = os.getenv("DISCORD_WEBHOOK_URL") or None

# Owned-account truth (optional; connectors are documented stubs until wired).
SP_API_REFRESH_TOKEN: str | None = os.getenv("SP_API_REFRESH_TOKEN") or None
SP_API_CLIENT_ID: str | None = os.getenv("SP_API_CLIENT_ID") or None
SP_API_CLIENT_SECRET: str | None = os.getenv("SP_API_CLIENT_SECRET") or None
ADS_API_REFRESH_TOKEN: str | None = os.getenv("ADS_API_REFRESH_TOKEN") or None

# ---------------------------------------------------------------------------
# Discovery criteria (pre-launch sourcing screen)
# ---------------------------------------------------------------------------
CRITERIA = {
    "price_min": _f("PRICE_MIN", 15.0),
    "price_max": _f("PRICE_MAX", 50.0),
    "min_monthly_sales": _i("MIN_MONTHLY_SALES", 200),
    "max_reviews": _i("MAX_REVIEWS", 500),
    "max_rating": _f("MAX_RATING", 4.3),
    "max_weight_lb": _f("MAX_WEIGHT_LB", 1.0),
    "max_offers": _i("MAX_OFFERS", 15),
}
CANDIDATE_LIMIT: int = _i("CANDIDATE_LIMIT", 200)

# ---------------------------------------------------------------------------
# Online-Arbitrage (OA) criteria — additive "OA mode" alongside the PL CRITERIA
# above (mirrors scout/config.py so scout_pro can run the same OA discipline).
# Amazon's own seller id (US marketplace). If Amazon holds the Buy Box, an OA
# reseller can't realistically win sales -> we reject/penalize those.
# ---------------------------------------------------------------------------
AMAZON_SELLER_ID: str = os.getenv("AMAZON_SELLER_ID", "ATVPDKIKX0DER")

# Assumed OA buy cost as a fraction of the Amazon sell price (Keepa has no real
# cost). ESTIMATE for pre-filtering only — always confirm the true cost + ROI
# in SellerAmp before buying.
OA_COGS_FRACTION: float = _f("OA_COGS_FRACTION", 0.50)

# Per-unit PREP cost (poly bag + label + labor). As of Jan 1, 2026 Amazon no
# longer preps/labels FBA items in the US — the seller must, so every OA buy
# carries this cost. Subtracted from the profit/ROI estimate.
OA_PREP_COST: float = _f("OA_PREP_COST", 0.50)

CRITERIA_OA = {
    "price_min": _f("OA_PRICE_MIN", 8.0),
    "price_max": _f("OA_PRICE_MAX", 60.0),
    "bsr_max": _i("OA_BSR_MAX", 200000),
    "min_monthly_sales": _i("OA_MIN_SALES", 50),
    "min_offers": _i("OA_MIN_OFFERS", 3),
    "max_offers": _i("OA_MAX_OFFERS", 25),
    "max_weight_lb": _f("OA_MAX_WEIGHT_LB", 5.0),
    "min_roi": _f("OA_MIN_ROI", 0.30),
    "min_profit_per_unit": _f("OA_MIN_PROFIT", 3.0),
}

# Price-spike guard: if the current price is far above its 90-day average, it's
# likely to revert — brutal with FBA's ~2-week check-in delay.
OA_PRICE_SPIKE_RATIO: float = _f("OA_PRICE_SPIKE_RATIO", 1.5)
# Rising-offers guard ("seller spike"): if the current new-offer count is far
# above its 90-day average, more sellers are piling in -> the price is about to tank.
OA_OFFERS_RISE_RATIO: float = _f("OA_OFFERS_RISE_RATIO", 1.4)
# Amazon Buy-Box SHARE guard (Buy-Box "rotation"): even when Amazon isn't the
# CURRENT Buy-Box holder, if it wins the Buy Box at least this fraction of the
# time it keeps stealing your sales -> hard reject. Below this (but > 0) we
# penalize + flag instead.
OA_AMAZON_SHARE_MAX: float = _f("OA_AMAZON_SHARE_MAX", 0.20)


# SINGLE SOURCE OF TRUTH: ai-brain.json's `criteria`/`guards` override the
# defaults above (same file scout/config.py and the control center read). Feed
# Claude new guidance -> brain updates -> scout_pro's thresholds change too.
# Falls back to defaults/.env if the brain is absent.
def _load_oa_criteria_from_brain() -> None:
    global OA_PRICE_SPIKE_RATIO, OA_OFFERS_RISE_RATIO, OA_AMAZON_SHARE_MAX
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
        # Learned red-flag guards are also single-sourced from the brain (`guards` block).
        g = brain.get("guards", {}) or {}
        if isinstance(g.get("priceSpikeRatio"), (int, float)):
            OA_PRICE_SPIKE_RATIO = float(g["priceSpikeRatio"])
        if isinstance(g.get("offersRiseRatio"), (int, float)):
            OA_OFFERS_RISE_RATIO = float(g["offersRiseRatio"])
        if isinstance(g.get("amazonBuyBoxShareMax"), (int, float)):
            OA_AMAZON_SHARE_MAX = float(g["amazonBuyBoxShareMax"])
    except Exception:
        pass


_load_oa_criteria_from_brain()


# ---------------------------------------------------------------------------
# Hard gates (rules-first; these REJECT regardless of model score)
# ---------------------------------------------------------------------------
GATES = {
    "margin_floor": _f("GATE_MARGIN_FLOOR", 0.15),       # reject < 15% est. net margin
    "max_offers": _i("GATE_MAX_OFFERS", 25),             # severe offer crowding
    "max_lead_time_days": _i("GATE_MAX_LEAD_TIME", 60),  # impossible cash cycle
    "max_weight_lb": _f("GATE_MAX_WEIGHT_LB", 5.0),      # oversize fee risk
    # comma-separated, case-insensitive substrings that block a product
    "forbidden_category_terms": os.getenv(
        "GATE_FORBIDDEN_CATEGORIES",
        "lithium,battery,hazmat,flammable,aerosol,knife,weapon,supplement,cbd,medical device,grocery",
    ).lower().split(","),
}

# ---------------------------------------------------------------------------
# Labels: parameterized family (weak public-proxy + strong realized)
# ---------------------------------------------------------------------------
LABEL_HORIZONS = [int(x) for x in os.getenv("LABEL_HORIZONS", "30,90,180").split(",")]
PRIMARY_HORIZON: int = _i("PRIMARY_HORIZON", 90)

# Strong realized success thresholds (your own account; from SP-API/Ads later)
STRONG_LABEL = {
    "min_contribution_margin": _f("STRONG_MIN_MARGIN", 0.20),   # 20% net
    "min_units": _i("STRONG_MIN_UNITS", 200),                   # per horizon
    "min_featured_offer_share": _f("STRONG_MIN_FO_SHARE", 0.7),
    "max_return_rate": _f("STRONG_MAX_RETURN_RATE", 0.10),
}

# Weak public-proxy label weights (competitor ASINs; never substitutes realized)
WEAK_LABEL_WEIGHTS = {
    "rank_stability": _f("W_RANK_STABILITY", 0.30),
    "price_resilience": _f("W_PRICE_RESILIENCE", 0.20),
    "buybox_continuity": _f("W_BUYBOX_CONTINUITY", 0.20),
    "review_velocity_health": _f("W_REVIEW_HEALTH", 0.15),
    "offer_crowding_penalty": _f("W_OFFER_CROWDING", 0.10),
    "compliance_risk_penalty": _f("W_COMPLIANCE_RISK", 0.05),
}
WEAK_SUCCESS_THRESHOLD: float = _f("WEAK_SUCCESS_THRESHOLD", 0.60)

# ---------------------------------------------------------------------------
# Margin-estimate assumptions (2026 fee schedule; used pre-launch)
# ---------------------------------------------------------------------------
REFERRAL_RATE: float = _f("REFERRAL_RATE", 0.15)
FUEL_SURCHARGE: float = _f("FUEL_SURCHARGE", 0.035)   # 3.5% on fulfillment (2026)
COGS_FRACTION: float = _f("COGS_FRACTION", 0.30)
PPC_FRACTION: float = _f("PPC_FRACTION", 0.10)
TARGET_NET_MARGIN: float = _f("TARGET_NET_MARGIN", 0.25)

# ---------------------------------------------------------------------------
# Model + serving
# ---------------------------------------------------------------------------
MODEL_BLEND_WEIGHT: float = _f("MODEL_BLEND_WEIGHT", 0.5)     # rule vs model
MIN_LABELS_TO_TRAIN: int = _i("MIN_LABELS_TO_TRAIN", 40)
ALERT_PROBABILITY: float = _f("ALERT_PROBABILITY", 0.70)     # calibrated P(success) to alert
# Uncertainty band around the decision boundary -> route to human review, don't auto-alert
UNCERTAINTY_LOW: float = _f("UNCERTAINTY_LOW", 0.45)
UNCERTAINTY_HIGH: float = _f("UNCERTAINTY_HIGH", 0.65)
TOP_N: int = _i("TOP_N", 5)

# Champion/challenger promotion: challenger must beat champion PR-AUC by this margin
PROMOTION_MIN_GAIN: float = _f("PROMOTION_MIN_GAIN", 0.02)
# Drift: population-stability-index above this on key features triggers a retrain
DRIFT_PSI_THRESHOLD: float = _f("DRIFT_PSI_THRESHOLD", 0.2)


def have_keepa() -> bool:
    return bool(KEEPA_KEY)


def have_discord() -> bool:
    return bool(DISCORD_WEBHOOK_URL)


def using_sqlite() -> bool:
    return DATABASE_URL.startswith("sqlite")
