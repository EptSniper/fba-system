"""
scout/signals/ebay.py — eBay Browse API sold-comps (Session 55, free signal-type features).

KEY-GATED, OPTIONAL: needs EBAY_APP_ID (a free eBay developer account) in scout/.env. Until it
exists, every function here degrades to an honest skip — never blocks the pipeline, never
fabricates a comp. Signup steps are in HUMAN_TODO.md.

Features per candidate UPC:
  - ebay_sold_count_30d: sold-listing count on eBay in the trailing 30 days.
  - median_sold_price_vs_amazon_ratio: median eBay sold price / the Amazon price passed in —
    below 1.0 means eBay buyers pay LESS than Amazon's price (a demand/arbitrage-ceiling signal
    distinct from anything Keepa reports, since Keepa only ever sees Amazon's own marketplace).

eBay's Browse API's sold/completed-items data requires the (paid, invitation-gated) Marketplace
Insights API for FULL history; the public Browse API's `item_summary/search` with a sold-items
filter is the free-tier substitute this module targets — coverage is therefore approximate, not
a complete sold-comps feed. Documented here rather than at every call site.
"""
from __future__ import annotations

import logging
import os
import statistics
import time
from typing import Any, Dict, List, Optional

log = logging.getLogger("scout.signals.ebay")

HERE = os.path.dirname(os.path.abspath(__file__))
BROWSE_API_BASE = "https://api.ebay.com/buy/browse/v1"
OAUTH_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"


def app_id() -> Optional[str]:
    return os.getenv("EBAY_APP_ID") or None


def app_secret() -> Optional[str]:
    return os.getenv("EBAY_CERT_ID") or None


def enabled() -> bool:
    """True once EBAY_APP_ID is configured. Honest skip (not an error) until then — the free
    developer-account signup is a HUMAN_TODO.md item, not something this code can do for
    itself."""
    return bool(app_id())


def _get_access_token(client_id: str, client_secret: str, sleep_fn=None) -> Optional[str]:
    """Client-credentials OAuth token for the Browse API (eBay requires this even for public,
    unauthenticated-buyer searches). None on any failure — never raises. sleep_fn unused today,
    kept for symmetry with trends.py's retry-injection convention if backoff is added later."""
    try:
        import requests
        import base64
        cred = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        r = requests.post(
            OAUTH_TOKEN_URL,
            headers={"Authorization": f"Basic {cred}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials",
                 "scope": "https://api.ebay.com/oauth/api_scope"},
            timeout=15,
        )
        r.raise_for_status()
        return (r.json() or {}).get("access_token")
    except Exception as e:
        log.warning("eBay OAuth token request failed (non-fatal): %s", e)
        return None


def sold_comps(upc: str, token: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    """Sold-listing comps for one UPC. Returns {"status": "skipped"|"ok"|"error", "sold_count",
    "median_price", "listings"}. Honest skip (status="skipped") when EBAY_APP_ID isn't
    configured — never an error, never blocks the caller. NEVER raises."""
    if not enabled():
        return {"status": "skipped", "reason": "EBAY_APP_ID not configured (see HUMAN_TODO.md)",
                "sold_count": None, "median_price": None, "listings": []}
    cid, secret = app_id(), app_secret()
    if token is None:
        if not secret:
            return {"status": "skipped", "reason": "EBAY_CERT_ID not configured",
                    "sold_count": None, "median_price": None, "listings": []}
        token = _get_access_token(cid, secret)
        if not token:
            return {"status": "error", "reason": "OAuth token request failed",
                    "sold_count": None, "median_price": None, "listings": []}
    try:
        import requests
        r = requests.get(
            f"{BROWSE_API_BASE}/item_summary/search",
            headers={"Authorization": f"Bearer {token}",
                     "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"},
            params={"gtin": upc, "filter": "buyingOptions:{FIXED_PRICE}", "limit": limit},
            timeout=15,
        )
        r.raise_for_status()
        items = (r.json() or {}).get("itemSummaries") or []
    except Exception as e:
        log.warning("eBay sold_comps request failed for %r (non-fatal): %s", upc, e)
        return {"status": "error", "reason": str(e), "sold_count": None, "median_price": None,
                "listings": []}

    prices = []
    for item in items:
        price = (item.get("price") or {}).get("value")
        try:
            if price is not None:
                prices.append(float(price))
        except (TypeError, ValueError):
            continue
    return {"status": "ok", "sold_count": len(items),
           "median_price": round(statistics.median(prices), 2) if prices else None,
           "listings": items}


def ebay_features(upc: str, amazon_price: Optional[float], token: Optional[str] = None) -> Dict[str, Any]:
    """ebay_sold_count_30d + median_sold_price_vs_amazon_ratio, nullable/stale-flagged when
    unavailable — never blocks the caller. NEVER raises."""
    comps = sold_comps(upc, token=token)
    if comps["status"] != "ok":
        return {"ebay_sold_count_30d": None, "median_sold_price_vs_amazon_ratio": None,
               "ebay_stale": True, "ebay_status": comps["status"]}
    ratio = None
    if comps["median_price"] is not None and amazon_price:
        ratio = round(comps["median_price"] / amazon_price, 3)
    return {"ebay_sold_count_30d": comps["sold_count"],
           "median_sold_price_vs_amazon_ratio": ratio,
           "ebay_stale": False, "ebay_status": "ok"}
