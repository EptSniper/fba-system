"""
scout/deals_firehose.py — the Keepa /deal endpoint as a brand-agnostic breadth firehose
(learning.sampling, Session 55).

Mehmet's directive: DATA collection for the training corpus must be brand-AGNOSTIC and as broad
as the token budget allows; brand lists (brands.py) stay ONLY for buy-candidate discovery and
purchase gating — untouched by this module. Product Finder is REQUEST_REJECTED on this Keepa Pro
plan (keepa_client.find_candidates, Session 51's live confirmation). Keepa's /deal endpoint
("recently changed products matching criteria") is a SEPARATE, cheaper endpoint the Pro plan CAN
reach: ~5 tokens per page of up to 150 deals — an order of magnitude cheaper per ASIN than the
10-token/term search fallback, and inherently diverse (deals span every category Amazon has, not
just our friendly-brand seeds).

Every ASIN a deal page returns is candidate training data, tagged sample_source="dealfeed"
downstream (scout/backtest.py owns turning an ASIN into an actual backtest_rows training row —
this module only harvests the raw ASIN list + archives the raw response).

CATEGORY ROTATION: Keepa's deal endpoint filters by numeric Amazon browse-node ids
(`includeCategories`), not this project's short internal keys (toys/kitchen/pet/...). Root ids
are STABLE (they're Amazon's own browse nodes) but must be resolved once via a live
`api.category_lookup(0)` call — a small flat cost, UNVERIFIED until a real dispatch runs (this
account was in token debt for most of Session 55; see AI_COLLABORATION_JOURNAL.md). The resolved
map is cached to disk so it's a ONE-TIME cost, not per-run. Until that cache exists, harvest()
degrades to an UNFILTERED pull — still broad and brand-agnostic (Keepa's raw deal feed already
spans every category) — rather than guessing numeric ids and risking a silently-wrong filter.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable, Dict, List, Optional

import config
import datalake
import keepa_client

log = logging.getLogger("scout.deals_firehose")

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN_PATH = os.path.join(HERE, "..", "learning-hub", "data", "ai-brain.json")
CACHE_PATH = os.path.join(HERE, ".cache", "keepa_category_ids.json")

DEALS_PAGE_TOKENS = keepa_client.DEALS_PAGE_TOKENS
DEFAULT_PAGES_PER_RUN = 3   # within Mehmet's 2-4 pages/day spec


def sampling_config() -> Dict[str, Any]:
    """learning.sampling from the brain (categories/priceBands/bsrStrata/tags) — single source of
    truth, same convention as every other brain-driven knob in this project. {} if unavailable."""
    try:
        with open(BRAIN_PATH, encoding="utf-8") as f:
            brain = json.load(f) or {}
        return (brain.get("learning") or {}).get("sampling") or {}
    except Exception:
        return {}


def _load_category_id_cache() -> Dict[str, int]:
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save_category_id_cache(mapping: Dict[str, int]) -> None:
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=2)
    except Exception as e:
        log.warning("category id cache save failed (non-fatal): %s", e)


def resolve_category_ids(api, categories: List[str], lookup_fn: Optional[Callable] = None) -> Dict[str, int]:
    """category key -> Keepa root catId, resolved live ONCE then cached to disk (root ids are
    stable Amazon browse nodes, so repeat runs never re-spend on this). Returns whatever subset
    resolves; an unmapped category is left OUT of the rotation, never guessed at. Never raises."""
    cached = _load_category_id_cache()
    if cached and all(c in cached for c in categories):
        return cached
    if lookup_fn is None:
        lookup_fn = api.category_lookup
    try:
        roots = lookup_fn(0, domain=config.KEEPA_DOMAIN) or {}
    except Exception as e:
        log.warning("category_lookup failed (non-fatal, using whatever was cached): %s", e)
        return cached
    by_name: Dict[str, int] = {}
    entries = roots.values() if isinstance(roots, dict) else (roots or [])
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = (entry.get("name") or entry.get("contextFreeName") or "").strip().lower()
        cat_id = entry.get("catId")
        if name and isinstance(cat_id, int):
            by_name[name] = cat_id
    # keepa_client._CATEGORY_MAP maps Keepa's real root names -> our short keys; invert it to find
    # each configured category's expected Keepa root name, then its resolved id.
    inverse: Dict[str, str] = {}
    for keepa_name, short_key in keepa_client._CATEGORY_MAP.items():
        inverse.setdefault(short_key, keepa_name)
    resolved = dict(cached)
    for cat in categories:
        keepa_name = inverse.get(cat)
        if keepa_name and keepa_name in by_name:
            resolved[cat] = by_name[keepa_name]
    _save_category_id_cache(resolved)
    return resolved


def fetch_deal_page(api, category: Optional[str] = None, category_id: Optional[int] = None,
                    page: int = 0, wait: bool = True) -> Dict[str, Any]:
    """One /deal page (<=150 deals), guarded so its flat DEALS_PAGE_TOKENS cost never overdraws
    the bank. wait: True (default) lets the keepa lib drip-pace against the token bucket like
    every other endpoint in this project; scout/collect_hourly.py's burst collector passes
    wait=False (DATA_ENGINE_PLAN.md's "never block on a refill" rule) — the guard above already
    means this call is only attempted when the bank covers it, so wait=False rarely matters in
    practice, but it keeps this endpoint consistent with keepa_client.py's own wait= convention
    rather than being the one silent exception to it. Returns {"status", "asins": [...],
    "tokens_spent", "category", "page"}. NEVER raises — a rejected/failed call degrades to an
    honest empty result."""
    ok = keepa_client._guard_flat(api, DEALS_PAGE_TOKENS, "deals firehose page")
    if not ok:
        return {"status": "skipped", "reason": "insufficient bank", "asins": [],
                "tokens_spent": 0, "category": category, "page": page}
    deal_parms: Dict[str, Any] = {"page": page, "domainId": 1, "priceTypes": [0]}
    if category_id is not None:
        deal_parms["includeCategories"] = [category_id]
    before = keepa_client._tokens_consumed(api)
    try:
        deals = api.deals(deal_parms, domain=config.KEEPA_DOMAIN, wait=wait) or {}
    except Exception as e:
        log.warning("deals() page failed (non-fatal): %s", e)
        return {"status": "error", "reason": str(e), "asins": [], "tokens_spent": 0,
                "category": category, "page": page}
    after = keepa_client._tokens_consumed(api)
    spent = keepa_client._delta(before, after)
    rows = deals.get("dr") or [] if isinstance(deals, dict) else []
    asins = [d.get("asin") for d in rows if isinstance(d, dict) and d.get("asin")]
    datalake.archive("keepa", f"deals:{category or 'all'}:{page}", "deal_page",
                     {"category": category, "page": page, "asins": asins},
                     tokens_consumed=spent if spent is not None else DEALS_PAGE_TOKENS)
    return {"status": "ok", "asins": asins,
            "tokens_spent": spent if spent is not None else DEALS_PAGE_TOKENS,
            "category": category, "page": page}


def harvest(api, pages: Optional[int] = None, categories: Optional[List[str]] = None,
           resolve_fn: Optional[Callable] = None, wait: bool = True) -> Dict[str, Any]:
    """The firehose entry point: pull `pages` deal pages (default DEFAULT_PAGES_PER_RUN, within
    Mehmet's 2-4/day spec), ROTATING through the configured categories when their Keepa root id
    is resolvable, falling back to an unfiltered pull for any that aren't yet. Returns
    {"status", "asins": [{"asin","category"}], "pages_pulled", "tokens_spent", "by_category",
    "categories_resolved"}. NEVER raises — every ASIN here is a dealfeed candidate, brand-agnostic
    by construction (no brand seed is ever consulted)."""
    cfg = sampling_config()
    categories = categories if categories is not None else (cfg.get("categories") or [])
    pages = pages if pages is not None else DEFAULT_PAGES_PER_RUN

    id_map: Dict[str, int] = {}
    if categories:
        try:
            id_map = (resolve_fn or resolve_category_ids)(api, categories)
        except Exception as e:
            log.warning("category id resolution failed (non-fatal, unfiltered pull): %s", e)

    out: List[Dict[str, Any]] = []
    seen = set()
    total_spent = 0
    by_category: Dict[str, int] = {}
    pulled = 0
    for i in range(max(0, pages)):
        if categories:
            cat = categories[i % len(categories)]
            cat_id = id_map.get(cat)
        else:
            cat, cat_id = None, None
        page = fetch_deal_page(api, category=cat, category_id=cat_id, page=0, wait=wait)
        pulled += 1
        total_spent += page.get("tokens_spent") or 0
        if page.get("status") == "skipped":
            break  # bank ran dry mid-run — stop, don't keep attempting spends that can't land
        for a in page.get("asins") or []:
            if a not in seen:
                seen.add(a)
                out.append({"asin": a, "category": cat})
                key = cat or "unfiltered"
                by_category[key] = by_category.get(key, 0) + 1
    return {"status": "ok", "asins": out, "pages_pulled": pulled, "tokens_spent": total_spent,
            "by_category": by_category, "categories_resolved": sorted(id_map.keys())}
