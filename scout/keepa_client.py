"""
keepa_client.py — thin, defensive wrapper around the `keepa` Python package.

Data policy: we NEVER scrape Amazon. Keepa is a sanctioned, paid data layer that
licenses Amazon price + sales-rank history. A PAID Keepa key is required
(Premium ~$19+/mo unlocks sales-rank data, Product Finder, and API access).

IMPORTANT about field names / Product Finder params:
    Keepa's Product Finder filter set is large and Keepa-specific, and the exact
    parameter keys change over time. Two ways to get the EXACT names for your
    account/version:
      1. Run  help(api.product_finder)  after constructing the client.
      2. Build the filter you want in Keepa's website Product Finder UI, then click
         "SHOW API QUERY" — it prints the precise JSON keys to copy here.
    The params below are a sensible starting set; confirm them before relying on
    results. Keepa expects PRICES IN CENTS and RATING x10 (4.3 stars -> 43).

The `keepa` import is guarded so this file (and the rest of the project) loads even
if the package isn't installed yet.
"""
from __future__ import annotations

import concurrent.futures
import os
from typing import Any, Dict, List, Optional

import config
import brands

try:
    import keepa  # pip install keepa
    _KEEPA = True
except Exception:  # pragma: no cover - package optional at import time
    keepa = None
    _KEEPA = False

# Code Review 2026-07-02, Finding S2: wait=True (used below) drip-paces against Keepa's token
# bucket by blocking/retrying with no built-in cap — a severely drained bucket can block a
# scheduled run indefinitely, past its next scheduled start. _with_deadline() wraps any such
# call in a hard wall-clock timeout via a background thread, so a drained key aborts this
# cycle honestly (the exception flows through pipeline.run_once()'s existing error handling —
# runs.error_summary, the digest, system_health) instead of hanging the whole process. Known
# limitation: Python cannot force-cancel a running thread, so the underlying Keepa call keeps
# blocking in the background until it either completes or the process exits — acceptable for a
# short-lived scheduled script, not for a long-running server.
KEEPA_CALL_DEADLINE_SECONDS = int(os.getenv("KEEPA_CALL_DEADLINE_SECONDS", "600"))  # 10 min


def _with_deadline(fn, *args, **kwargs):
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn, *args, **kwargs)
        try:
            return future.result(timeout=KEEPA_CALL_DEADLINE_SECONDS)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(
                f"Keepa call exceeded the {KEEPA_CALL_DEADLINE_SECONDS}s deadline "
                f"(KEEPA_CALL_DEADLINE_SECONDS in .env) — likely a drained token bucket. "
                f"Aborting this cycle rather than blocking past the next scheduled run."
            )

# Keepa CSV "type" indices used to read stats['current'].
# (These follow Keepa's documented CSV ordering; confirm against your keepa
#  version with help(keepa.Keepa) if values look off.)
IDX_AMAZON = 0
IDX_NEW = 1
IDX_SALES_RANK = 3
IDX_COUNT_NEW = 11      # number of new offers (Buy Box crowding proxy)
IDX_RATING = 16         # rating x10  (45 -> 4.5 stars)
IDX_COUNT_REVIEWS = 17
IDX_BUY_BOX = 18        # buy box landed price (cents)

GRAMS_PER_LB = 453.59237


def _require_keepa():
    if not _KEEPA:
        raise ImportError(
            "The 'keepa' package is not installed. Run: pip install keepa\n"
            "You also need a PAID Keepa subscription key set as KEEPA_KEY in .env."
        )


def get_client(key: Optional[str] = None):
    """Construct a keepa.Keepa client. Raises a clear error if key/package missing."""
    _require_keepa()
    key = key or config.KEEPA_KEY
    if not key:
        raise ValueError("No Keepa key. Set KEEPA_KEY in .env (paid Keepa subscription).")
    return keepa.Keepa(key)


