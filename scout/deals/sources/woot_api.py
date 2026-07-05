"""
scout/deals/sources/woot_api.py — Woot official API adapter (TOP100_DEAL_WATCH_PLAN.md T1).
Woot is Amazon-owned; its closeouts are a clean, official, free API signal. Key-gated:
requires WOOT_API_KEY (from developer.woot.com) — absent -> honest no-op ([]), never fakes
rows, exactly like bestbuy.py.

UNVERIFIED until a real key exists: Woot's API shape (endpoint, header name, response fields)
is implemented from its public developer docs but has NOT been exercised against a live key —
same honest caveat bestbuy.py carries. Confirm and adjust the field mapping on first real run.
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
import datalake  # V0 raw data lake — archive() never raises and no-ops when disabled/absent

log = logging.getLogger("scout.deals.woot")

# Woot's developer API. The "Clearance" feed is the OA-relevant one; "All" is the firehose.
FEED_URL = "https://developer.woot.com/feed/{feed}"
DEFAULT_FEED = "Clearance"


def configured() -> bool:
    return bool(os.getenv("WOOT_API_KEY")) and requests is not None


def _row_from_item(item: Dict[str, Any]) -> Dict[str, Any]:
    sale = item.get("SalePrice")
    listp = item.get("ListPrice")
    discount_pct = round((1 - sale / listp) * 100, 1) if sale and listp and listp > 0 else None
    return {
        "retailer": "Woot",
        "source": "woot",
        "source_signal": "woot",
        "sku": str(item["OfferId"]) if item.get("OfferId") is not None else None,
        "upc": None,
        "title_raw": item.get("Title") or "",
        "brand": None,
        "price_current": sale,
        "price_original": listp,
        "discount_pct": discount_pct,
        "url": item.get("Url"),
        "extraction_confidence": 0.95,  # structured official API, not a scraped guess
    }


def collect(feed: Optional[str] = None, timeout: int = 15) -> List[Dict[str, Any]]:
    """On-sale/closeout items from the Woot feed. Honest no-op ([]) without WOOT_API_KEY. A
    failure is logged (key redacted — Woot takes the key as an x-api-key header, but redact
    anyway) and degrades to []."""
    if not configured():
        log.info("WOOT_API_KEY not set; skipping Woot connector (no fake data).")
        return []
    url = FEED_URL.format(feed=feed or DEFAULT_FEED)
    try:
        r = requests.get(url, headers={"x-api-key": os.environ["WOOT_API_KEY"]}, timeout=timeout)
        r.raise_for_status()
        # Archive the RAW API body before normalization; keyed by feed URL (dedupes unchanged).
        datalake.archive("deals_woot", url, "api", r.text)
        data = r.json()
    except Exception as e:
        log.warning("Woot fetch failed: %s", redact.redact(str(e)))
        return []
    items = data.get("Items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    return [_row_from_item(it) for it in items if isinstance(it, dict)]
