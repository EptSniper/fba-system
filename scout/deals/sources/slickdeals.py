"""
scout/deals/sources/slickdeals.py — Slickdeals RSS connector (Deal Finder Build Plan, Prompt
D1). Official RSS feeds are free and ToS-clean to consume (unlike scraping the site itself).
Crowd-visible, so margins compress fast on anything front-paged — use as signal alongside
Best Buy's cleaner feed, not the sole source.

Config (feed URLs) comes from ai-brain.json's dealFinder.sources.slickdeals.feeds block —
falls back to DEFAULT_FEEDS if the brain has none yet. No API key required.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

import redact

from .. import brain_config

log = logging.getLogger("scout.deals.slickdeals")

# Identifies this as an automated research/sourcing tool, honestly, per the build plan's
# ToS note (prefer official feeds; identify any automated agent honestly).
USER_AGENT = "FBA-OA-DealScout/1.0 (personal sourcing research; +https://slickdeals.net RSS)"

DEFAULT_FEEDS = [
    "https://slickdeals.net/newsearch.php?rss=1&mode=frontpage",
]

_PRICE_RE = re.compile(r'\$(\d[\d,]*\.?\d*)')
_REG_RE = re.compile(r'(?:reg\.?|regularly|originally)\s*\$?(\d[\d,]*\.?\d*)', re.I)

# Checked longest-first isn't necessary here (single-word/short multi-word names, no prefix
# collisions), but keep alphabetical for readability.
_KNOWN_RETAILERS = [
    "Ace Hardware", "Amazon", "Best Buy", "Costco", "CVS", "Grocery Outlet", "Home Depot",
    "Kohl's", "Lowe's", "Sam's Club", "Target", "Walgreens", "Walmart",
]


def _guess_retailer(text: str) -> str:
    for name in _KNOWN_RETAILERS:
        if name.lower() in text.lower():
            return name
    return "unknown"


def _parse_prices(title: str):
    prices = [float(p.replace(",", "")) for p in _PRICE_RE.findall(title)]
    current = prices[0] if prices else None
    reg_match = _REG_RE.search(title)
    if reg_match:
        original = float(reg_match.group(1).replace(",", ""))
    else:
        original = prices[1] if len(prices) > 1 else None
    return current, original


def fetch_feed(url: str, timeout: int = 15) -> List[Dict[str, str]]:
    """Fetch + parse one RSS feed into raw {title, link} dicts. Never raises — a bad feed
    logs a warning and returns [] so one dead feed never breaks the whole collection run."""
    if requests is None:
        log.warning("requests not installed; skipping Slickdeals feed %s", url)
        return []
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception as e:
        log.warning("Slickdeals feed fetch/parse failed (%s): %s", url, redact.redact(str(e)))
        return []

    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if title:
            items.append({"title": title, "link": link})
    return items


def normalize_items(items: List[Dict[str, str]], source: str = "slickdeals") -> List[Dict[str, Any]]:
    """Raw RSS items -> deals-table rows (unmatched, sku/upc unknown — Slickdeals rarely
    states either; the matcher's title path (Prompt D2) is what resolves these)."""
    rows = []
    for it in items:
        title = it["title"]
        current, original = _parse_prices(title)
        discount_pct = None
        if current is not None and original and original > 0:
            discount_pct = round((1 - current / original) * 100, 1)
        rows.append({
            "retailer": _guess_retailer(title),
            "source": source,
            "sku": None,
            "upc": None,
            "title_raw": title,
            "brand": None,
            "price_current": current,
            "price_original": original,
            "discount_pct": discount_pct,
            "url": it.get("link"),
        })
    return rows


def collect(feeds: Optional[List[str]] = None, timeout: int = 15) -> List[Dict[str, Any]]:
    """Fetch + normalize every configured feed. A feed with no items or a fetch failure
    contributes nothing (never fabricated) — an empty return means "nothing new this poll",
    not an error."""
    feeds = feeds if feeds is not None else (brain_config.source_config("slickdeals").get("feeds") or DEFAULT_FEEDS)
    rows: List[Dict[str, Any]] = []
    for url in feeds:
        rows.extend(normalize_items(fetch_feed(url, timeout=timeout)))
    return rows
