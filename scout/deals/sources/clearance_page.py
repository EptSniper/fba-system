"""
scout/deals/sources/clearance_page.py — the generic, polite official-clearance-page fetcher
(TOP100_DEAL_WATCH_PLAN.md T1). ONE fetch per URL per run, and it earns "polite" concretely:

  - robots.txt is checked (and cached per domain for the run) and OBEYED — a disallowed path
    is skipped, never fetched.
  - an honest User-Agent identifies the tool (_feeds.USER_AGENT).
  - conditional GET: prior ETag/Last-Modified (from Supabase source_http_cache, since the
    cloud runner is ephemeral) are sent as If-None-Match / If-Modified-Since; a 304 means
    "nothing changed since last run" and costs almost nothing.

Extraction is DELIBERATELY conservative and HONEST: generic product/price extraction from
arbitrary retail HTML is unreliable, so this only trusts JSON-LD structured data
(<script type="application/ld+json"> Product/Offer objects) — a real published standard many
retailers embed. A page with no parseable JSON-LD yields [] (extraction_confidence is never
fabricated to make a noisy parse look clean); the run's digest reports which clr sources came
back empty so a broken/changed page surfaces instead of silently contributing nothing.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

import redact
import datalake  # V0 raw data lake — archive_clearance_html() never raises / no-ops when off

from . import _feeds

log = logging.getLogger("scout.deals.clearance")

_JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)


def _robots_allows(url: str, cache: Dict[str, RobotFileParser], timeout: int = 10) -> bool:
    """True if robots.txt allows _feeds.USER_AGENT to fetch `url`. Cached per host for the run.

    CRITICAL: robots.txt is fetched via requests WITH A TIMEOUT and the text handed to
    RobotFileParser.parse() — NOT RobotFileParser.read(), which calls urllib with NO timeout
    and will hang the ENTIRE run forever on one slow/unresponsive robots.txt host (this bit
    during first live testing — a single hung robots.txt froze the whole nightly job). Fails
    OPEN on any robots fetch error (can't read the rules -> don't block on them, standard
    crawler behavior); the page fetch itself still honors its own timeout/errors."""
    host = urlparse(url).netloc
    if host not in cache:
        rp = None
        if requests is not None:
            robots_url = f"{urlparse(url).scheme}://{host}/robots.txt"
            try:
                r = requests.get(robots_url, headers={"User-Agent": _feeds.USER_AGENT}, timeout=timeout)
                if r.status_code == 200:
                    rp = RobotFileParser()
                    rp.parse(r.text.splitlines())
                # A 4xx/5xx (incl. 404 "no robots.txt") -> rp stays None -> allow.
            except Exception:
                rp = None  # unreachable/slow robots -> allow (can't read the rules)
        cache[host] = rp
    rp = cache[host]
    if rp is None:
        return True
    try:
        return rp.can_fetch(_feeds.USER_AGENT, url)
    except Exception:
        return True


def _extract_jsonld_products(html: str, url: str, retailer: str) -> List[Dict[str, Any]]:
    """Pull Product/Offer objects out of a page's JSON-LD blocks. Only rows with BOTH a name
    and a numeric price are returned — anything less isn't an actionable deal row."""
    rows: List[Dict[str, Any]] = []
    for block in _JSON_LD_RE.findall(html or ""):
        try:
            data = json.loads(block.strip())
        except Exception:
            continue
        # JSON-LD can be a single object, a list, or a @graph wrapper.
        candidates = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        for obj in candidates:
            if not isinstance(obj, dict):
                continue
            types = obj.get("@type")
            types = types if isinstance(types, list) else [types]
            if "Product" not in types:
                continue
            name = obj.get("name")
            offers = obj.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            price = offers.get("price") if isinstance(offers, dict) else None
            try:
                price = float(price) if price is not None else None
            except (TypeError, ValueError):
                price = None
            if not name or price is None:
                continue
            brand = obj.get("brand")
            if isinstance(brand, dict):
                brand = brand.get("name")
            rows.append({
                "retailer": retailer,
                "source": "clearance_page",
                "source_signal": "clr",
                "sku": str(obj.get("sku")) if obj.get("sku") else None,
                "upc": obj.get("gtin13") or obj.get("gtin12") or None,
                "title_raw": str(name),
                "brand": brand if isinstance(brand, str) else None,
                "price_current": price,
                "price_original": None,
                "discount_pct": None,
                "url": obj.get("url") or url,
                "extraction_confidence": 0.7,  # structured data, but not confirmed on-sale
            })
    return rows


