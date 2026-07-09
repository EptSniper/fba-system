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


# Supabase Storage persistence — mirrors scout/backtest.py's proven _fetch_remote_state() /
# _upload_remote_state() pattern exactly (audit finding, 2026-07-08 live incident): the on-disk
# CACHE_PATH never survives a GitHub Actions runner (fresh checkout every run, no persistent
# disk), so this cache — meant to be a ONE-TIME resolution cost — silently re-paid its live
# category_lookup() cost on every single hourly burst. Same bucket ("models") as backtest's
# state, different path.
_CATEGORY_CACHE_BUCKET = "models"
_CATEGORY_CACHE_STORAGE_PATH = "backtest/category_ids.json"


def _category_cache_storage_headers() -> Dict[str, str]:
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def _fetch_remote_category_cache() -> Dict[str, int]:
    """{} on any failure/missing env — never raises; a missing remote cache just means the next
    resolve_category_ids() call pays the (guarded, flat, cheap) live lookup cost once."""
    try:
        import requests
        supa = os.getenv("SUPABASE_URL", "").rstrip("/")
        if not supa or not os.getenv("SUPABASE_SERVICE_KEY"):
            return {}
        r = requests.get(
            f"{supa}/storage/v1/object/{_CATEGORY_CACHE_BUCKET}/{_CATEGORY_CACHE_STORAGE_PATH}",
            headers=_category_cache_storage_headers(), timeout=15)
        if r.status_code != 200:
            return {}
        return r.json() or {}
    except Exception as e:
        log.warning("category id remote cache fetch failed (non-fatal): %s", e)
        return {}


def _upload_remote_category_cache(mapping: Dict[str, int]) -> bool:
    """Best-effort — never raises. Same bucket/upsert pattern backtest.py's resume state and
    train_ranker.py's fingerprint already use for cross-run persistence on ephemeral runners."""
    try:
        import requests
        supa = os.getenv("SUPABASE_URL", "").rstrip("/")
        if not supa or not os.getenv("SUPABASE_SERVICE_KEY"):
            return False
        r = requests.post(
            f"{supa}/storage/v1/object/{_CATEGORY_CACHE_BUCKET}/{_CATEGORY_CACHE_STORAGE_PATH}",
            headers={**_category_cache_storage_headers(), "x-upsert": "true",
                    "Content-Type": "application/json"},
            data=json.dumps(mapping).encode("utf-8"), timeout=30,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        log.warning("category id remote cache upload failed (non-fatal): %s", e)
        return False


def _load_category_id_cache() -> Dict[str, int]:
    """Prefers the local file (fast path, unchanged for local dev / any persistent host) and
    falls back to the Supabase-Storage-backed copy when the local file is empty/missing — see
    _fetch_remote_category_cache()'s docstring for why that fallback exists."""
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            local = json.load(f) or {}
        if local:
            return local
    except Exception:
        pass
    return _fetch_remote_category_cache()


def _save_category_id_cache(mapping: Dict[str, int]) -> None:
    """Persists BOTH locally (fast local-dev path, unchanged) AND to Supabase Storage, so the
    cache actually survives an ephemeral GitHub Actions runner."""
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=2)
    except Exception as e:
        log.warning("category id cache save failed (non-fatal): %s", e)
    _upload_remote_category_cache(mapping)


_CURSOR_STORAGE_PATH = "backtest/dealfeed_cursor.json"


def _fetch_remote_cursor() -> int:
    """The rotation cursor (see harvest()'s docstring) — persisted the same way the category-id
    cache is, since GitHub Actions has no disk between runs. 0 (start of the list) on any
    failure/missing env — never raises."""
    try:
        import requests
        supa = os.getenv("SUPABASE_URL", "").rstrip("/")
        if not supa or not os.getenv("SUPABASE_SERVICE_KEY"):
            return 0
        r = requests.get(f"{supa}/storage/v1/object/{_CATEGORY_CACHE_BUCKET}/{_CURSOR_STORAGE_PATH}",
                         headers=_category_cache_storage_headers(), timeout=15)
        if r.status_code != 200:
            return 0
        v = (r.json() or {}).get("cursor")
        return int(v) if isinstance(v, (int, float)) else 0
    except Exception as e:
        log.warning("dealfeed rotation cursor fetch failed (non-fatal, restarting at 0): %s", e)
        return 0


