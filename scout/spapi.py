"""
spapi.py — Amazon SP-API: "am I allowed?" + exact fees (System Blueprint Prompt G3).

A self-authorized PRIVATE developer app (System Blueprint §2/§3 — a solo Professional-plan
seller can register one directly in Seller Central, no company/review required, typically days
not months). Credentials (LWA client id/secret + refresh token) are server-side only:
SP_API_LWA_CLIENT_ID / SP_API_LWA_CLIENT_SECRET / SP_API_REFRESH_TOKEN in scout/.env
(registry copy in API_KEYS.env). NEVER exposed to a browser.

HONEST STATUS: this module is fully built and unit-tested with MOCKED responses (see
tests/test_spapi.py), but it has never made a real call — as of this writing every SP_API_*
credential in API_KEYS.env is still a placeholder. Treat every live-network code path here as
UNVERIFIED against the actual API until real credentials exist and a call succeeds; `configured()`
gates every function so nothing here can silently claim eligibility it never checked.

Endpoints wrapped (all ordinary seller roles, no restricted-role application needed):
  - Listings Restrictions API `getListingsRestrictions` (5 req/s) -> ALLOWED / APPROVAL_REQUIRED
    / NOT_ELIGIBLE (+ approval links)
  - Product Fees API `getMyFeesEstimateForASIN` (1 req/s) -> referral + FBA fee estimate
  - Catalog Items API UPC->ASIN lookup (2 req/s)
Rate limiting: a minimal single-process token-bucket per endpoint — this project runs a
single-threaded drip scan, not concurrent workers, so no cross-process coordination is needed.
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
SPAPI_BASE = os.getenv("SP_API_BASE_URL", "https://sellingpartnerapi-na.amazon.com")
MARKETPLACE_ID = os.getenv("SP_API_MARKETPLACE_ID", "ATVPDKIKX0DER")  # Amazon.com (US)

CLIENT_ID = os.getenv("SP_API_LWA_CLIENT_ID") or None
CLIENT_SECRET = os.getenv("SP_API_LWA_CLIENT_SECRET") or None
REFRESH_TOKEN = os.getenv("SP_API_REFRESH_TOKEN") or None


def configured() -> bool:
    return bool(CLIENT_ID and CLIENT_SECRET and REFRESH_TOKEN and requests)


class _TokenBucket:
    """Sleeps just enough to stay under `rate_per_sec` requests/second. Not thread-safe by
    design — this project's scan is single-threaded."""

    def __init__(self, rate_per_sec: float):
        self.min_interval = 1.0 / rate_per_sec
        self._last = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last = time.monotonic()


_LIMITERS = {
    "restrictions": _TokenBucket(5.0),
    "fees": _TokenBucket(1.0),
    "catalog": _TokenBucket(2.0),
}

_access_token: Optional[str] = None
_access_token_expires: float = 0.0


def _refresh_access_token() -> str:
    """LWA access tokens last ~1h; cached and only refreshed when close to expiry."""
    global _access_token, _access_token_expires
    if _access_token and time.time() < _access_token_expires - 60:
        return _access_token
    if not configured():
        raise RuntimeError("SP-API not configured — set SP_API_LWA_CLIENT_ID/SECRET and "
                           "SP_API_REFRESH_TOKEN (server-side .env only, never in the browser).")
    r = requests.post(LWA_TOKEN_URL, data={
        "grant_type": "refresh_token", "refresh_token": REFRESH_TOKEN,
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
    }, timeout=15)
    r.raise_for_status()
    body = r.json()
    _access_token = body["access_token"]
    _access_token_expires = time.time() + body.get("expires_in", 3600)
    return _access_token


def _headers() -> Dict[str, str]:
    return {"x-amz-access-token": _refresh_access_token(), "Content-Type": "application/json"}