# ----------------------------------------------------------------------------
# helpers to read Keepa's stats safely
# ----------------------------------------------------------------------------
def _cur(stats: Dict[str, Any], idx: int):
    """Read stats['current'][idx], treating Keepa's -1 / missing as None."""
    try:
        v = stats["current"][idx]
        if v is None or v == -1:
            return None
        return v
    except (KeyError, IndexError, TypeError):
        return None


def _cents_to_dollars(c):
    return round(c / 100.0, 2) if isinstance(c, (int, float)) and c >= 0 else None


def _weight_lb(product: Dict[str, Any]) -> Optional[float]:
    for k in ("packageWeight", "itemWeight"):
        g = product.get(k)
        if isinstance(g, (int, float)) and g > 0:
            return round(g / GRAMS_PER_LB, 2)
    return None


def _est_monthly_sales(stats: Dict[str, Any]) -> Optional[int]:
    """
    Estimate monthly units from Keepa 'Sales Rank Drops'. Each drop ~ a sale.
    Accurate at low volume; noisier above ~50/mo. Prefer the 30-day count.
    """
    d30 = stats.get("salesRankDrops30")
    if isinstance(d30, (int, float)) and d30 >= 0:
        return int(d30)
    d90 = stats.get("salesRankDrops90")
    if isinstance(d90, (int, float)) and d90 >= 0:
        return int(round(d90 / 3.0))
    return None


# Amazon category-tree names (Keepa's categoryTree[].name, a root->leaf breadcrumb of
# {catId, name}) mapped to this project's referral-rate keys (ai-brain.json
# fees.referralRates) — Amazon's real category names ("Toys & Games") are longer/human than
# our short rate keys ("toys"), so this is a translation table, not a passthrough. Deliberately
# incomplete: only covers categories the brain actually prices; add more as OA candidates hit
# an unmapped category (Code Review 2026-07-02, Finding S3).
_CATEGORY_MAP = {
    "toys & games": "toys",
    "home & kitchen": "home",
    "kitchen & dining": "kitchen",
    "grocery & gourmet food": "grocery",
    "beauty & personal care": "beauty",
    "health & household": "health",
    "health & personal care": "health",
    "clothing, shoes & jewelry": "clothing",
    "shoes": "shoes",
    "office products": "office",
    "pet supplies": "pet",
    "sports & outdoors": "sports",
    "tools & home improvement": "tools",
    "baby products": "baby",
    "baby": "baby",
    "cell phones & accessories": "electronics_accessories",
    "electronics": "electronics_accessories",
}


def _category_from_tree(product: Dict[str, Any]):
    """Map Keepa's categoryTree to one of this project's referral-rate keys. Tries every level
    leaf-to-root (the mapping table is deliberately incomplete); falls back to the raw root
    category name so callers always get SOMETHING to display even when it won't match a
    referral-rate key (config.referral_rate_for degrades to REFERRAL_RATES['default'] either
    way). Returns (category_or_none, category_source_or_none) — category_source is
    "keepa_category_tree" only when Keepa actually provided tree data, so callers can tell a
    real-but-unmapped category from "Keepa gave us nothing."""
    tree = product.get("categoryTree")
    if not isinstance(tree, list) or not tree:
        return None, None
    names = [n.get("name") for n in tree if isinstance(n, dict) and n.get("name")]
    if not names:
        return None, None
    for name in reversed(names):  # leaf-to-root
        mapped = _CATEGORY_MAP.get(name.strip().lower())
        if mapped:
            return mapped, "keepa_category_tree"
    return names[0], "keepa_category_tree"


