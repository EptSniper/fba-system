"""
keepa_client.py — thin, defensive wrapper around the `keepa` Python package.

Data policy: we NEVER scrape Amazon. Keepa is a sanctioned, paid data layer that
licenses Amazon price + sales-rank history. A PAID Keepa key is required
(Premium ~$19+/mo unlocks sales-rank data, Product Finder, and API access).

IMPORTANT about field names / Product Finder params:
    Keepa's Product Finder filter set is large and Keepa-specific, and the exact
    parameter keys change over time. Two ways to get the EXACT names for your
    account/version:
      1. Run  help(api.product_finder)  after constructing the client.
      2. Build the filter you want in Keepa's website Product Finder UI, then click
         "SHOW API QUERY" — it prints the precise JSON keys to copy here.
    The params below are a sensible starting set; confirm them before relying on
    results. Keepa expects PRICES IN CENTS and RATING x10 (4.3 stars -> 43).

The `keepa` import is guarded so this file (and the rest of the project) loads even
if the package isn't installed yet.
"""
from __future__ import annotations

import concurrent.futures
import os
import threading
from typing import Any, Dict, List, Optional

import config
import brands
import datalake  # V0 raw data lake — archive() never raises and no-ops when disabled/absent

try:
    import keepa  # pip install keepa
    _KEEPA = True
except Exception:  # pragma: no cover - package optional at import time
    keepa = None
    _KEEPA = False

# Code Review 2026-07-02, Finding S2: wait=True (used below) drip-paces against Keepa's token
# bucket by blocking/retrying with no built-in cap — a severely drained bucket can block a
# scheduled run indefinitely, past its next scheduled start. _with_deadline() wraps any such
# call in a hard wall-clock timeout via a background thread, so a drained key aborts this
# cycle honestly (the exception flows through pipeline.run_once()'s existing error handling —
# runs.error_summary, the digest, system_health) instead of hanging the whole process. Known
# limitation: Python cannot force-cancel a running thread, so the underlying Keepa call keeps
# blocking in the background until it either completes or the process exits — acceptable for a
# short-lived scheduled script, not for a long-running server.
KEEPA_CALL_DEADLINE_SECONDS = int(os.getenv("KEEPA_CALL_DEADLINE_SECONDS", "600"))  # 10 min

# Review fix (2026-07-07, live incident): the hourly cloud collector was silently hanging every
# single run past keepa-collect.yml's own timeout-minutes: 10 and getting force-killed with the
# Supabase `runs` row stuck at status='running' forever. Root cause: EVERY enrich()/
# query_history()/find_candidates() call — wait=True (nightly, legitimately may need to wait for
# a token refill) OR wait=False (the hourly burst, which must NEVER block) — was wrapped in the
# SAME _with_deadline() using the SAME 600s ceiling as the external job timeout. That guarantees
# the external kill always wins the race (it fires ~20-30s sooner, after accounting for the
# job's own checkout+install time) — our own honest TimeoutError never gets a chance to raise,
# unwind to run_hourly_collect()'s finally block, and call db.finish_run() with a real status.
# Worse, shadow_outcomes.run_rechecks() catches a per-batch enrich failure and keeps going, so
# MULTIPLE tiers/batches could each independently eat up to the full deadline in one run,
# compounding past the external budget regardless of what a single shared deadline was set to.
#
# Fix: wait=False calls (the hourly burst — should return almost instantly; nothing legitimate
# ever needs it to wait) get a MUCH shorter deadline than wait=True calls (nightly drip-pacing,
# which genuinely may want to wait several minutes for tokens to trickle in — unchanged).
KEEPA_NO_WAIT_DEADLINE_SECONDS = int(os.getenv("KEEPA_NO_WAIT_DEADLINE_SECONDS", "60"))


def _with_deadline(fn, *args, **kwargs):
    # Read (never pop) an existing wait= kwarg so it still flows through to fn exactly as the
    # caller passed it — this function doesn't own that parameter, it only inspects it to pick
    # a deadline. Absent entirely (e.g. a caller with no wait concept at all), default True/the
    # long deadline, matching the pre-fix behavior for every such caller.
    wait = kwargs.get("wait", True)
    deadline = KEEPA_CALL_DEADLINE_SECONDS if wait else KEEPA_NO_WAIT_DEADLINE_SECONDS
    # Review fix (2026-07-07, live incident): NOT a `with ... as pool:` context manager. Its
    # __exit__ calls shutdown(wait=True), which BLOCKS until the abandoned background thread
    # actually finishes — silently re-absorbing the full underlying hang duration on the way
    # out, regardless of what `deadline` is set to. That was quietly defeating the ENTIRE
    # deadline mechanism from the day it was written: every run's real wall-clock time was
    # dominated by however long the underlying call took to resolve on its own (observed: ~600s
    # every time), never by the configured deadline. shutdown(wait=False) lets this function
    # actually return/raise AT the deadline — the orphaned thread keeps running until it
    # finishes or the process exits (Python cannot force-cancel a thread; same documented
    # limitation as before), but this call no longer waits on it.
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = pool.submit(fn, *args, **kwargs)
    try:
        return future.result(timeout=deadline)
    except concurrent.futures.TimeoutError:
        raise TimeoutError(
            f"Keepa call exceeded its {deadline}s deadline (wait={wait}; "
            f"{'KEEPA_CALL_DEADLINE_SECONDS' if wait else 'KEEPA_NO_WAIT_DEADLINE_SECONDS'} "
            f"in .env) — likely a drained token bucket or an unresponsive Keepa API. "
            f"Aborting this cycle rather than blocking past the next scheduled run."
        )
    finally:
        pool.shutdown(wait=False)