def _get(path: str, params: Dict[str, Any], limiter_key: str) -> Dict[str, Any]:
    _LIMITERS[limiter_key].wait()
    r = requests.get(f"{SPAPI_BASE}{path}", headers=_headers(), params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def get_listings_restrictions(asin: str, condition: str = "new_new",
                              seller_id: Optional[str] = None,
                              use_cache: bool = True) -> Dict[str, Any]:
    """ALLOWED / APPROVAL_REQUIRED / NOT_ELIGIBLE (+ reasons/links), or NOT_CONFIGURED —
    NEVER claims eligibility it didn't verify. Checks the 7-day Supabase cache first (account-
    specific, slow-changing) unless use_cache=False; degrades to a live check if the cache is
    unavailable (db.py handles that gracefully — see db.get_cached_restriction)."""
    if not configured():
        return {"status": "NOT_CONFIGURED", "asin": asin,
                "message": "SP-API credentials not set — eligibility unverified."}

    if use_cache:
        import db
        cached = db.get_cached_restriction(asin)
        if cached:
            return {"status": cached.get("status"), "asin": asin,
                    "reasons": cached.get("reasons") or [], "links": cached.get("links") or [],
                    "cached": True}

    seller_id = seller_id or os.getenv("SP_API_SELLER_ID")
    data = _get("/listings/2021-08-01/restrictions", {
        "asin": asin, "conditionType": condition, "sellerId": seller_id,
        "marketplaceIds": MARKETPLACE_ID,
    }, "restrictions")
    restrictions = data.get("restrictions") or []

    if not restrictions:
        result = {"status": "ALLOWED", "asin": asin, "reasons": [], "links": []}
    else:
        reasons, links = [], []
        for r in restrictions:
            for c in r.get("reasons", []):
                if c.get("message"):
                    reasons.append(c["message"])
                for link in c.get("links", []) or []:
                    if link.get("resource"):
                        links.append(link["resource"])
        # An approval path (a link to apply) exists -> APPROVAL_REQUIRED; no path -> hard NOT_ELIGIBLE.
        status = "APPROVAL_REQUIRED" if links else "NOT_ELIGIBLE"
        result = {"status": status, "asin": asin, "reasons": reasons, "links": links}

    if use_cache:
        import db
        db.cache_restriction(asin, result)
    return result


def get_fees_estimate(asin: str, price: float, is_fba: bool = True) -> Dict[str, Any]:
    """Amazon's own referral + FBA fee estimate at a real price point, or `available: False`
    with a reason — callers must keep the rule-based estimate as an explicit fallback and
    record which source was actually used (honest data flow, never silently swapped)."""
    if not configured():
        return {"available": False, "asin": asin, "reason": "SP-API not configured"}
    body = {
        "FeesEstimateRequest": {
            "MarketplaceId": MARKETPLACE_ID,
            "IsAmazonFulfilled": is_fba,
            "PriceToEstimateFees": {"ListingPrice": {"Amount": price, "CurrencyCode": "USD"}},
            "Identifier": asin,
        }
    }
    _LIMITERS["fees"].wait()
    r = requests.post(f"{SPAPI_BASE}/products/fees/v0/items/{asin}/feesEstimate",
                      headers=_headers(), json=body, timeout=20)
    r.raise_for_status()
    data = r.json()
    result = (data.get("payload") or {}).get("FeesEstimateResult", {})
    estimate = result.get("FeesEstimate", {})
    fee_list = estimate.get("FeeDetailList", [])
    referral = next((f["FeeAmount"]["Amount"] for f in fee_list if f.get("FeeType") == "ReferralFee"), None)
    fba_fee = next((f["FeeAmount"]["Amount"] for f in fee_list if "FBA" in (f.get("FeeType") or "")), None)
    return {"available": True, "asin": asin, "referral_fee": referral, "fba_fee": fba_fee,
           "total_fees": (estimate.get("TotalFeesEstimate") or {}).get("Amount")}


def catalog_lookup_upc(upc: str) -> Dict[str, Any]:
    """UPC -> ASIN via the Catalog Items API, or `available: False` with a reason."""
    if not configured():
        return {"available": False, "upc": upc, "reason": "SP-API not configured"}
    data = _get("/catalog/2022-04-01/items", {
        "marketplaceIds": MARKETPLACE_ID, "identifiers": upc, "identifiersType": "UPC",
    }, "catalog")
    items = data.get("items") or []
    return {"available": True, "upc": upc, "asins": [i.get("asin") for i in items if i.get("asin")]}
