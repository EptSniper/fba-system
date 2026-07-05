"""
scout/deals/sources/_feeds.py — shared polite RSS/Atom fetch for the registry-driven deal
adapters (TOP100_DEAL_WATCH_PLAN.md T1). One User-Agent, one parser, one never-raises
contract, so slickdeals_search / reddit_rss / dealnews_rss don't each reimplement feed I/O.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

import redact
import datalake  # V0 raw data lake — archive() never raises and no-ops when disabled/absent

log = logging.getLogger("scout.deals.feeds")

# Honest identification per the build plan's ToS note (prefer official feeds; identify any
# automated agent honestly). A personal, single-operator research tool — not a bot farm.
USER_AGENT = "FBA-personal-deal-watch/1.0 (personal OA sourcing research)"


def _local(tag: str) -> str:
    """Strip an XML namespace ('{http://www.w3.org/2005/Atom}entry' -> 'entry') so RSS and
    Atom (which namespaces everything) can be walked with the same tag names."""
    return tag.rsplit("}", 1)[-1].lower()


def fetch_rss(url: str, timeout: int = 15,
              extra_headers: Optional[Dict[str, str]] = None) -> List[Dict[str, str]]:
    """Fetch + parse one RSS or Atom feed into raw {title, link} dicts. NEVER raises — a dead
    feed logs a warning and returns [] so one broken source never breaks a collection run
    (matching every other connector's degrade-to-empty contract)."""
    if requests is None:
        log.warning("requests not installed; skipping feed %s", url)
        return []
    headers = {"User-Agent": USER_AGENT}
    if extra_headers:
        headers.update(extra_headers)
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        # Archive the RAW feed body before parsing (deals/sources/* archive raw-before-normalize).
        # Keyed by URL so an unchanged feed dedupes to a cheap last_seen bump. Never breaks I/O.
        datalake.archive("deals_rss", url, "rss", r.text)
        root = ET.fromstring(r.content)
    except Exception as e:
        log.warning("feed fetch/parse failed (%s): %s", url, redact.redact(str(e)))
        return []

    items: List[Dict[str, str]] = []
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):  # RSS item / Atom entry
            continue
        title, link = "", ""
        for child in el:
            name = _local(child.tag)
            if name == "title" and child.text:
                title = child.text.strip()
            elif name == "link":
                # RSS: <link>url</link>; Atom: <link href="url"/> (prefer rel="alternate").
                if child.text and child.text.strip():
                    link = child.text.strip()
                elif child.get("href") and (not link or child.get("rel") in (None, "alternate")):
                    link = child.get("href").strip()
        if title:
            items.append({"title": title, "link": link})
    return items
