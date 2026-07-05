"""
scout/deals/sources/dealnews_rss.py — DealNews editor-curated RSS adapter
(TOP100_DEAL_WATCH_PLAN.md T1). Spans most Tier 1-2 stores with a human-curated eye, a useful
complement to Slickdeals's crowd firehose. Feed URLs come from the registry's `aggregates`
entry named "DealNews category feeds" (flagged VERIFY there — confirm the exact feed URLs on
first wire-up; a VERIFY-flagged aggregate that returns nothing is reported, never silently
dropped).
"""
from __future__ import annotations

from typing import Any, Dict, List

from .. import normalize
from . import _feeds


def collect(feed_urls: List[str], known_retailers: List[str], timeout: int = 15) -> List[Dict[str, Any]]:
    """One deals-table row per item across every DealNews feed URL. A failed/empty feed
    contributes nothing (never fabricated); retailer guessed from the title against the
    registry store names."""
    rows: List[Dict[str, Any]] = []
    for url in feed_urls:
        for it in _feeds.fetch_rss(url, timeout=timeout):
            rows.append(normalize.normalize_rss_item(
                title=it["title"], url=it.get("link"), source="dealnews",
                source_signal="dealnews", known_retailers=known_retailers,
            ))
    return rows