def _upload_remote_cursor(cursor: int) -> bool:
    """Best-effort — never raises."""
    try:
        import requests
        supa = os.getenv("SUPABASE_URL", "").rstrip("/")
        if not supa or not os.getenv("SUPABASE_SERVICE_KEY"):
            return False
        r = requests.post(
            f"{supa}/storage/v1/object/{_CATEGORY_CACHE_BUCKET}/{_CURSOR_STORAGE_PATH}",
            headers={**_category_cache_storage_headers(), "x-upsert": "true",
                    "Content-Type": "application/json"},
            data=json.dumps({"cursor": cursor}).encode("utf-8"), timeout=30,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        log.warning("dealfeed rotation cursor upload failed (non-fatal): %s", e)
        return False


def resolve_category_ids(api, categories: List[str], lookup_fn: Optional[Callable] = None,
                         wait: bool = True) -> Dict[str, int]:
    """category key -> Keepa root catId, resolved live ONCE then cached (root ids are stable
    Amazon browse nodes, so repeat runs never re-spend on this). Returns whatever subset
    resolves; an unmapped category is left OUT of the rotation, never guessed at. Never raises.

    Review fix (2026-07-07, live incident): this call used to have NO wait= override (silently
    defaulting to the keepa package's own wait=True) and NO deadline wrapper at all — on a
    GitHub Actions runner (ephemeral, no persistent disk between runs) the on-disk cache never
    survives, so every hourly-burst run hits this LIVE, unguarded and unwrapped. Once the
    account was already overdrawn (a separate real bug — see keepa_client._tokens_consumed's
    fix — that let tier 3 run at all despite tier 2 having already spent the bank), this call
    hit a 429 and the keepa library's own internal retry-wait slept for however long a refill
    actually takes (880s observed live), with nothing on our side bounding it. Now explicitly
    threads wait (collect_hourly.py's hourly burst passes wait=False, same as every other Keepa
    call it makes) and wraps the call in keepa_client._with_deadline for defense-in-depth even
    if wait=False's effect on this specific endpoint ever changes upstream.

    Review fix (2026-07-08 audit): the cache is now Supabase-Storage-backed (see
    _load_category_id_cache()) so it's a true one-time cost across ephemeral runners, AND this
    call is now guarded by keepa_client._guard_flat — previously it hit the live endpoint on
    every cache miss with no check the bank could even cover it, unlike every other Keepa call
    in this module."""
    cached = _load_category_id_cache()
    if cached and all(c in cached for c in categories):
        return cached
    if not keepa_client._guard_flat(api, keepa_client.CATEGORY_LOOKUP_TOKENS, "category lookup"):
        return cached
    if lookup_fn is None:
        lookup_fn = api.category_lookup
    try:
        roots = keepa_client._with_deadline(lookup_fn, 0, domain=config.KEEPA_DOMAIN, wait=wait) or {}
    except Exception as e:
        log.warning("category_lookup failed (non-fatal, using whatever was cached): %s",
                   keepa_client.redact_err(e))
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
    #
    # ML de-bias audit (2026-07-09): ai-brain.json's learning.sampling.categories spelled this key
    # "electronics-accessories" (hyphen) while _CATEGORY_MAP's values use "electronics_accessories"
    # (underscore) -- an exact-string inverse lookup silently never matched, so this ONE category
    # NEVER resolved and always fell back to an unfiltered pull. Normalizing hyphens to underscores
    # on both sides makes the match robust to either spelling convention instead of requiring the
    # two independently-edited files to stay byte-identical.
    inverse: Dict[str, str] = {}
    for keepa_name, short_key in keepa_client._CATEGORY_MAP.items():
        inverse.setdefault(short_key.replace("-", "_"), keepa_name)
    resolved = dict(cached)
    for cat in categories:
        keepa_name = inverse.get(cat.replace("-", "_"))
        if keepa_name and keepa_name in by_name:
            resolved[cat] = by_name[keepa_name]
    _save_category_id_cache(resolved)
    return resolved


# ML de-bias Lever A, part 2 (2026-07-09, ML_DEBIAS_PLAN.md): "vary a secondary axis across runs
# — rank sub-bands, price bands, 90-day drop% buckets — so you sweep the whole surface, not one
# corner." Category rotation alone still means every page within a category pulls whatever
# Keepa's /deal feed ranks first for that category (often the same handful of highly-active
# listings); rotating these filters too spreads collection across DIFFERENT slices of each
# category's surface. keepa.Keepa.deals()'s documented DEAL_REQUEST_KEYS include
# "salesRankRange", "currentRange" (price, in cents — same *100 convention as
# keepa_client.py's own Product Finder filters), and "deltaPercentRange" (price-drop %).
#
# deltaPercentRange's exact sign/scale convention is UNVERIFIED live (Keepa's own docs are terse
# here) — an inverted sign would just return fewer/no deals for that slice sometimes, degrading
# to breadth-neutral rather than erroring (fetch_deal_page already handles an empty page fine);
# flagged for confirmation once real per-band deal counts come back.
RANK_SUB_BANDS = [(0, 30000), (30000, 90000), (90000, 200000)]
PRICE_BANDS_DOLLARS = [(8, 20), (20, 40), (40, 60)]
DROP_PERCENT_BANDS = [(50, 100), (20, 50), (5, 20)]  # biggest drops first; UNVERIFIED convention

_SECONDARY_CURSOR_STORAGE_PATH = "backtest/dealfeed_secondary_cursor.json"
_SECONDARY_AXIS_SIZE = len(RANK_SUB_BANDS) * len(PRICE_BANDS_DOLLARS) * len(DROP_PERCENT_BANDS)


def _fetch_remote_secondary_cursor() -> int:
    try:
        import requests
        supa = os.getenv("SUPABASE_URL", "").rstrip("/")
        if not supa or not os.getenv("SUPABASE_SERVICE_KEY"):
            return 0
        r = requests.get(
            f"{supa}/storage/v1/object/{_CATEGORY_CACHE_BUCKET}/{_SECONDARY_CURSOR_STORAGE_PATH}",
            headers=_category_cache_storage_headers(), timeout=15)
        if r.status_code != 200:
            return 0
        v = (r.json() or {}).get("cursor")
        return int(v) if isinstance(v, (int, float)) else 0
    except Exception as e:
        log.warning("dealfeed secondary-axis cursor fetch failed (non-fatal, restarting at 0): %s", e)
        return 0


def _upload_remote_secondary_cursor(cursor: int) -> bool:
    try:
        import requests
        supa = os.getenv("SUPABASE_URL", "").rstrip("/")
        if not supa or not os.getenv("SUPABASE_SERVICE_KEY"):
            return False
        r = requests.post(
            f"{supa}/storage/v1/object/{_CATEGORY_CACHE_BUCKET}/{_SECONDARY_CURSOR_STORAGE_PATH}",
            headers={**_category_cache_storage_headers(), "x-upsert": "true",
                    "Content-Type": "application/json"},
            data=json.dumps({"cursor": cursor}).encode("utf-8"), timeout=30,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        log.warning("dealfeed secondary-axis cursor upload failed (non-fatal): %s", e)
        return False


def secondary_axis_filters(index: int) -> Dict[str, Any]:
    """Decomposes a combined cursor position into one (rank band, price band, drop% band) combo
    and returns the matching keepa.Keepa.deals() filter keys. Cycles through all
    len(RANK_SUB_BANDS)*len(PRICE_BANDS_DOLLARS)*len(DROP_PERCENT_BANDS) combinations as `index`
    advances — one full combo per dealfeed run (see harvest()), not per page, so a run explores
    one specific slice broadly across whichever categories the category cursor lands on."""
    index = index % _SECONDARY_AXIS_SIZE
    rank_idx, rem = divmod(index, len(PRICE_BANDS_DOLLARS) * len(DROP_PERCENT_BANDS))
    price_idx, drop_idx = divmod(rem, len(DROP_PERCENT_BANDS))
    rank_lo, rank_hi = RANK_SUB_BANDS[rank_idx]
    price_lo, price_hi = PRICE_BANDS_DOLLARS[price_idx]
    drop_lo, drop_hi = DROP_PERCENT_BANDS[drop_idx]
    return {
        "salesRankRange": [rank_lo, rank_hi],
        "currentRange": [int(price_lo * 100), int(price_hi * 100)],
        "deltaPercentRange": [drop_lo, drop_hi],
        # Review fix (2026-07-09, fba-code-reviewer, BLOCKER): keepa.Keepa.deals() JSON-dumps
        # deal_parms verbatim -- it does not auto-enable range filters. Keepa's own deals UI
        # gates these behind separate toggles; WITHOUT them, salesRankRange/currentRange/
        # deltaPercentRange above risk being silently ignored (every "band" secretly returns the
        # same unfiltered results -- a silent no-op, ml-doctrine.md §7's "green tests, broken
        # machine" failure class, since FakeApi.deals() in tests can't catch a Keepa-side ignore).
        # Harmless if unneeded; closes the gap if it is. Still UNVERIFIED until a live dispatch's
        # per-band asin counts confirm the filters are actually taking effect.
        "isRangeEnabled": True,
        "isFilterEnabled": True,
    }


def fetch_deal_page(api, category: Optional[str] = None, category_id: Optional[int] = None,
                    page: int = 0, wait: bool = True,
                    extra_filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """One /deal page (<=150 deals), guarded so its flat DEALS_PAGE_TOKENS cost never overdraws
    the bank. wait: True (default) lets the keepa lib drip-pace against the token bucket like
    every other endpoint in this project; scout/collect_hourly.py's burst collector passes
    wait=False (DATA_ENGINE_PLAN.md's "never block on a refill" rule) — the guard above already
    means this call is only attempted when the bank covers it, so wait=False rarely matters in
    practice, but it keeps this endpoint consistent with keepa_client.py's own wait= convention
    rather than being the one silent exception to it. extra_filters (e.g. secondary_axis_filters())
    are merged directly into the deal_parms sent to Keepa. Returns {"status", "asins": [...],
    "tokens_spent", "category", "page"}. NEVER raises — a rejected/failed call degrades to an
    honest empty result."""
    ok = keepa_client._guard_flat(api, DEALS_PAGE_TOKENS, "deals firehose page")
    if not ok:
        return {"status": "skipped", "reason": "insufficient bank", "asins": [],
                "tokens_spent": 0, "category": category, "page": page}
    deal_parms: Dict[str, Any] = {"page": page, "domainId": 1, "priceTypes": [0]}
    if category_id is not None:
        deal_parms["includeCategories"] = [category_id]
    if extra_filters:
        deal_parms.update(extra_filters)
    before = keepa_client._tokens_consumed(api)
    try:
        # Review fix (2026-07-07): wrapped in _with_deadline for defense-in-depth (matching
        # every other live Keepa call in keepa_client.py) — the guard above makes a hang here
        # unlikely in practice, but resolve_category_ids() right above this function looked
        # exactly as safe until it wasn't, and this is the same endpoint class.
        deals = keepa_client._with_deadline(api.deals, deal_parms, domain=config.KEEPA_DOMAIN,
                                           wait=wait) or {}
    except Exception as e:
        reason = keepa_client.redact_err(e)
        log.warning("deals() page failed (non-fatal): %s", reason)
        return {"status": "error", "reason": reason, "asins": [], "tokens_spent": 0,
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
    by construction (no brand seed is ever consulted).

    ML de-bias fix (2026-07-09, live incident): the category rotation below used to restart at
    `categories[0]` on EVERY call (`i` was always a fresh 0-based loop counter) -- with `pages`
    typically capped at 2-4 by the run's token budget and ~10 categories configured, every single
    hourly run only ever touched the FIRST few list entries. Live-confirmed: 100% of the 200
    dealfeed-sourced backtest_rows collected since this rotation existed were tagged "toys" (list
    index 0), and the corpus as a whole is 82.5% toys / top-5 brands 37% as a direct result — not a
    sampling-luck fluke, a structural bug. A cursor now persists ACROSS runs (same Supabase Storage
    pattern as the category-id cache above) so each run continues rotating from where the last one
    left off, guaranteeing every configured category eventually gets a turn regardless of how few
    pages any single run can afford.

    ML de-bias fix, Lever A part 2 (2026-07-09, ML_DEBIAS_PLAN.md): category rotation alone still
    means every page pulls whatever Keepa's /deal feed ranks first WITHIN that category — often
    the same handful of highly-active listings. A second persisted cursor (secondary_axis_filters())
    layered on top rotates rank/price/drop% bands too, one full combination per RUN (not per page,
    so a run explores one slice broadly across whichever categories the category cursor lands on)."""
    cfg = sampling_config()
    categories = categories if categories is not None else (cfg.get("categories") or [])
    pages = pages if pages is not None else DEFAULT_PAGES_PER_RUN

    rotation = list(categories)
    cursor = 0
    if rotation:
        cursor = _fetch_remote_cursor() % len(rotation)
        rotation = rotation[cursor:] + rotation[:cursor]

    secondary_cursor = _fetch_remote_secondary_cursor()
    secondary_filters = secondary_axis_filters(secondary_cursor)

    id_map: Dict[str, int] = {}
    total_spent = 0
    if categories:
        before = keepa_client._tokens_consumed(api)
        try:
            # Review fix (2026-07-07, live incident): wait= was never threaded through to the
            # resolver before — it silently defaulted to wait=True regardless of what THIS
            # function's own caller (e.g. collect_hourly.py's wait=False hourly burst) asked for.
            id_map = (resolve_fn or resolve_category_ids)(api, categories, wait=wait)
        except Exception as e:
            log.warning("category id resolution failed (non-fatal, unfiltered pull): %s",
                       keepa_client.redact_err(e))
        after = keepa_client._tokens_consumed(api)
        # Review fix (2026-07-08 audit): this cost used to go entirely unmeasured — a live
        # category_lookup() call (a real spend once the guard above lets it through on a cache
        # miss) never showed up in harvest()'s returned tokens_spent, understating this run's
        # true cost to every caller that budgets off it (collect_hourly.py's tier-3 waterfall).
        resolve_spent = keepa_client._delta(before, after)
        if isinstance(resolve_spent, int) and resolve_spent > 0:
            total_spent += resolve_spent

    out: List[Dict[str, Any]] = []
    seen = set()
    by_category: Dict[str, int] = {}
    pulled = 0
    for i in range(max(0, pages)):
        if rotation:
            cat = rotation[i % len(rotation)]
            cat_id = id_map.get(cat)
        else:
            cat, cat_id = None, None
        page = fetch_deal_page(api, category=cat, category_id=cat_id, page=0, wait=wait,
                              extra_filters=secondary_filters)
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
    if rotation:
        # Advance past however many category slots THIS run actually attempted (successes and
        # the one skip that broke the loop alike) so the next run picks up fresh ground instead
        # of potentially re-hitting the same still-dry category first.
        _upload_remote_cursor((cursor + pulled) % len(rotation))
    # One full secondary-axis combination per RUN (not per page/category slot) -- advances
    # regardless of how many pages this run actually pulled, so a starved run doesn't repeat the
    # same rank/price/drop% slice next time either.
    _upload_remote_secondary_cursor((secondary_cursor + 1) % _SECONDARY_AXIS_SIZE)
    # Review fix (2026-07-09, fba-code-reviewer SHOULD-FIX): 4 simultaneous filters (category +
    # rank + price + drop%) can legitimately AND down to zero-few real deals for many
    # combinations -- not a bug, but silent if nothing surfaces it. Logging the combo alongside
    # its actual yield makes a consistently-dry slice visible in the collector's own output
    # instead of only discoverable by manually cross-referencing the corpus later.
    if pulled:
        log.info("dealfeed secondary axis %s -> %d unique asin(s) across %d page(s)",
                 secondary_filters, len(out), pulled)
    return {"status": "ok", "asins": out, "pages_pulled": pulled, "tokens_spent": total_spent,
            "by_category": by_category, "categories_resolved": sorted(id_map.keys()),
            "secondary_axis_filters": secondary_filters}
