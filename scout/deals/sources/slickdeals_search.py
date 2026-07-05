"""
scout/deals/sources/slickdeals_search.py — the per-store Slickdeals search-RSS adapter
(TOP100_DEAL_WATCH_PLAN.md T1, the workhorse). The registry's verified pattern
(newsearch.php?...&rss=1&q=<store>) turns one mechanism into coverage of every store that has
a `sd-rss:<query>` detect code — community-vetted deals, no scraping.

Generic + registry-driven: it is handed registry entries, reads each one's sd-rss query arg,
fetches that store's search feed, and tags every resulting row with the store as its retailer
(a per-store feed already KNOWS the retailer, so no guessing needed). One polite request per
store per run.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

from .. import normalize
from . import _feeds

# The registry documents this exact verified pattern (aggregates[1].urlPattern). Kept here as
# the single format string the adapter fills so a Slickdeals URL-shape change is a one-line fix.
SEARCH_URL = "https://slickdeals.net/newsearch.php?searcharea=deals&searchin=first&rss=1&q={query}"

# Fetch different stores' feeds concurrently to stay under the run's ~5-min budget. This is
# still POLITE: each store gets exactly ONE request (concurrency is ACROSS stores, never
# repeated requests to one) — the "1 req/store/run" rule is about not hammering a single store,
# which this preserves. Modest pool so we don't open a flood of sockets at once.
MAX_WORKERS = 6


def collect_for_entries(entries: List[Dict[str, Any]], timeout: int = 15) -> List[Dict[str, Any]]:
    """One deals-table row per item across every entry's sd-rss query. `entries` are registry
    entries (already tier-filtered / AVOID-included-as-signal by the caller). An entry with no
    sd-rss detect arg contributes nothing; a failed feed contributes nothing (never fabricated).
    Import registry lazily to avoid a package import cycle (sources is a subpackage of deals)."""
    from .. import registry

    # Flatten to (retailer_name, query) fetch jobs, so one entry with two queries is two jobs.
    jobs = [(entry.get("name"), query)
            for entry in entries
            for query in registry.detect_args(entry, "sd-rss")]
    if not jobs:
        return []

    def _fetch(job):
        retailer, query = job
        items = _feeds.fetch_rss(SEARCH_URL.format(query=query), timeout=timeout)
        return [normalize.normalize_rss_item(
            title=it["title"], url=it.get("link"), source="slickdeals",
            source_signal="sd-rss", retailer_hint=retailer) for it in items]

    rows: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(jobs))) as pool:
        for result in pool.map(_fetch, jobs):
            rows.extend(result)
    return rows