# Keepa CSV "type" indices used to read stats['current'].
# (These follow Keepa's documented CSV ordering; confirm against your keepa
#  version with help(keepa.Keepa) if values look off.)
IDX_AMAZON = 0
IDX_NEW = 1
IDX_SALES_RANK = 3
IDX_COUNT_NEW = 11      # number of new offers (Buy Box crowding proxy)
IDX_RATING = 16         # rating x10  (45 -> 4.5 stars)
IDX_COUNT_REVIEWS = 17
IDX_BUY_BOX = 18        # buy box landed price (cents)

GRAMS_PER_LB = 453.59237


def _require_keepa():
    if not _KEEPA:
        raise ImportError(
            "The 'keepa' package is not installed. Run: pip install keepa\n"
            "You also need a PAID Keepa subscription key set as KEEPA_KEY in .env."
        )


def _tokens_consumed(api) -> Optional[int]:
    """A balance snapshot for computing a before/after SPEND delta via _delta() below — despite
    the name (kept for every existing call site), this reads the client's CURRENT tokens_left
    balance, not a cumulative counter.

    Review fix (2026-07-07, live incident): this used to read `tokens_consumed_total`/
    `tokens_consumed` off the api object — attributes the `keepa` PyPI package has NEVER
    actually exposed, in ANY version (confirmed by inspecting both 1.3.15, this repo's pinned
    dev version, and 1.5.0, the live-deployed version — neither defines either attribute
    anywhere; the client only ever tracks `tokens_left`, a balance). getattr(..., None) on a
    nonexistent attribute always returned None, so `_delta()` always returned None too, and
    every "measured spend" computation across this whole project (run_hourly_collect()'s
    cross-tier budget accounting, backtest.py's batch spend tracking, datalake token archiving)
    silently fell back to 0 or a length-based estimate instead of a real number — forever, since
    the day this was written. Concretely: tier 2 of the hourly burst could genuinely overdraw
    the account by ~90+ tokens, `tokens_spent` would still read back as 0, so tier 3 (backtest.
    run_backtest -> deals_firehose.harvest -> resolve_category_ids) would run anyway against an
    already-negative bank, reach a completely unguarded live Keepa call (see
    deals_firehose.resolve_category_ids' own fix), and hang.

    Reads the object's own last-known tokens_left (no extra network round trip — every real
    request already updates this attribute in place), matching the original function's
    free/no-extra-cost intent, just off the attribute that actually exists."""
    try:
        v = getattr(api, "tokens_left", None)
        return int(v) if isinstance(v, (int, float)) else None
    except Exception:
        return None


def _delta(before: Optional[int], after: Optional[int]) -> Optional[int]:
    """Tokens spent between two BALANCE reads (before - after — tokens_left DECREASES as tokens
    are spent, and Keepa allows it to go negative on overdraw). None if either read failed. A
    small negative result (balance went UP slightly) is possible if a refill tick landed
    mid-operation — reported honestly rather than clamped; callers already treat a falsy/None
    delta as 'unknown, degrade to a safer estimate'."""
    if isinstance(before, int) and isinstance(after, int):
        return before - after
    return None


# ----------------------------------------------------------------------------
# Hard overdraw guard (Session 55). LIVE-CONFIRMED: the Keepa balance hit -100 tokens — a
# batched request was sized off an ESTIMATE without ever checking the actual bank first, and
# Keepa charges the full batch cost upfront and ALLOWS negative balances (the consequence is
# ~100 minutes of enforced lockout at the 1 token/min Pro-trickle refill rate, not money, but a
# real availability hit to every job sharing this one key). This is the SINGLE CHOKE POINT: every
# request-making function in this file (enrich, query_history, the search-API fallback) routes
# through _guard_batch() before firing, so no caller — tracked or ad-hoc, today's collectors or
# a future one — can repeat this by forgetting to check its own budget first.
#
# Per-unit costs are the OBSERVED values from live telemetry (Sessions 51/54/55), not estimates:
ENRICH_TOKENS_PER_ASIN = 4     # enrich(): stats=90, rating=True, buybox=True, history=False.
                                # Corrected from 3 (2026-07-07, live incident): two independent
                                # real bursts each measured EXACTLY 64 tokens for a 16-ASIN batch
                                # (64/16 = 4.0) now that _tokens_consumed() actually reports real
                                # spend -- the old estimate of 3 let the guard under-cap the
                                # batch, causing a consistent ~14-token overdraft every run.
