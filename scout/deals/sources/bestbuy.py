"""
scout/deals/sources/bestbuy.py — Best Buy Products API connector (Deal Finder Build Plan,
Prompt D1). The only major US big-box retailer with a free, official, open developer API —
research found onSale filters + UPCs on every product, no scraping needed.

Requires BESTBUY_API_KEY in scout/.env (register at developer.bestbuy.com — the build plan
flags that signups from free-email domains like Gmail are rejected; a domain email is
needed). Absent -> honest no-op ([]), never fakes rows. Rate limits are UNVERIFIED until a
real key exists and is exercised (the build plan cites ~5 req/s / 50k/day as commonly
reported, not confirmed) — page_size/max_pages default conservatively; widen once observed
limits are recorded here.

SECRET-IN-URL NOTE (Code Review 2026-07-02, Finding B5): the Best Buy API takes apiKey as a
query parameter (there is no header-based auth option in their API), so a request exception
(e.g. requests.raise_for_status()) can legitimately embed the real key in its message —
every place that logs such an exception here redacts it first.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

import redact

from .. import brain_config

log = logging.getLogger("scout.deals.bestbuy")

API_BASE = "https://api.bestbuy.com/v1/products"
DEFAULT_CATEGORIES: List[Optional[str]] = [None]  # None = no category filter (all onSale items)
DEFAULT_PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 1  # conservative until real rate limits are observed


def configured() -> bool:
    return bool(os.getenv("BESTBUY_API_KEY")) and requests is not None


def _fetch_page(api_key: str, category: Optional[str], page: int, page_size: int, timeout: int) -> Dict[str, Any]:
    filters = "onSale=true"
    if category:
        filters += f"&categoryPath.id={category}"
    url = (
        f"{API_BASE}({filters})?apiKey={api_key}&format=json"
        f"&show=sku,name,manufacturer,upc,salePrice,regularPrice,url"
        f"&pageSize={page_size}&page={page}"
    )
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _row_from_product(p: Dict[str, Any]) -> Dict[str, Any]:
    sale = p.get("salePrice")
    reg = p.get("regularPrice")
    discount_pct = round((1 - sale / reg) * 100, 1) if sale and reg else None
    return {
        "retailer": "Best Buy",
        "source": "bestbuy",
        "sku": str(p["sku"]) if p.get("sku") is not None else None,
        "upc": p.get("upc"),
        "title_raw": p.get("name") or "",
        "brand": p.get("manufacturer"),
        "price_current": sale,
        "price_original": reg,
        "discount_pct": discount_pct,
        "url": p.get("url"),
    }


def collect(categories: Optional[List[Optional[str]]] = None,
           page_size: Optional[int] = None,
           max_pages: Optional[int] = None,
           timeout: int = 15) -> List[Dict[str, Any]]:
    """Pull on-sale items for each configured category. Honest no-op ([]) without an API key
    — never fabricates deal rows. One category's failure is logged and skipped; it never
    blocks the others."""
    if not configured():
        log.info("BESTBUY_API_KEY not set; skipping Best Buy connector (no fake data).")
        return []

    cfg = brain_config.source_config("bestbuy")
    api_key = os.environ["BESTBUY_API_KEY"]
    cats = categories if categories is not None else (cfg.get("categories") or DEFAULT_CATEGORIES)
    if not cats:
        cats = DEFAULT_CATEGORIES
    page_size = page_size or int(cfg.get("pageSize") or DEFAULT_PAGE_SIZE)
    max_pages = max_pages or int(cfg.get("maxPages") or DEFAULT_MAX_PAGES)

    rows: List[Dict[str, Any]] = []
    for cat in cats:
        for page in range(1, max_pages + 1):
            try:
                data = _fetch_page(api_key, cat, page, page_size, timeout)
            except Exception as e:
                log.warning("Best Buy fetch failed (category=%s page=%s): %s",
                           cat, page, redact.redact(str(e)))
                break
            products = data.get("products") or []
            if not products:
                break
            rows.extend(_row_from_product(p) for p in products)
            total_pages = data.get("totalPages", page)
            if page >= total_pages:
                break
    return rows