def _normalize(product: Dict[str, Any]) -> Dict[str, Any]:
    stats = product.get("stats") or {}
    # price: prefer Buy Box, then NEW, then Amazon
    price = (_cents_to_dollars(stats.get("buyBoxPrice"))
             or _cents_to_dollars(_cur(stats, IDX_BUY_BOX))
             or _cents_to_dollars(_cur(stats, IDX_NEW))
             or _cents_to_dollars(_cur(stats, IDX_AMAZON)))
    rating_raw = _cur(stats, IDX_RATING)
    rating = round(rating_raw / 10.0, 1) if isinstance(rating_raw, (int, float)) else None
    reviews = _cur(stats, IDX_COUNT_REVIEWS)
    offers = _cur(stats, IDX_COUNT_NEW)
    sales_rank = _cur(stats, IDX_SALES_RANK)
    # 90-day average price (for the price-spike check). Keepa exposes stats['avg90'].
    avg90 = stats.get("avg90") or []

    def _avg90(idx):
        try:
            v = avg90[idx]
            return _cents_to_dollars(v) if v not in (None, -1) else None
        except (IndexError, TypeError):
            return None

    avg_price_90 = _avg90(IDX_BUY_BOX) or _avg90(IDX_NEW)

    def _avg90_count(idx):
        try:
            v = avg90[idx]
            return int(v) if isinstance(v, (int, float)) and v not in (None, -1) else None
        except (IndexError, TypeError):
            return None

    avg_offers_90 = _avg90_count(IDX_COUNT_NEW)

    # 90-day average SALES RANK (Scout Agent Build Plan sec 3.1 — "gate on avg90, not current
    # values"; current BSR is stockout/spike-prone). Same avg90 array, sales-rank index.
    def _avg90_rank(idx):
        try:
            v = avg90[idx]
            return int(v) if isinstance(v, (int, float)) and v not in (None, -1) else None
        except (IndexError, TypeError):
            return None

    avg_sales_rank_90 = _avg90_rank(IDX_SALES_RANK)

    # Amazon's Buy-Box WIN SHARE over the period (Buy-Box "rotation"). Keepa returns
    # `buyBoxStats` when query(..., buybox=True): a dict keyed by sellerId ->
    # {percentageWon, avgPrice, isFBA, ...}. We read Amazon's percentageWon (0-100) and
    # normalize to a 0-1 fraction. Confirm the exact key/units against your keepa version.
    def _amazon_bb_share():
        bbs = product.get("buyBoxStats") or stats.get("buyBoxStats") or {}
        if not isinstance(bbs, dict):
            return None
        entry = bbs.get(config.AMAZON_SELLER_ID)
        pw = entry.get("percentageWon") if isinstance(entry, dict) else None
        return round(pw / 100.0, 3) if isinstance(pw, (int, float)) and pw >= 0 else None

    amazon_bb_share = _amazon_bb_share()

    # 90-day LOW Buy-Box price (for the worst-case break-even check in scoring). Keepa exposes the
    # minimum differently across versions (`min90` scalar array, or `min` where each entry may be a
    # [timestamp, value] pair) — read defensively; degrade to None rather than guess.
    min90 = stats.get("min90") or stats.get("min") or []

    def _min90_price(idx):
        try:
            v = min90[idx]
        except (IndexError, TypeError):
            return None
        if isinstance(v, (list, tuple)):
            v = v[-1] if v else None
        return _cents_to_dollars(v) if v not in (None, -1) else None

    price_low_90 = _min90_price(IDX_BUY_BOX) or _min90_price(IDX_NEW)

    # Featured offer (Buy Box) presence. buybox_price is the current Buy-Box landed price; has_buybox
    # is True/False/None — only False when we have offer data but NO featured offer, so a missing-data
    # product never falsely trips the "no featured offer" flag in scoring.
    bb_price = _cents_to_dollars(stats.get("buyBoxPrice")) or _cents_to_dollars(_cur(stats, IDX_BUY_BOX))
    bb_seller = stats.get("buyBoxSellerId")
    if bb_seller or bb_price:
        has_buybox = True
    elif offers is not None:
        has_buybox = False
    else:
        has_buybox = None

    category, category_source = _category_from_tree(product)

    return {
        "asin": product.get("asin"),
        "title": product.get("title"),
        "brand": product.get("brand"),
        "category": category,
        "category_source": category_source,
        "price": price,
        "rating": rating,
        "reviews": int(reviews) if isinstance(reviews, (int, float)) else None,
        "offers": int(offers) if isinstance(offers, (int, float)) else None,
        "sales_rank": int(sales_rank) if isinstance(sales_rank, (int, float)) else None,
        "weight_lb": _weight_lb(product),
        "est_sales": _est_monthly_sales(stats),
        "drops30": stats.get("salesRankDrops30"),
        "drops90": stats.get("salesRankDrops90"),
        "buybox_seller": bb_seller,
        "buybox_price": bb_price,
        "has_buybox": has_buybox,
        "oos_90": stats.get("outOfStockPercentage90"),
        "avg_price_90": avg_price_90,
        "avg_offers_90": avg_offers_90,
        "avg_sales_rank_90": avg_sales_rank_90,
        "price_low_90": price_low_90,
        "amazon_bb_share": amazon_bb_share,
    }


