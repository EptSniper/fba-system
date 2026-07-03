"""
ingest_keepa.py — Keepa ingestion (public marketplace history).

Keepa is the sanctioned public-marketplace source (price, sales-rank, buy box,
offers, reviews, seller/storefront). We NEVER scrape Amazon. A PAID Keepa key is
required.

Writes daily ASIN snapshots to the operational DB and to the Parquet lake, and can
enrich competitor sellers via storefront queries. Product Finder / category params
are Keepa-specific — confirm exact names via help(api.product_finder) or Keepa's
"SHOW API QUERY". Keepa expects prices in CENTS and rating x10.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

import config
import database as db
import lake

try:
    import keepa
    _KEEPA = True
except Exception:  # pragma: no cover
    keepa = None
    _KEEPA = False

# Keepa CSV indices (confirm against your keepa version with help(keepa.Keepa)).
IDX_AMAZON, IDX_NEW, IDX_SALES_RANK = 0, 1, 3
IDX_COUNT_NEW, IDX_RATING, IDX_COUNT_REVIEWS, IDX_BUY_BOX = 11, 16, 17, 18
GRAMS_PER_LB = 453.59237


def _require():
    if not _KEEPA:
        raise ImportError("pip install keepa — and set a PAID KEEPA_KEY in .env")


def get_client(key: Optional[str] = None):
    _require()
    key = key or config.KEEPA_KEY
    if not key:
        raise ValueError("No KEEPA_KEY set (paid Keepa subscription required).")
    return keepa.Keepa(key)


def _cur(stats, idx):
    try:
        v = stats["current"][idx]
        return None if v is None or v == -1 else v
    except (KeyError, IndexError, TypeError):
        return None


def _dollars(c):
    return round(c / 100.0, 2) if isinstance(c, (int, float)) and c >= 0 else None


def _weight_lb(p):
    for k in ("packageWeight", "itemWeight"):
        g = p.get(k)
        if isinstance(g, (int, float)) and g > 0:
            return round(g / GRAMS_PER_LB, 3)
    return None


def _est_sales(stats):
    d30 = stats.get("salesRankDrops30")
    if isinstance(d30, (int, float)) and d30 >= 0:
        return int(d30)
    d90 = stats.get("salesRankDrops90")
    if isinstance(d90, (int, float)) and d90 >= 0:
        return int(round(d90 / 3.0))
    return None


def find_candidates(criteria: Optional[Dict[str, Any]] = None, api=None,
                    limit: Optional[int] = None) -> List[str]:
    """Product Finder candidate ASINs (confirm param names for your Keepa version)."""
    _require()
    api = api or get_client()
    c = criteria or config.CRITERIA
    limit = limit or config.CANDIDATE_LIMIT
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
    return list(api.product_finder(params, domain=config.KEEPA_DOMAIN) or [])[:limit]


def find_candidates_by_category(query: str, api=None, limit: Optional[int] = None) -> List[str]:
    """Alternative candidate source from the paper: category best-sellers."""
    _require()
    api = api or get_client()
    limit = limit or config.CANDIDATE_LIMIT
    cats = api.search_for_categories(query, domain=config.KEEPA_DOMAIN)
    if not cats:
        return []
    cat_id = next(iter(cats.keys()))
    asins = api.best_sellers_query(cat_id, rank_avg_range=90, domain=config.KEEPA_DOMAIN)
    return list(asins or [])[:limit]


def _to_snapshot(p: Dict[str, Any], today: dt.date) -> Dict[str, Any]:
    stats = p.get("stats") or {}
    rating_raw = _cur(stats, IDX_RATING)
    rating = round(rating_raw / 10.0, 1) if isinstance(rating_raw, (int, float)) else None
    title = p.get("title")
    return {
        "asin": p.get("asin"),
        "marketplace": config.KEEPA_DOMAIN,
        "snapshot_date": today,
        "category_id": str(p.get("rootCategory")) if p.get("rootCategory") else None,
        "brand": p.get("brand"),
        "title": title,
        "image_count": len(p.get("imagesCSV", "").split(",")) if p.get("imagesCSV") else None,
        "bullet_count": len(p.get("features") or []) if isinstance(p.get("features"), list) else None,
        "buy_box_price": (_dollars(stats.get("buyBoxPrice")) or _dollars(_cur(stats, IDX_BUY_BOX))),
        "price_new_fba": _dollars(_cur(stats, IDX_NEW)),
        "price_new_fbm": None,
        "price_amazon": _dollars(_cur(stats, IDX_AMAZON)),
        "sales_rank": _cur(stats, IDX_SALES_RANK),
        "offer_count_new": _cur(stats, IDX_COUNT_NEW),
        "offer_count_used": None,
        "rating": rating,
        "review_count": _cur(stats, IDX_COUNT_REVIEWS),
        "weight_lb": _weight_lb(p),
        "featured_offer_eligible": bool(stats.get("buyBoxSellerId")),
        "est_sales": _est_sales(stats),
        "raw": {"salesRankDrops30": stats.get("salesRankDrops30"),
                "salesRankDrops90": stats.get("salesRankDrops90"),
                "outOfStockPercentage90": stats.get("outOfStockPercentage90"),
                "buyBoxSellerId": stats.get("buyBoxSellerId")},
    }


def snapshot(asins: List[str], api=None) -> List[Dict[str, Any]]:
    """Pull stats for ASINs and return normalized snapshot rows (also persisted)."""
    if not asins:
        return []
    _require()
    api = api or get_client()
    today = dt.date.today()
    products = api.query(list(asins), domain=config.KEEPA_DOMAIN, stats=90,
                         rating=True, history=False) or []
    rows = []
    for p in products:
        try:
            if p.get("asin"):
                rows.append(_to_snapshot(p, today))
        except Exception:
            continue
    # persist: DB (always) + Parquet lake (if available)
    db.upsert(db.asin_snapshot_daily, rows, ["asin", "marketplace", "snapshot_date"])
    lake.write_snapshots(rows)
    return rows


def storefront(seller_ids: List[str], api=None) -> List[Dict[str, Any]]:
    """Competitor seller/storefront daily proxies (Keepa seller_query)."""
    if not seller_ids:
        return []
    _require()
    api = api or get_client()
    today = dt.date.today()
    res = api.seller_query(list(seller_ids), domain=config.KEEPA_DOMAIN,
                           storefront=True) or {}
    rows = []
    for sid, info in (res.items() if isinstance(res, dict) else []):
        asin_list = info.get("asinList", []) or []
        rows.append({
            "seller_id": sid,
            "snapshot_date": today,
            "storefront_asin_count": info.get("totalStorefrontAsins") or len(asin_list),
            "top_asins": asin_list[:50],
            "portfolio_category_mix": None,
            "estimated_buy_box_share": None,
            "avg_price_band": None,
        })
    db.upsert(db.seller_storefront_daily, rows, ["seller_id", "snapshot_date"])
    return rows


def ingest(criteria: Optional[Dict[str, Any]] = None, api=None) -> List[Dict[str, Any]]:
    """Find candidates -> snapshot -> persist. Returns today's snapshot rows."""
    api = api or get_client()
    asins = find_candidates(criteria, api=api)
    return snapshot(asins, api=api)