HISTORY_TOKENS_PER_ASIN = 1    # query_history(): stats=90, rating=False, history=True
SEARCH_TOKENS_PER_TERM = 10    # the flat-rate product-search fallback (Pro-plan PF substitute)
SELLER_QUERY_TOKENS_ESTIMATE = 10  # seller_asins() — UNVERIFIED, conservative placeholder;
                                    # not on any active collector's path today, guarded anyway.
DEALS_PAGE_TOKENS = 5          # deals_firehose.py's /deal page (<=150 deals) — Mehmet's spec,
                                # UNVERIFIED live until the account's negative balance recovers
                                # and a real dispatch confirms tokensConsumed (Session 55).

_guard_lock = threading.Lock()
_guard_stats = {"skips": 0, "caps": 0}


def guard_telemetry() -> Dict[str, int]:
    """Counts of overdraw-guard interventions this process — for the daily digest's honest
    'N runs skipped due to negative Keepa balance' line."""
    return dict(_guard_stats)


def reset_guard_telemetry() -> None:
    for k in _guard_stats:
        _guard_stats[k] = 0


def current_tokens_left(api, refresh: bool = True) -> Optional[int]:
    """The REAL current bank — MAY BE NEGATIVE (Keepa allows overdraw). `api.tokens_left` reads
    STALE (often a leftover 0) until either a request has been made or `update_status()` (a
    free, no-token-cost probe) is called explicitly — LIVE-CONFIRMED 2026-07-06 (Session 54): a
    naive read showed 0 when the true balance was actually -68. Returns None (not 0) when the
    attribute is genuinely unreadable, so callers can tell 'unknown' from 'exactly zero'."""
    if refresh:
        try:
            api.update_status()
        except Exception:
            pass
    v = getattr(api, "tokens_left", None)
    return int(v) if isinstance(v, (int, float)) else None


