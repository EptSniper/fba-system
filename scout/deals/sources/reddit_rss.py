"""
scout/deals/sources/reddit_rss.py — Reddit deal-subreddit RSS/Atom adapter
(TOP100_DEAL_WATCH_PLAN.md T1). Cross-source confirmation signal alongside Slickdeals: the
same product front-paged on both is a stronger buy signal than either alone.

Reddit's .rss endpoints are Atom (handled by _feeds.fetch_rss's namespace-agnostic parse) and
REQUIRE a descriptive User-Agent (a generic one gets a 429/403) — _feeds.USER_AGENT supplies
one. Feed URLs come from the registry's `aggregates` list (the entry named "Reddit deals
subs"); the retailer is guessed from each post title against the registry's store names, since
a subreddit post can be about any store.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .. import normalize
from . import _feeds


def collect(feed_urls: List[str], known_retailers: List[str], timeout: int = 15) -> List[Dict[str, Any]]:
    """One deals-table row per Reddit post across every feed URL. A failed feed contributes
    nothing. known_retailers (the registry's store names) drives retailer-guessing from the
    post title."""
    rows: List[Dict[str, Any]] = []
    for url in feed_urls:
        for it in _feeds.fetch_rss(url, timeout=timeout):
            rows.append(normalize.normalize_rss_item(
                title=it["title"], url=it.get("link"), source="reddit",
                source_signal="reddit", known_retailers=known_retailers,
            ))
    return rows