# ----------------------------------------------------------------------------
# public API
# ----------------------------------------------------------------------------
def find_candidates(criteria: Optional[Dict[str, Any]] = None,
                    api=None, limit: Optional[int] = None) -> List[str]:
    """
    Use Keepa Product Finder to return candidate ASINs matching the criteria.

    Returns a list of ASIN strings. See the module docstring about confirming the
    exact Product Finder parameter names for your Keepa version.
    """
    _require_keepa()
    api = api or get_client()
    c = criteria or config.active_criteria()
    limit = limit or config.CANDIDATE_LIMIT

    # ---- Product Finder query (CONFIRM these keys via help(api.product_finder)
    #      or Keepa's "SHOW API QUERY"). Prices in CENTS, rating x10. ----
    if config.MODE == "OA":
        # Online arbitrage: mirror the Keepa Product Finder recipe from the videos —
        # price band + sales-rank cap + a seller-count BAND + proven velocity.
        # (Amazon-on-Buy-Box and rising-offer trend are filtered later in scoring.)
        params: Dict[str, Any] = {
            "current_NEW_gte": int(c["price_min"] * 100),
            "current_NEW_lte": int(c["price_max"] * 100),
            "current_SALES_lte": int(c["bsr_max"]),         # sales RANK <= max (CONFIRM key)
            "current_COUNT_NEW_gte": int(c["min_offers"]),  # >= a few sellers => OA, not PL/wholesale
            "current_COUNT_NEW_lte": int(c["max_offers"]),  # but not a crowded price war
            "packageWeight_lte": int(c["max_weight_lb"] * GRAMS_PER_LB),
            "salesRankDrops30_gte": int(c["min_monthly_sales"]),
            "sort": [["salesRankDrops30", "desc"]],
            "perPage": min(limit, 10000),
            "page": 0,
        }
        # Knowledge-driven: aim at our known-good brands (brands.py) like the videos do.
        if config.USE_BRAND_SEEDS:
            seeds = brands.seed_brands(config.BRAND_SEED_LIMIT)
            if seeds:
                params["brand"] = seeds   # CONFIRM exact key via Keepa "SHOW API QUERY"
    else:
        # Private label (legacy): weak incumbents + beatable review moat.
        params = {
            "current_NEW_gte": int(c["price_min"] * 100),
            "current_NEW_lte": int(c["price_max"] * 100),
            "current_COUNT_REVIEWS_lte": int(c["max_reviews"]),
            "current_RATING_lte": int(c["max_rating"] * 10),
            "current_COUNT_NEW_lte": int(c["max_offers"]),
            "packageWeight_lte": int(c["max_weight_lb"] * GRAMS_PER_LB),
            "salesRankDrops30_gte": int(c["min_monthly_sales"]),
            "sort": [["salesRankDrops30", "desc"]],
            "perPage": min(limit, 10000),
            "page": 0,
        }

    # wait=True: drip-pace against the token bucket (block/retry instead of erroring on a rate
    # limit) — System Blueprint Prompt G2's "drip, not burst" rule; safe for a nightly run.
    # Wrapped in a hard deadline (Finding S2) so a drained bucket aborts honestly instead of
    # blocking indefinitely.
    asins = _with_deadline(api.product_finder, params, domain=config.KEEPA_DOMAIN, wait=True)
    return list(asins or [])[:limit]