def fetch_page(url: str, retailer: str, robots_cache: Dict[str, RobotFileParser],
               http_cache_get=None, http_cache_set=None, timeout: int = 10) -> Dict[str, Any]:
    """Politely fetch ONE clearance URL and best-effort-extract JSON-LD product rows.

    Returns {"rows": [...], "status": "ok"|"skipped_robots"|"not_modified"|"error"|"empty",
    "status_code": int|None, "detail": ...}. status_code lets the caller distinguish a 403
    (forbidden -> may retire the URL) from a 429 (rate-limited -> transient, retry tomorrow) —
    see scout/deals/source_status.py. http_cache_get/set are injected (db.get_source_http_cache
    / db.set_source_http_cache) so this stays testable and DB-optional."""
    if requests is None:
        return {"rows": [], "status": "error", "status_code": None, "detail": "requests not installed"}
    if not _robots_allows(url, robots_cache):
        log.info("robots.txt disallows %s; skipping", url)
        return {"rows": [], "status": "skipped_robots", "status_code": None, "detail": None}

    headers = {"User-Agent": _feeds.USER_AGENT}
    cached = http_cache_get(url) if http_cache_get else None
    if cached:
        if cached.get("etag"):
            headers["If-None-Match"] = cached["etag"]
        if cached.get("last_modified"):
            headers["If-Modified-Since"] = cached["last_modified"]
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
    except Exception as e:
        log.warning("clearance fetch failed (%s): %s", url, redact.redact(str(e)))
        return {"rows": [], "status": "error", "status_code": None, "detail": redact.redact(str(e))}

    if r.status_code == 304:
        return {"rows": [], "status": "not_modified", "status_code": 304, "detail": None}
    if r.status_code >= 400:
        return {"rows": [], "status": "error", "status_code": r.status_code, "detail": f"HTTP {r.status_code}"}

    if http_cache_set:
        http_cache_set(url, r.headers.get("ETag"), r.headers.get("Last-Modified"))
    rows = _extract_jsonld_products(r.text, url, retailer)
    # Archive the raw HTML body via the confidence/changed gate. changed=None: a 200 doesn't tell
    # us whether the BODY differs from last run (only a 304 proves "unchanged"), so the lake's
    # dedupe manifest is the change detector — identical bodies dedupe to a last_seen bump.
    confidence = max((row.get("extraction_confidence", 0.0) for row in rows), default=0.0)
    datalake.archive_clearance_html(url, r.text, extraction_confidence=confidence, changed=None)
    return {"rows": rows, "status": "ok" if rows else "empty", "status_code": r.status_code, "detail": None}


def collect_for_entries(entries: List[Dict[str, Any]], http_cache_get=None, http_cache_set=None,
                        skip_urls=None, timeout: int = 10) -> Dict[str, Any]:
    """Fetch every entry's clr URLs, EXCEPT any in skip_urls (URLs already retired to
    sd-rss-only — the store's Slickdeals feed covers them, so re-fetching would only burn a
    doomed request). Returns {"rows": [...], "results": [{url, retailer, has_sd_rss, status,
    status_code}, ...], "skipped": [urls]} — run_watch turns `results` into source_status
    transitions and the (filtered) digest broken-list."""
    from .. import registry

    skip = set(skip_urls or ())
    robots_cache: Dict[str, RobotFileParser] = {}
    all_rows: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []
    skipped: List[str] = []
    for entry in entries:
        has_sd_rss = bool(registry.detect_args(entry, "sd-rss"))
        for url in registry.detect_args(entry, "clr"):
            if url in skip:
                skipped.append(url)
                continue
            result = fetch_page(url, entry.get("name", "unknown"), robots_cache,
                                http_cache_get=http_cache_get, http_cache_set=http_cache_set,
                                timeout=timeout)
            all_rows.extend(result["rows"])
            results.append({
                "url": url, "retailer": entry.get("name", "unknown"), "has_sd_rss": has_sd_rss,
                "status": result["status"], "status_code": result.get("status_code"),
                "detail": result.get("detail"),
            })
    return {"rows": all_rows, "results": results, "skipped": skipped}