def _guard_batch(api, requested_n: int, tokens_per_unit: int, label: str) -> "tuple[int, bool]":
    """THE choke point. Before spending on `requested_n` units (ASINs, search terms) each
    costing ~tokens_per_unit, cap `requested_n` so the ESTIMATED total cost never exceeds the
    CURRENTLY BANKED tokens — WE must refuse to ask for more than we can afford; Keepa will not
    refuse it for us (it bills the full batch upfront and allows the balance to go negative).
    Returns (capped_n, skip_entirely). skip_entirely=True means the bank is empty/negative right
    now — the caller must return its own honest empty result, not attempt anything.
    requested_n<=0 is passed through unchanged (nothing to guard)."""
    if requested_n <= 0:
        return requested_n, False
    tokens_left = current_tokens_left(api)
    if tokens_left is None:
        return requested_n, False  # can't read the bank — degrade to trusting the caller's sizing
    available = max(tokens_left, 0)
    if available <= 0:
        with _guard_lock:
            _guard_stats["skips"] += 1
        print(f"[keepa] token guard: bank empty/negative ({tokens_left}) — skipping {label} "
             f"entirely (refills at 1 token/min)")
        return 0, True
    capped = max(1, available // max(1, tokens_per_unit))
    if capped < requested_n:
        with _guard_lock:
            _guard_stats["caps"] += 1
        print(f"[keepa] token guard: capping {label} from {requested_n} to {capped} "
             f"(bank={tokens_left}, ~{tokens_per_unit} tokens/unit)")
    return min(requested_n, capped), False


def _guard_flat(api, cost: int, label: str) -> bool:
    """Flat-cost sibling of _guard_batch, for endpoints whose price doesn't scale with a batch
    size (deals_firehose.py's /deal pages, a one-time category lookup): a single call either
    fits in the current bank or it doesn't — there's no smaller size to cap down to. Returns
    True (ok to spend `cost` tokens now) or False (bank can't cover it — skip entirely). Same
    single-choke-point philosophy as _guard_batch: an unreadable bank degrades to trusting the
    caller rather than blocking it."""
    tokens_left = current_tokens_left(api)
    if tokens_left is None:
        return True
    if tokens_left < cost:
        with _guard_lock:
            _guard_stats["skips"] += 1
        print(f"[keepa] token guard: bank ({tokens_left}) can't cover {label}'s {cost}-token "
             f"flat cost — skipping (refills at 1 token/min)")
        return False
    return True


def get_client(key: Optional[str] = None):
    """Construct a keepa.Keepa client. Raises a clear error if key/package missing."""
    _require_keepa()
    key = key or config.KEEPA_KEY
    if not key:
        raise ValueError("No Keepa key. Set KEEPA_KEY in .env (paid Keepa subscription).")
    return keepa.Keepa(key)


# ----------------------------------------------------------------------------
# helpers to read Keepa's stats safely
# ----------------------------------------------------------------------------
def _cur(stats: Dict[str, Any], idx: int):
    """Read stats['current'][idx], treating Keepa's -1 / missing as None."""
    try:
        v = stats["current"][idx]
        if v is None or v == -1:
            return None
        return v
    except (KeyError, IndexError, TypeError):
        return None


def _cents_to_dollars(c):
    return round(c / 100.0, 2) if isinstance(c, (int, float)) and c >= 0 else None


def _weight_lb(product: Dict[str, Any]) -> Optional[float]:
    for k in ("packageWeight", "itemWeight"):
        g = product.get(k)
        if isinstance(g, (int, float)) and g > 0:
            return round(g / GRAMS_PER_LB, 2)
    return None


def _upc(product: Dict[str, Any]) -> Optional[str]:
    """First UPC/EAN Keepa has on file for this ASIN (Session 55 — scout/signals/ebay.py's
    sold-comps key on). Read defensively across both list fields since exact availability
    varies by product/version; None (not fabricated) when neither is present."""
    for key in ("upcList", "eanList"):
        vals = product.get(key)
        if isinstance(vals, list) and vals:
            v = vals[0]
            if v:
                return str(v)
    return None


def _est_monthly_sales(stats: Dict[str, Any]) -> Optional[int]:
    """
    Estimate monthly units from Keepa 'Sales Rank Drops'. Each drop ~ a sale.
    Accurate at low volume; noisier above ~50/mo. Prefer the 30-day count.
    """
    d30 = stats.get("salesRankDrops30")
    if isinstance(d30, (int, float)) and d30 >= 0:
        return int(d30)
    d90 = stats.get("salesRankDrops90")
    if isinstance(d90, (int, float)) and d90 >= 0:
        return int(round(d90 / 3.0))
    return None


# Amazon category-tree names (Keepa's categoryTree[].name, a root->leaf breadcrumb of
# {catId, name}) mapped to this project's referral-rate keys (ai-brain.json
# fees.referralRates) — Amazon's real category names ("Toys & Games") are longer/human than
# our short rate keys ("toys"), so this is a translation table, not a passthrough. Deliberately
# incomplete: only covers categories the brain actually prices; add more as OA candidates hit
# an unmapped category (Code Review 2026-07-02, Finding S3).
_CATEGORY_MAP = {
    "toys & games": "toys",
    "home & kitchen": "home",
    "kitchen & dining": "kitchen",
    "grocery & gourmet food": "grocery",
    "beauty & personal care": "beauty",
    "health & household": "health",
    "health & personal care": "health",
    "clothing, shoes & jewelry": "clothing",
    "shoes": "shoes",
    "office products": "office",
    "pet supplies": "pet",
    "sports & outdoors": "sports",
    "tools & home improvement": "tools",
    "baby products": "baby",
    "baby": "baby",
    "cell phones & accessories": "electronics_accessories",
    "electronics": "electronics_accessories",
}


def _category_from_tree(product: Dict[str, Any]):
    """Map Keepa's categoryTree to one of this project's referral-rate keys. Tries every level
    leaf-to-root (the mapping table is deliberately incomplete); falls back to the raw root
    category name so callers always get SOMETHING to display even when it won't match a
    referral-rate key (config.referral_rate_for degrades to REFERRAL_RATES['default'] either
    way). Returns (category_or_none, category_source_or_none) — category_source is
    "keepa_category_tree" only when Keepa actually provided tree data, so callers can tell a
    real-but-unmapped category from "Keepa gave us nothing."""
    tree = product.get("categoryTree")
    if not isinstance(tree, list) or not tree:
        return None, None
    names = [n.get("name") for n in tree if isinstance(n, dict) and n.get("name")]
    if not names:
        return None, None
    for name in reversed(names):  # leaf-to-root
        mapped = _CATEGORY_MAP.get(name.strip().lower())
        if mapped:
            return mapped, "keepa_category_tree"
    return names[0], "keepa_category_tree"


def _normalize(product: Dict[str, Any]) -> Dict[str, Any]:
    stats = product.get("stats") or {}
    # price: prefer Buy Box, then NEW, then Amazon
    price = (_cents_to_dollars(stats.get("buyBoxPrice"))
             or _cents_to_dollars(_cur(stats, IDX_BUY_BOX))
             or _cents_to_dollars(_cur(stats, IDX_NEW))
             or _cents_to_dollars(_cur(stats, IDX_AMAZON)))
    rating_raw = _cur(stats, IDX_RATING)
    rating = round(rating_raw / 10.0, 1) if isinstance(rating_raw, (int, float)) else None
    reviews = _cur(stats, IDX_COUNT_REVIEWS)
    offers = _cur(stats, IDX_COUNT_NEW)
    sales_rank = _cur(stats, IDX_SALES_RANK)
    # 90-day average price (for the price-spike check). Keepa exposes stats['avg90'].
    avg90 = stats.get("avg90") or []

    def _avg90(idx):
        try:
            v = avg90[idx]
            return _cents_to_dollars(v) if v not in (None, -1) else None
        except (IndexError, TypeError):
            return None

    avg_price_90 = _avg90(IDX_BUY_BOX) or _avg90(IDX_NEW)

    def _avg90_count(idx):
        try:
            v = avg90[idx]
            return int(v) if isinstance(v, (int, float)) and v not in (None, -1) else None
        except (IndexError, TypeError):
            return None

    avg_offers_90 = _avg90_count(IDX_COUNT_NEW)

    # 90-day average SALES RANK (Scout Agent Build Plan sec 3.1 — "gate on avg90, not current
    # values"; current BSR is stockout/spike-prone). Same avg90 array, sales-rank index.
    def _avg90_rank(idx):
        try:
            v = avg90[idx]
            return int(v) if isinstance(v, (int, float)) and v not in (None, -1) else None
        except (IndexError, TypeError):
            return None

    avg_sales_rank_90 = _avg90_rank(IDX_SALES_RANK)

    # Amazon's Buy-Box WIN SHARE over the period (Buy-Box "rotation"). Keepa returns
    # `buyBoxStats` when query(..., buybox=True): a dict keyed by sellerId ->
    # {percentageWon, avgPrice, isFBA, ...}. We read Amazon's percentageWon (0-100) and
    # normalize to a 0-1 fraction. Confirm the exact key/units against your keepa version.
    def _amazon_bb_share():
        bbs = product.get("buyBoxStats") or stats.get("buyBoxStats") or {}
        if not isinstance(bbs, dict):
            return None
        entry = bbs.get(config.AMAZON_SELLER_ID)
        pw = entry.get("percentageWon") if isinstance(entry, dict) else None
        return round(pw / 100.0, 3) if isinstance(pw, (int, float)) and pw >= 0 else None

    amazon_bb_share = _amazon_bb_share()

    # 90-day LOW Buy-Box price (for the worst-case break-even check in scoring). Keepa exposes the
    # minimum differently across versions (`min90` scalar array, or `min` where each entry may be a
    # [timestamp, value] pair) — read defensively; degrade to None rather than guess.
    min90 = stats.get("min90") or stats.get("min") or []

    def _min90_price(idx):
        try:
            v = min90[idx]
        except (IndexError, TypeError):
            return None
        if isinstance(v, (list, tuple)):
            v = v[-1] if v else None
        return _cents_to_dollars(v) if v not in (None, -1) else None

    price_low_90 = _min90_price(IDX_BUY_BOX) or _min90_price(IDX_NEW)

    # Featured offer (Buy Box) presence. buybox_price is the current Buy-Box landed price; has_buybox
    # is True/False/None — only False when we have offer data but NO featured offer, so a missing-data
    # product never falsely trips the "no featured offer" flag in scoring.
    bb_price = _cents_to_dollars(stats.get("buyBoxPrice")) or _cents_to_dollars(_cur(stats, IDX_BUY_BOX))
    bb_seller = stats.get("buyBoxSellerId")
    if bb_seller or bb_price:
        has_buybox = True
    elif offers is not None:
        has_buybox = False
    else:
        has_buybox = None

    category, category_source = _category_from_tree(product)

    return {
        "asin": product.get("asin"),
        "title": product.get("title"),
        "brand": product.get("brand"),
        "category": category,
        "category_source": category_source,
        "upc": _upc(product),
        "price": price,
        "rating": rating,
        "reviews": int(reviews) if isinstance(reviews, (int, float)) else None,
        "offers": int(offers) if isinstance(offers, (int, float)) else None,
        "sales_rank": int(sales_rank) if isinstance(sales_rank, (int, float)) else None,
        "weight_lb": _weight_lb(product),
        "est_sales": _est_monthly_sales(stats),
        "drops30": stats.get("salesRankDrops30"),
        "drops90": stats.get("salesRankDrops90"),
        "buybox_seller": bb_seller,
        "buybox_price": bb_price,
        "has_buybox": has_buybox,
        "oos_90": stats.get("outOfStockPercentage90"),
        "avg_price_90": avg_price_90,
        "avg_offers_90": avg_offers_90,
        "avg_sales_rank_90": avg_sales_rank_90,
        "price_low_90": price_low_90,
        "amazon_bb_share": amazon_bb_share,
    }


# ----------------------------------------------------------------------------
# public API
# ----------------------------------------------------------------------------
def find_candidates(criteria: Optional[Dict[str, Any]] = None,
                    api=None, limit: Optional[int] = None,
                    brand_seeds: Optional[List[str]] = None, wait: bool = True) -> List[str]:
    """
    Use Keepa Product Finder to return candidate ASINs matching the criteria.

    Returns a list of ASIN strings. See the module docstring about confirming the
    exact Product Finder parameter names for your Keepa version.

    brand_seeds: an explicit brand-seed override (TOP100_DEAL_WATCH_PLAN.md T3 — the deal
    watch's fresh hinted brands, for the hint-led FIRST discovery pass). None -> the normal
    friendly-brand rotation (brands.seed_brands). An explicit [] means "seed nothing" (search
    broadly), distinct from None.

    wait: True (default) drip-paces against the token bucket (blocks until enough tokens
    refill) — correct for the nightly run's "drip, not burst" rule. scout/collect_hourly.py's
    burst collector passes wait=False (spend only what's currently banked, never block waiting
    for a refill) — DATA_ENGINE_PLAN.md's hourly-burst model.
    """
    _require_keepa()
    api = api or get_client()
    c = criteria or config.active_criteria()
    limit = limit or config.CANDIDATE_LIMIT

    # ---- Product Finder query (CONFIRM these keys via help(api.product_finder)
    #      or Keepa's "SHOW API QUERY"). Prices in CENTS, rating x10. ----
    if config.MODE == "OA":
        # Online arbitrage: mirror the Keepa Product Finder recipe from the videos —
        # price band + sales-rank cap + a seller-count BAND + proven velocity.
        # (Amazon-on-Buy-Box and rising-offer trend are filtered later in scoring.)
        params: Dict[str, Any] = {
            "current_NEW_gte": int(c["price_min"] * 100),
            "current_NEW_lte": int(c["price_max"] * 100),
            "current_SALES_lte": int(c["bsr_max"]),         # sales RANK <= max (CONFIRM key)
            "current_COUNT_NEW_gte": int(c["min_offers"]),  # >= a few sellers => OA, not PL/wholesale
            "current_COUNT_NEW_lte": int(c["max_offers"]),  # but not a crowded price war
            "packageWeight_lte": int(c["max_weight_lb"] * GRAMS_PER_LB),
            "salesRankDrops30_gte": int(c["min_monthly_sales"]),
            "sort": [["salesRankDrops30", "desc"]],
            "perPage": min(limit, 10000),
            "page": 0,
        }
        # Knowledge-driven: aim at our known-good brands (brands.py) like the videos do — OR at
        # an explicit brand_seeds override (deal-watch hinted brands, T3's hint-led pass). A
        # non-None brand_seeds wins over the default rotation; an explicit [] seeds nothing.
        if brand_seeds is not None:
            seeds = brand_seeds
        elif config.USE_BRAND_SEEDS:
            seeds = brands.seed_brands(config.BRAND_SEED_LIMIT)
        else:
            seeds = []
        if seeds:
            params["brand"] = seeds   # CONFIRM exact key via Keepa "SHOW API QUERY"
    else:
        # Private label (legacy): weak incumbents + beatable review moat.
        params = {
            "current_NEW_gte": int(c["price_min"] * 100),
            "current_NEW_lte": int(c["price_max"] * 100),
            "current_COUNT_REVIEWS_lte": int(c["max_reviews"]),
            "current_RATING_lte": int(c["max_rating"] * 10),
            "current_COUNT_NEW_lte": int(c["max_offers"]),
            "packageWeight_lte": int(c["max_weight_lb"] * GRAMS_PER_LB),
            "salesRankDrops30_gte": int(c["min_monthly_sales"]),
            "sort": [["salesRankDrops30", "desc"]],
            "perPage": min(limit, 10000),
            "page": 0,
        }

    # wait=True: drip-pace against the token bucket (block/retry instead of erroring on a rate
    # limit) — System Blueprint Prompt G2's "drip, not burst" rule; safe for a nightly run.
    # Wrapped in a hard deadline (Finding S2) so a drained bucket aborts honestly instead of
    # blocking indefinitely.
    before = _tokens_consumed(api)
    try:
        asins = _with_deadline(api.product_finder, params, domain=config.KEEPA_DOMAIN, wait=wait)
    except Exception as e:
        # LIVE-CONFIRMED 2026-07-05 (Session 51): Keepa PRO-plan keys get REQUEST_REJECTED on the
        # Product Finder endpoint (it's an API-plan feature). The product-SEARCH endpoint IS
        # available on Pro (10 tokens/term), so fall back to searching the seed brands — weaker
        # filtering (no BSR/offer-count server-side; our own gates still apply downstream) but a
        # working nightly discovery until the API-tier upgrade. Other errors re-raise unchanged.
        fallback_terms = list(params.get("brand") or [])[:3]  # seeds only exist in OA mode
        if "REQUEST_REJECTED" not in str(e) or not fallback_terms:
            raise
        # Overdraw guard (Session 55): each search term is a flat SEARCH_TOKENS_PER_TERM cost —
        # cap how many terms we even ATTEMPT so the estimate never exceeds the currently banked
        # tokens (Keepa bills the full request upfront and allows the balance to go negative;
        # we must refuse to ask for more than we can afford, since it will not refuse for us).
        capped_n, skip = _guard_batch(api, len(fallback_terms), SEARCH_TOKENS_PER_TERM, "brand search")
        if skip:
            asins = []
        else:
            fallback_terms = fallback_terms[:capped_n]
            print("[keepa] Product Finder rejected on this plan; falling back to brand SEARCH "
                  f"({len(fallback_terms)} term(s), {SEARCH_TOKENS_PER_TERM} tokens each)")
            asins = _search_asins(fallback_terms, limit)
    after = _tokens_consumed(api)
    asins = list(asins or [])[:limit]
    # Archive the raw finder response (the params + ASIN set it returned). Keyed by params_hash
    # so re-running the same recipe dedupes when the market hasn't moved and appends when it has
    # — this IS the on-policy sampling history V2's backtest reads. Never breaks discovery.
    datalake.archive("keepa", datalake.params_hash(params), "product_finder",
                     {"params": params, "asins": list(asins)},
                     tokens_consumed=_delta(before, after), params=params)
    return asins


def _search_asins(terms: List[str], limit: int) -> List[str]:
    """Pro-plan discovery fallback: Keepa's product-search endpoint per brand term (10 tokens
    each, ~20 products/term; live-verified 2026-07-05). Raw responses archived. Never raises —
    a failed term just contributes nothing."""
    import requests as _rq
    out: List[str] = []
    seen = set()
    for term in terms:
        try:
            r = _rq.get("https://api.keepa.com/search",
                        params={"key": config.KEEPA_KEY, "domain": 1,
                                "type": "product", "term": term}, timeout=60)
            data = r.json() or {}
            prods = data.get("products") or []
            datalake.archive("keepa", f"search:{term}", "product_search",
                             [{k: p.get(k) for k in ("asin", "title", "brand")} for p in prods],
                             tokens_consumed=data.get("tokensConsumed"))
            for p in prods:
                a = p.get("asin")
                if a and a not in seen:
                    seen.add(a)
                    out.append(a)
        except Exception as e2:
            print(f"[keepa] search fallback failed for {term!r}: {redact_err(e2)}")
        if len(out) >= limit:
            break
    return out[:limit]


def redact_err(e: Exception) -> str:
    """Error text safe for logs — the search URL carries the key as a query param, so a raw
    requests exception string could leak it."""
    try:
        import redact
        return redact.redact(str(e))[:200]
    except Exception:
        return type(e).__name__


def enrich(asins: List[str], api=None, wait: bool = True) -> List[Dict[str, Any]]:
    """
    Pull stats for ASINs via api.query and normalize the fields we score on:
    price, est_sales (from sales-rank drops), reviews, rating, weight, offers.

    wait: see find_candidates()'s docstring — False for the hourly burst collector (never
    block waiting on a token refill; a request beyond the current bank should fail/degrade
    fast, not stall the run).
    """
    if not asins:
        return []
    _require_keepa()
    api = api or get_client()

    # Overdraw guard (Session 55): cap the batch so its ESTIMATED cost never exceeds the
    # currently banked tokens — Keepa bills the full batch upfront and allows the balance to go
    # negative, so WE must refuse to over-ask rather than trust Keepa to refuse it for us.
    asins = list(asins)
    capped_n, skip = _guard_batch(api, len(asins), ENRICH_TOKENS_PER_ASIN, "enrich")
    if skip:
        return []
    asins = asins[:capped_n]

    # stats=90 computes 90-day stats incl. salesRankDrops30/90; rating=True pulls
    # rating + review counts; buybox=True returns buyBoxStats (Amazon's Buy-Box win
    # share, for the rotation guard). These extra fields can cost more Keepa tokens.
    # Wrapped in a hard deadline (Finding S2) — same reasoning as find_candidates() above.
    before = _tokens_consumed(api)
    products = _with_deadline(
        api.query,
        list(asins),
        domain=config.KEEPA_DOMAIN,
        stats=90,
        rating=True,
        buybox=True,     # -> product['buyBoxStats']: who wins the Buy Box & how often
        history=False,   # we only need stats, not full time series -> cheaper
        wait=wait,        # drip-pace against the token bucket (System Blueprint Prompt G2) —
                          # or not, for the hourly burst (DATA_ENGINE_PLAN.md's spend-only-
                          # what's-banked rule).
    )
    after = _tokens_consumed(api)
    plist = products or []
    # Archive each RAW product response, keyed by ASIN, so a re-pull next week dedupes when the
    # product hasn't changed. Batch token cost is split evenly across the products (an estimate —
    # Keepa doesn't itemize per-ASIN cost). Archiving can never break enrichment.
    per_tokens = None
    batch_tokens = _delta(before, after)
    if batch_tokens is not None and plist:
        per_tokens = int(round(batch_tokens / len(plist)))
    for p in plist:
        datalake.archive("keepa", (p.get("asin") if isinstance(p, dict) else None),
                         "product", p, tokens_consumed=per_tokens)
    out = []
    for p in plist:
        try:
            out.append(_normalize(p))
        except Exception:
            # never let one bad product blow up the batch
            out.append({"asin": p.get("asin"), "title": p.get("title")})
    return out


def query_history(asins: List[str], api=None, days: int = 365, wait: bool = True) -> List[Dict[str, Any]]:
    """Pull FULL price/rank/offer HISTORY (not just current stats) for a batch of ASINs — the
    backtest engine's on-policy data source (DATA_ENGINE_PLAN.md V2). Unlike enrich() (history=
    False, cheap), this returns Keepa's time-series `data`/`csv` so features can be reconstructed
    at PAST dates. Each raw product is archived (endpoint 'product_history', keyed by ASIN) so a
    re-pull dedupes. Returns the RAW keepa products (backtest.parse_keepa_history parses them).

    LIVE-VERIFIED 2026-07-05 (Session 51): 1 token/ASIN observed for this exact field mix.
    wait: see find_candidates()'s docstring — False for the hourly burst collector."""
    if not asins:
        return []
    _require_keepa()
    api = api or get_client()

    # Overdraw guard (Session 55) — same reasoning as enrich() above.
    asins = list(asins)
    capped_n, skip = _guard_batch(api, len(asins), HISTORY_TOKENS_PER_ASIN, "query_history")
    if skip:
        return []
    asins = asins[:capped_n]

    before = _tokens_consumed(api)
    products = _with_deadline(
        api.query, list(asins), domain=config.KEEPA_DOMAIN,
        stats=90, rating=False, history=True, days=days, wait=wait,
    )
    after = _tokens_consumed(api)
    plist = products or []
    per_tokens = None
    batch_tokens = _delta(before, after)
    if batch_tokens is not None and plist:
        per_tokens = int(round(batch_tokens / len(plist)))
    for p in plist:
        datalake.archive("keepa", (p.get("asin") if isinstance(p, dict) else None),
                         "product_history", _json_safe(p), tokens_consumed=per_tokens)
    return plist


def _json_safe(obj):
    """Deep-convert a keepa history product for lossless JSON archiving: numpy arrays -> lists
    (str(np.array) ELIDES long arrays with '...', silently corrupting an archived payload),
    numpy scalars -> python scalars, datetimes -> isoformat. Never raises — falls back to str."""
    try:
        import numpy as np
    except Exception:
        np = None
    import datetime as _dt2
    if np is not None and isinstance(obj, np.ndarray):
        return [_json_safe(x) for x in obj.tolist()]
    if np is not None and isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(x) for x in obj]
    if isinstance(obj, (_dt2.datetime, _dt2.date)):
        return obj.isoformat()
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def token_telemetry(api) -> Dict[str, Optional[int]]:
    """Read tokensLeft off a keepa.Keepa client instance for the runs table (System Blueprint
    Prompt G2 — "a drained key silently looks like no results, alert on tokensLeft"). Read
    defensively via getattr — degrade to None rather than raise.

    Review fix (2026-07-07, live incident): "tokens_consumed"/"tokens_consumed_total" used to
    be read off the api object here — attributes the `keepa` package has NEVER actually
    exposed, in any version (confirmed against 1.3.15 and the live-deployed 1.5.0; the client
    only ever tracks tokens_left, a balance). That always returned None, and every caller of
    _tokens_consumed()/_delta() (the real budget-tracking path) silently inherited the bug —
    see _tokens_consumed()'s own docstring for the fix there. This function's "tokens_consumed"
    key is kept for any existing caller checking for its presence, but is now honestly None
    always (a real per-call spend needs a before/after tokens_left DIFFERENCE, which this
    single-snapshot function can't produce — that's exactly what _tokens_consumed()/_delta()
    are for)."""
    return {
        "tokens_left": getattr(api, "tokens_left", None),
        "tokens_consumed": None,
    }