def enrich(asins: List[str], api=None) -> List[Dict[str, Any]]:
    """
    Pull stats for ASINs via api.query and normalize the fields we score on:
    price, est_sales (from sales-rank drops), reviews, rating, weight, offers.
    """
    if not asins:
        return []
    _require_keepa()
    api = api or get_client()

    # stats=90 computes 90-day stats incl. salesRankDrops30/90; rating=True pulls
    # rating + review counts; buybox=True returns buyBoxStats (Amazon's Buy-Box win
    # share, for the rotation guard). These extra fields can cost more Keepa tokens.
    # Wrapped in a hard deadline (Finding S2) — same reasoning as find_candidates() above.
    products = _with_deadline(
        api.query,
        list(asins),
        domain=config.KEEPA_DOMAIN,
        stats=90,
        rating=True,
        buybox=True,     # -> product['buyBoxStats']: who wins the Buy Box & how often
        history=False,   # we only need stats, not full time series -> cheaper
        wait=True,        # drip-pace against the token bucket (System Blueprint Prompt G2)
    )
    out = []
    for p in (products or []):
        try:
            out.append(_normalize(p))
        except Exception:
            # never let one bad product blow up the batch
            out.append({"asin": p.get("asin"), "title": p.get("title")})
    return out


def token_telemetry(api) -> Dict[str, Optional[int]]:
    """Read tokensLeft/tokensConsumed off a keepa.Keepa client instance for the runs table
    (System Blueprint Prompt G2 — "a drained key silently looks like no results, alert on
    tokensLeft"). Read defensively via getattr: the python keepa lib exposes these as plain
    instance attributes updated after each request, but never assume the exact attribute
    names are stable across versions — degrade to None rather than raise."""
    return {
        "tokens_left": getattr(api, "tokens_left", None),
        "tokens_consumed": getattr(api, "tokens_consumed_total", None) or getattr(api, "tokens_consumed", None),
    }


def seller_asins(seller_id: str, api=None) -> List[str]:
    """Return the ASINs in a seller's catalog via Keepa's seller data."""
    _require_keepa()
    api = api or get_client()
    res = api.seller_query(seller_id, domain=config.KEEPA_DOMAIN)
    info = (res or {}).get(seller_id, {}) if isinstance(res, dict) else {}
    return list(info.get("asinList", []) or [])


def seller_catalog_signals(asins: List[str], api=None) -> List[Dict[str, Any]]:
    """
    Rank a competitor's ASINs by VELOCITY PROXIES, highest first.

    NOTE (be honest in comments): Keepa cannot reveal a competitor's exact private
    sales. The legitimate signals are velocity PROXIES — Keepa 'Sales Rank Drops'
    (each drop ~ a sale) and Buy Box stability / low out-of-stock %. We rank on
    those, not on real sales numbers.
    """
    enriched = enrich(asins, api=api)
    for e in enriched:
        drops = e.get("est_sales") or 0
        oos = e.get("oos_90") or 0
        has_buybox = 1 if e.get("buybox_seller") else 0
        # simple, transparent velocity proxy
        e["velocity_proxy"] = round(drops * (1 - min(oos, 100) / 100.0) + 2 * has_buybox, 2)
    enriched.sort(key=lambda x: x.get("velocity_proxy", 0), reverse=True)
    return enriched