def seller_asins(seller_id: str, api=None, wait: bool = True) -> List[str]:
    """Return the ASINs in a seller's catalog via Keepa's seller data."""
    _require_keepa()
    api = api or get_client()
    # Overdraw guard (Session 55): a single seller_query is one "unit" at an unverified but
    # conservative estimated cost — not on any active collector's path today, guarded anyway
    # since this is the single choke point every Keepa-calling function routes through.
    _capped_n, skip = _guard_batch(api, 1, SELLER_QUERY_TOKENS_ESTIMATE, "seller_query")
    if skip:
        return []
    before = _tokens_consumed(api)
    # Review fix (2026-07-07): this call had no wait= override (silently defaulted to the keepa
    # package's own wait=True) and no deadline wrapper — the exact unguarded shape that hung
    # deals_firehose.resolve_category_ids() live. Not on any active collector's path today, but
    # fixed anyway so it can't become the next version of that incident if this ever gets wired
    # into a scheduled job without someone remembering the guard.
    res = _with_deadline(api.seller_query, seller_id, domain=config.KEEPA_DOMAIN, wait=wait)
    after = _tokens_consumed(api)
    datalake.archive("keepa", seller_id, "seller", res, tokens_consumed=_delta(before, after))
    info = (res or {}).get(seller_id, {}) if isinstance(res, dict) else {}
    return list(info.get("asinList", []) or [])


def seller_catalog_signals(asins: List[str], api=None) -> List[Dict[str, Any]]:
    """
    Rank a competitor's ASINs by VELOCITY PROXIES, highest first.

    NOTE (be honest in comments): Keepa cannot reveal a competitor's exact private
    sales. The legitimate signals are velocity PROXIES — Keepa 'Sales Rank Drops'
    (each drop ~ a sale) and Buy Box stability / low out-of-stock %. We rank on
    those, not on real sales numbers.
    """
    enriched = enrich(asins, api=api)
    for e in enriched:
        drops = e.get("est_sales") or 0
        oos = e.get("oos_90") or 0
        has_buybox = 1 if e.get("buybox_seller") else 0
        # simple, transparent velocity proxy
        e["velocity_proxy"] = round(drops * (1 - min(oos, 100) / 100.0) + 2 * has_buybox, 2)
    enriched.sort(key=lambda x: x.get("velocity_proxy", 0), reverse=True)
    return enriched
