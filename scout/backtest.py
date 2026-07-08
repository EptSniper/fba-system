"""
scout/backtest.py — the historical backtest engine (DATA_ENGINE_PLAN.md V2).

The VOLUME source of training data (~50k rows target): for a few thousand on-policy ASINs, walk
their Keepa history and, at simulation dates every ~35 days, reconstruct the EXACT pre-decision
feature snapshot the live pipeline would have computed — using ONLY history strictly before that
date — then label each window at date+60 by whether it WOULD have profited at the simulated
landed cost.

THE HINDSIGHT-LEAKAGE BOUNDARY IS THE WHOLE GAME (and the deliverable is the tests that prove it):
  * the feature builder can see NO datapoint at or after the simulation date (strict `< as_of`);
  * an ASIN's windows never straddle a train/validation split (split BY ASIN, tested);
  * the reconstructed features reuse db.PRE_DECISION_FEATURES + the same projection the live path
    uses (db.feature_snapshot) — no parallel reimplementation of the feature contract.

These are the 4th and WEAKEST label tier (label_quality='backtest'): hindsight simulations with a
simulated buy cost, no execution, no sell-through. They train the ranker (V3) but are ALWAYS
reported as their own tier, never blended into gold/silver.

Storage: derived feature rows only (backtest_rows, migration 010) — NEVER raw histories (those
live in the data lake). Budget: hard token cap (brain learning.backtestTokenCap, default 10000),
resumable across days.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

import brands
import config
import db
import scoring

log = logging.getLogger("scout.backtest")

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN_PATH = os.path.join(HERE, "..", "learning-hub", "data", "ai-brain.json")

DEFAULT_BACKTEST_TOKEN_CAP = 10000
STEP_DAYS = 35              # a simulation window roughly every 35 days
LABEL_HORIZON_DAYS = 60    # label observed at simulation_date + 60
MIN_HISTORY_DAYS = 90      # need >=90 days of history BEFORE a window (for the avg90 features)
_ENRICH_BATCH = 100
TARGET_ASINS = 4000        # 3k-5k target; the token cap is the real limiter
SAMPLE_TOKEN_RESERVE_FRACTION = 0.5   # cap sampling (dealfeed/explore/onpolicy combined) to at
                                       # most half of run_backtest()'s token_cap, guaranteeing the
                                       # other half for the history-pull loop that actually builds
                                       # backtest_rows. Live-confirmed (2026-07-08, run 192): a
                                       # 39-token cap with NO reserve let sampling alone spend 41
                                       # tokens (599 ASINs sampled via dealfeed's full-cap
                                       # ceiling), leaving zero headroom for the loop below —
                                       # rows_written=0 despite a healthy sample. Same reserve
                                       # philosophy as collect_hourly.py's TIER1/TIER3_RESERVE_
                                       # FRACTION: one phase getting the whole budget by default
                                       # starves the phase that actually matters downstream.

# A normalized per-ASIN history is: {metric: [(day_ordinal:int, value:float|None), ...]} sorted by
# day, where day_ordinal is date.toordinal(). None value = out-of-stock/no-data at that point.
# Metrics: 'price', 'offers', 'sales_rank', 'amazon' (1.0 when Amazon holds the buy box, else 0.0).
Series = List[Tuple[int, Optional[float]]]
History = Dict[str, Series]


# --- brain-driven knobs -----------------------------------------------------
def backtest_token_cap() -> int:
    """learning.backtestTokenCap (default 10000) — the hard per-run token ceiling. Read live."""
    try:
        with open(BRAIN_PATH, encoding="utf-8") as f:
            v = ((json.load(f) or {}).get("learning") or {}).get("backtestTokenCap")
        if isinstance(v, (int, float)) and v > 0:
            return int(v)
    except Exception:
        pass
    return DEFAULT_BACKTEST_TOKEN_CAP


def sampling_config() -> Dict[str, Any]:
    """learning.sampling (Session 55) — categories/priceBands/bsrStrata/tags. {} if unavailable."""
    try:
        with open(BRAIN_PATH, encoding="utf-8") as f:
            brain = json.load(f) or {}
        return (brain.get("learning") or {}).get("sampling") or {}
    except Exception:
        return {}


# --- leakage-safe series reads (STRICTLY before the cutoff) -----------------
def _last_before(series: Series, as_of: int) -> Optional[float]:
    """The most recent non-None value at a day STRICTLY before `as_of`. This is the leakage
    boundary: a point at day == as_of or later is INVISIBLE, by construction."""
    val = None
    for day, v in series:
        if day >= as_of:
            break
        if v is not None:
            val = v
    return val


def _window_mean(series: Series, as_of: int, lookback: int) -> Optional[float]:
    """Mean of non-None values in [as_of - lookback, as_of) — again strictly before as_of."""
    lo = as_of - lookback
    vals = [v for day, v in series if lo <= day < as_of and v is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


def _oos_fraction(price_series: Series, as_of: int, lookback: int) -> Optional[float]:
    """Fraction of price points in the trailing window that were out of stock (None). Approximate
    (samples the observed points, not continuous time) — the honest proxy for Keepa's oos_90."""
    lo = as_of - lookback
    pts = [v for day, v in price_series if lo <= day < as_of]
    if not pts:
        return None
    return round(100.0 * sum(1 for v in pts if v is None) / len(pts), 1)


def _rank_drops(series: Series, as_of: int, lookback: int) -> Optional[int]:
    """Sales-rank DROPS (a rank decrease ~ a sale) in the trailing window — the est_sales proxy,
    mirroring Keepa's salesRankDrops30. Strictly before as_of."""
    lo = as_of - lookback
    pts = [v for day, v in series if lo <= day < as_of and v is not None]
    if len(pts) < 2:
        return None
    return sum(1 for a, b in zip(pts, pts[1:]) if b < a)


def _value_at_or_after(series: Series, target: int) -> Optional[float]:
    """The first non-None value at day >= target — used for the +horizon label (the observed
    future is ALLOWED here; this is the label side, not the feature side)."""
    for day, v in series:
        if day >= target and v is not None:
            return v
    return None


# --- feature reconstruction (reuses the live PRE_DECISION contract) ---------
def features_as_of(hist: History, as_of: int, static: Dict[str, Any]) -> Dict[str, Any]:
    """Reconstruct the enriched dict the live pipeline would have had at day `as_of`, from history
    STRICTLY before it. `static` carries the time-invariant fields (asin, brand, category,
    weight_lb). The result is projected through db.feature_snapshot by the caller, so it shares
    the live path's exact PRE_DECISION_FEATURES contract — no parallel feature list here."""
    price = hist.get("price", [])
    offers = hist.get("offers", [])
    rank = hist.get("sales_rank", [])
    amazon = hist.get("amazon", [])
    return {
        "asin": static.get("asin"),
        "brand": static.get("brand"),
        "category": static.get("category"),
        "weight_lb": static.get("weight_lb"),
        "price": _last_before(price, as_of),
        "offers": _int_or_none(_last_before(offers, as_of)),
        "sales_rank": _int_or_none(_last_before(rank, as_of)),
        "avg_price_90": _window_mean(price, as_of, 90),
        "avg_offers_90": _int_or_none(_window_mean(offers, as_of, 90)),
        "avg_sales_rank_90": _int_or_none(_window_mean(rank, as_of, 90)),
        "oos_90": _oos_fraction(price, as_of, 90),
        "est_sales": _rank_drops(rank, as_of, 30),
        "amazon_bb_share": _window_mean(amazon, as_of, 90),
        "buybox_seller": None,  # historical per-point seller id isn't reconstructable from csv
    }


def _int_or_none(v):
    return int(v) if isinstance(v, (int, float)) else None


# --- windowing + labeling ---------------------------------------------------
def windows_for(hist: History, step_days: int = STEP_DAYS,
                horizon: int = LABEL_HORIZON_DAYS, min_history: int = MIN_HISTORY_DAYS) -> List[int]:
    """Simulation days (ordinals) every ~step_days where BOTH sides have data: >= min_history days
    of history before, AND at least one observed point at/after day+horizon (for the label)."""
    price = hist.get("price", [])
    days = [d for d, v in price if v is not None]
    if len(days) < 2:
        return []
    first, last = days[0], days[-1]
    out = []
    d = first + min_history
    while d + horizon <= last:
        if _value_at_or_after(price, d + horizon) is not None and _last_before(price, d) is not None:
            out.append(d)
        d += step_days
    return out


def label_at(hist: History, as_of: int, landed_cost: Optional[float], weight_lb: Optional[float],
             category: Optional[str], horizon: int = LABEL_HORIZON_DAYS) -> Dict[str, Any]:
    """The observed label at as_of + horizon: would_have_profited at the ORIGINAL landed cost,
    via the SAME fee math (scoring.net_proceeds) the shadow tracker and live pipeline use."""
    price = hist.get("price", [])
    offers = hist.get("offers", [])
    price_at_h = _value_at_or_after(price, as_of + horizon)
    offers_at_h = _value_at_or_after(offers, as_of + horizon)
    net = scoring.net_proceeds(price_at_h, weight_lb, category=category)
    est_profit = would = None
    if net is not None and landed_cost is not None:
        est_profit = round(net - landed_cost, 2)
        would = est_profit > 0
    return {
        "price_at_horizon": price_at_h,
        "offers_at_horizon": _int_or_none(offers_at_h),
        "est_profit": est_profit,
        "would_have_profited": would,
    }


def _fetch_trend_series(brand: Optional[str], category: Optional[str],
                        cache: Optional[Dict[str, List[Tuple[Any, float]]]] = None):
    """Each term's FULL stored Trends series, fetched ONCE per ASIN (not once per simulation
    window) — trends_features() then filters to strictly-before-as_of per window from this same
    in-memory list, avoiding an expensive per-window Supabase round trip. Never raises; []/[] on
    any failure (trends_features degrades to stale=True nulls from an empty series, same as a
    genuinely-untracked term).

    `cache` (review fix, 2026-07-06): an optional pre-fetched {term: series} map — run_backtest()
    bulk-prefetches every distinct brand/category term ONCE per batch (signals.trends.
    prefetch_series) and passes it here so a batch of N ASINs costs one Supabase round trip
    instead of up to 2*N. A cache MISS still falls through to the old per-term live fetch below
    (never a hard requirement — single-ASIN callers, e.g. tests, keep working unchanged)."""
    def _series(term):
        if not term:
            return []
        if cache is not None and term in cache:
            return cache[term]
        try:
            raw = db.trends_series_for(term)
            return [(_dt.date.fromisoformat(r["week_start"]), float(r["interest"])) for r in raw]
        except Exception as e:
            log.warning("trends series fetch failed for %r (non-fatal): %s", term, e)
            return []
    return _series(brand), _series(category)


def _signal_features_for(as_of_date: _dt.date, brand: Optional[str], category: Optional[str],
                         brand_series=None, category_series=None) -> Dict[str, Any]:
    """Session 55's free signal-type features (scout/signals/), date-correct for `as_of_date` —
    leakage-safe (trends.trends_features only reads points strictly before as_of; calendar
    functions are pure functions of as_of). Any one source failing degrades to nulls for just
    that source, never loses the whole row."""
    try:
        from signals import calendar as signals_calendar
        cal_feats = signals_calendar.calendar_features(as_of_date)
    except Exception as e:
        log.warning("calendar_features failed (non-fatal): %s", e)
        cal_feats = {}
    try:
        from signals import trends as signals_trends
        brand_t = signals_trends.trends_features(brand, as_of_date, series=brand_series or []) if brand else {}
        cat_t = signals_trends.trends_features(category, as_of_date, series=category_series or []) if category else {}
    except Exception as e:
        log.warning("trends_features failed (non-fatal): %s", e)
        brand_t, cat_t = {}, {}
    return {
        **cal_feats,
        "brand_trend_ratio": brand_t.get("interest_now_vs_90d_avg"),
        "brand_trend_slope": brand_t.get("slope_4wk"),
        "brand_trend_seasonal_z": brand_t.get("seasonal_z"),
        "brand_trend_spike": brand_t.get("spike_flag"),
        "brand_trend_stale": brand_t.get("stale", True),
        "category_trend_ratio": cat_t.get("interest_now_vs_90d_avg"),
        "category_trend_slope": cat_t.get("slope_4wk"),
        "category_trend_seasonal_z": cat_t.get("seasonal_z"),
        "category_trend_spike": cat_t.get("spike_flag"),
        "category_trend_stale": cat_t.get("stale", True),
    }


def build_rows_for_asin(asin: str, hist: History, static: Dict[str, Any],
                        sample_source: str = "onpolicy",
                        step_days: int = STEP_DAYS, horizon: int = LABEL_HORIZON_DAYS,
                        min_history: int = MIN_HISTORY_DAYS,
                        trend_cache: Optional[Dict[str, List[Tuple[Any, float]]]] = None
                        ) -> List[Dict[str, Any]]:
    """Every backtest row for one ASIN (one per simulation window). Each carries the leakage-safe
    feature snapshot, the observed label, and split_key=asin so downstream splits stay BY ASIN.

    sample_source (Session 55): which mechanism supplied this ASIN — 'onpolicy' (friendly+hint
    brand-seeded, unchanged), 'explore' (brand-agnostic category-keyword search), or 'dealfeed'
    (the Keepa /deal firehose). ip_risk is computed from the SAME brands.is_avoided() the buy
    pipeline's hard-reject gate uses — an avoid-listed brand is still collected as training data
    (brandFilter=NONE for explore/dealfeed) but flagged, never silently blended in unlabeled.
    This function only ever writes to backtest_rows (via db.upsert_backtest_rows downstream) —
    it has no path to db.log_lead/decisions/review-queue, so a flagged row can never surface as a
    buy candidate regardless of its score (test-asserted: test_backtest_sampling.py).

    trend_cache (review fix, 2026-07-06): an optional pre-fetched {term: series} map, passed
    straight through to _fetch_trend_series — see run_backtest()'s batch loop, which bulk-
    prefetches once per batch instead of once per ASIN."""
    static = dict(static, asin=asin)
    ip_risk = brands.is_avoided(static.get("brand"))
    brand_series, category_series = _fetch_trend_series(static.get("brand"), static.get("category"),
                                                         cache=trend_cache)
    rows = []
    for as_of in windows_for(hist, step_days, horizon, min_history):
        enriched = features_as_of(hist, as_of, static)
        as_of_date = _dt.date.fromordinal(as_of)
        enriched.update(_signal_features_for(as_of_date, static.get("brand"), static.get("category"),
                                             brand_series=brand_series, category_series=category_series))
        price_then = enriched.get("price")
        landed_cost = scoring.assumed_landed_cost(price_then)
        lbl = label_at(hist, as_of, landed_cost, static.get("weight_lb"), static.get("category"), horizon)
        if lbl["would_have_profited"] is None:
            continue  # no usable label for this window — skip, never fabricate
        rows.append({
            "asin": asin,
            "simulation_date": _dt.date.fromordinal(as_of).isoformat(),
            "horizon_days": horizon,
            "features_snapshot": db.feature_snapshot(enriched),  # shared allowlist projection
            "landed_cost": landed_cost,
            "price_then": price_then,
            "offers_then": enriched.get("offers"),
            "price_at_horizon": lbl["price_at_horizon"],
            "offers_at_horizon": lbl["offers_at_horizon"],
            "est_profit": lbl["est_profit"],
            "would_have_profited": lbl["would_have_profited"],
            "label_quality": "backtest",
            "sample_source": sample_source,
            "category": enriched.get("category"),
            "ip_risk": ip_risk,
        })
    return rows


# --- by-ASIN split (leakage guard #2) ---------------------------------------
def split_by_asin(rows: List[Dict[str, Any]], val_fraction: float = 0.3
                  ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Partition rows into (train, val) so that ALL windows of any given ASIN land on the SAME
    side — an ASIN's windows must never straddle the boundary (temporal leakage). Deterministic
    (hash of asin), so it's stable across runs without Math.random."""
    train, val = [], []
    for r in rows:
        asin = r.get("asin") or ""
        bucket = (int(_stable_hash(asin), 16) % 1000) / 1000.0
        (val if bucket < val_fraction else train).append(r)
    return train, val


def _stable_hash(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:8]


# --- Keepa history adapter (LIVE-VERIFIED 2026-07-05, Session 51) -----------
def _to_ordinal(t) -> Optional[int]:
    """A keepa time point -> date ordinal. The keepa lib (to_datetime=True) yields
    datetime.datetime arrays (confirmed live 2026-07-05); numpy datetime64 and epoch-seconds
    are handled defensively for other lib versions. None (skip the point) when unparseable."""
    try:
        if hasattr(t, "toordinal"):
            return t.toordinal()
        try:
            import numpy as np
            if isinstance(t, np.datetime64):
                return int(t.astype("datetime64[D]").astype(int)) + _EPOCH_ORDINAL
        except ImportError:
            pass
        v = float(t)
        if 9.4e8 < v < 4.1e9:  # plausible epoch-seconds range (2000..2100)
            return _dt.datetime.utcfromtimestamp(v).toordinal()
        return None
    except Exception:
        return None


_EPOCH_ORDINAL = _dt.date(1970, 1, 1).toordinal()


def parse_keepa_history(product: Dict[str, Any]) -> Tuple[History, Dict[str, Any]]:
    """Convert a raw keepa product (from keepa_client.query_history, history=True) into the
    normalized History + static dict this module works in.

    LIVE-VERIFIED against real Pro-key responses (Session 51): product['data'] carries
    {'NEW': np.float64[] (dollars, NaN = out of stock), 'NEW_time': datetime.datetime[],
    'COUNT_NEW': np.int64[] (-1 = missing), 'SALES': sales-rank ints, 'AMAZON': Amazon's own
    offer price (NaN = Amazon out of stock)}. Static fields reuse keepa_client's category map +
    grams->lb conversion so the backtest and live pipeline share one vocabulary."""
    import keepa_client as _kc
    data = product.get("data") or {}
    category, _src = _kc._category_from_tree(product)
    static = {
        "asin": product.get("asin"),
        "brand": product.get("brand"),
        "category": category,
        "weight_lb": _kc._weight_lb(product),
    }

    def _series(value_key: str, time_key: str, scale: float = 1.0) -> Series:
        vals = data.get(value_key)
        times = data.get(time_key)
        if vals is None or times is None:
            return []
        out: Series = []
        for t, v in zip(times, vals):
            day = _to_ordinal(t)
            if day is None:
                continue
            fv = None
            try:
                if v is not None and v == v and float(v) >= 0:  # v==v filters NaN
                    fv = float(v) * scale
            except (TypeError, ValueError):
                fv = None
            out.append((day, fv))
        out.sort(key=lambda p: p[0])
        return out

    amazon_price = _series("AMAZON", "AMAZON_time")
    hist: History = {
        "price": _series("NEW", "NEW_time"),
        "offers": _series("COUNT_NEW", "COUNT_NEW_time"),
        "sales_rank": _series("SALES", "SALES_time"),
        # Amazon-presence proxy: 1.0 when Amazon itself had an offer at that point (AMAZON price
        # non-NaN), else 0.0 — the 90d windowed mean approximates amazon_bb_share for backtest
        # windows. A PRESENCE proxy, not true Buy-Box win share; documented weaker signal.
        "amazon": [(d, (1.0 if v is not None else 0.0)) for d, v in amazon_price],
    }
    return hist, static


# --- on-policy sampling + orchestration -------------------------------------
def _state_path() -> str:
    import datalake
    return os.path.join(datalake.lake_dir(), "_backtest_state.json")


_STATE_BUCKET = "models"
_STATE_STORAGE_PATH = "backtest/state.json"


def _state_storage_headers() -> Dict[str, str]:
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def _fetch_remote_state() -> Dict[str, Any]:
    """The resume state (processed ASINs, spend, rows written), persisted in Supabase Storage —
    see _load_state()'s docstring for why. {} on any failure/missing env — never raises, a
    missing remote state just means 'start fresh', same as an empty local file always meant."""
    try:
        import requests
        supa = os.getenv("SUPABASE_URL", "").rstrip("/")
        if not supa or not os.getenv("SUPABASE_SERVICE_KEY"):
            return {}
        r = requests.get(f"{supa}/storage/v1/object/{_STATE_BUCKET}/{_STATE_STORAGE_PATH}",
                         headers=_state_storage_headers(), timeout=15)
        if r.status_code != 200:
            return {}
        return r.json() or {}
    except Exception as e:
        log.warning("backtest remote state fetch failed (non-fatal): %s", e)
        return {}


def _upload_remote_state(st: Dict[str, Any]) -> bool:
    """Best-effort — never raises. Same bucket/upsert pattern train_ranker.py already uses for
    its own cross-run fingerprint, applied here for the backtest resume state."""
    try:
        import requests
        supa = os.getenv("SUPABASE_URL", "").rstrip("/")
        if not supa or not os.getenv("SUPABASE_SERVICE_KEY"):
            return False
        r = requests.post(
            f"{supa}/storage/v1/object/{_STATE_BUCKET}/{_STATE_STORAGE_PATH}",
            headers={**_state_storage_headers(), "x-upsert": "true", "Content-Type": "application/json"},
            data=json.dumps(st).encode("utf-8"), timeout=30,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        log.warning("backtest remote state upload failed (non-fatal): %s", e)
        return False


def _load_state() -> Dict[str, Any]:
    """Resume state (processed ASINs, spend, rows written so far). Review fix (2026-07-07, live
    incident): _state_path() is a LOCAL file — on GitHub Actions (no persistent disk between
    runs) it never actually survived, so every hourly burst silently started from empty state,
    re-sampled fresh dealfeed candidates, spent its whole tier-3 budget on sampling alone, and
    deferred everything (298 ASINs sampled, 0 processed, 0 rows written, observed live) — the
    exact resumability this mechanism exists to provide never actually happened in production.
    Now prefers the local file (fast path, unchanged for local dev / any persistent host) and
    falls back to the Supabase-Storage-backed copy when the local file is empty/missing."""
    try:
        with open(_state_path(), encoding="utf-8") as f:
            local = json.load(f) or {}
        if local:
            return local
    except Exception:
        pass
    return _fetch_remote_state()


def _save_state(st: Dict[str, Any]) -> None:
    """Persists BOTH locally (fast local-dev path, unchanged) AND to Supabase Storage, so the
    state actually survives an ephemeral GitHub Actions runner — see _load_state()'s docstring."""
    try:
        import datalake
        os.makedirs(datalake.lake_dir(), exist_ok=True)
        with open(_state_path(), "w", encoding="utf-8") as f:
            json.dump(st, f)
    except Exception as e:
        log.warning("backtest local state save failed (non-fatal): %s", e)
    _upload_remote_state(st)


def sample_asins_on_policy(api, budget_tokens: int, target: int = TARGET_ASINS,
                           find_fn: Optional[Callable] = None) -> Tuple[List[str], int]:
    """Pull candidate ASINs via the SAME Product Finder stack the live scout uses — per friendly
    brand + hint brands — NOT random ASINs (on-policy). Returns (unique_asins, tokens_spent).
    Product Finder itself costs tokens, drawn from the same cap."""
    if find_fn is None:
        import keepa_client
        find_fn = keepa_client.find_candidates
    seeds: List[str] = []
    try:
        import brands
        seeds += brands.seed_brands(config.BRAND_SEED_LIMIT) or []
    except Exception as e:
        # Review fix (2026-07-08 audit): was a bare `pass` — a broken brand-seed source silently
        # dropped the entire seed list with no trace, making a starved sample look identical to
        # "nothing configured".
        log.warning("backtest sampling: brands.seed_brands() failed (non-fatal): %s", e)
    try:
        import discovery_hints
        seeds += [s for s in (discovery_hints.hinted_brand_seeds() or []) if s not in seeds]
    except Exception as e:
        log.warning("backtest sampling: discovery_hints.hinted_brand_seeds() failed (non-fatal): %s", e)

    asins: List[str] = []
    seen = set()  # O(1) membership — list-scan dedupe goes quadratic at the 4-5k target
    spent = 0
    import keepa_client
    for brand in seeds:
        if len(asins) >= target or spent >= budget_tokens:
            break
        before = keepa_client._tokens_consumed(api)
        try:
            got = find_fn(api=api, brand_seeds=[brand], limit=min(300, target - len(asins)))
        except Exception as e:
            log.warning("backtest sampling finder failed for %s (non-fatal): %s", brand, e)
            got = []
        after = keepa_client._tokens_consumed(api)
        d = keepa_client._delta(before, after)
        # Unreadable counters -> charge Keepa's documented PF cost (10), never 0: an unbilled
        # sampling loop would blow straight through backtestTokenCap (Review 2026-07-05).
        spent += d if isinstance(d, int) and d > 0 else 10
        for a in got or []:
            if a not in seen:
                seen.add(a)
                asins.append(a)
    return asins[:target], spent


def sample_asins_explore(api, budget_tokens: int, categories: Optional[List[str]] = None,
                         find_fn: Optional[Callable] = None) -> Tuple[List[Dict[str, Any]], int]:
    """The brand-AGNOSTIC 'explore' sample (Session 55, learning.sampling — brandFilter=NONE):
    reuses the SAME Product-Finder-rejected-on-Pro search fallback sample_asins_on_policy already
    depends on (keepa_client.find_candidates -> _search_asins), but seeds it with CATEGORY
    keywords ("toys", "kitchen", ...) instead of brand names, so the token spend buys category
    breadth instead of buy-discovery-biased brand coverage. No friendly/avoid brand list is ever
    consulted. Returns ([{"asin","category"}], tokens_spent)."""
    if find_fn is None:
        import keepa_client
        find_fn = keepa_client.find_candidates
    cats = categories if categories is not None else (sampling_config().get("categories") or [])

    out: List[Dict[str, Any]] = []
    seen = set()
    spent = 0
    import keepa_client
    for cat in cats:
        if spent >= budget_tokens:
            break
        before = keepa_client._tokens_consumed(api)
        try:
            got = find_fn(api=api, brand_seeds=[cat], limit=50)
        except Exception as e:
            log.warning("explore sampling finder failed for %s (non-fatal): %s", cat, e)
            got = []
        after = keepa_client._tokens_consumed(api)
        d = keepa_client._delta(before, after)
        spent += d if isinstance(d, int) and d > 0 else 10
        for a in got or []:
            if a not in seen:
                seen.add(a)
                out.append({"asin": a, "category": cat})
    return out, spent


def sample_asins_stratified(api, budget_tokens: int, target: int = TARGET_ASINS,
                            find_fn: Optional[Callable] = None,
                            firehose_fn: Optional[Callable] = None
                            ) -> Tuple[List[Dict[str, Any]], int, Dict[str, int]]:
    """The brand-agnostic data-sampling plan (Session 55): three independent sources under ONE
    budget, waterfalled in priority order — dealfeed FIRST (the cheapest ASIN diversity available
    on this Pro plan, ~5 tokens/150-deal page), then explore (category-keyword search,
    brand-agnostic, ~10 tokens/term), then the EXISTING onpolicy brand-seeded sample (unchanged
    mechanism — kept as the ranker's onpolicy-vs-explore comparison baseline; buy-discovery's OWN
    seeding in pipeline.py/discovery_hints.py is a completely separate path, untouched by this).
    Each source's REAL observed spend is subtracted before sizing the next — a TRUE waterfall,
    dealfeed gets the FULL budget_tokens as its ceiling, not a pre-divided share (review fix,
    2026-07-07, live incident): the original code pre-split budget_tokens // 3 and capped
    dealfeed to ONLY that third, contradicting this very docstring's "dealfeed FIRST" claim — on
    a small tier-3 reserve (the exact scenario the 2026-07-07 reserve fix introduced) a 1/3 share
    routinely fell below DEALS_PAGE_TOKENS (5), silently zeroing out the cheapest and most
    reliable source (no dependency on Product Finder's Pro-plan rejection) every single run.
    Returns (asin_dicts, total_tokens_spent, per_source_counts) where each asin_dict is
    {"asin", "category", "sample_source"}."""
    spent = 0
    out: List[Dict[str, Any]] = []
    seen = set()
    counts = {"dealfeed": 0, "explore": 0, "onpolicy": 0}

    # 1) dealfeed — cheapest, goes first, gets the FULL budget as its ceiling (capped at 4 pages
    #    regardless, so a large budget still leaves plenty for explore/onpolicy below).
    #    firehose_fn defaults to deals_firehose.harvest with the library's normal wait=True
    #    drip-pacing; collect_hourly.py injects a wait=False closure (matching its own
    #    _find_no_wait/_history_no_wait convention) for the "never block on a refill" burst rule
    #    — the guard above already means this is rarely reached regardless.
    try:
        import deals_firehose
        pages_affordable = budget_tokens // max(1, deals_firehose.DEALS_PAGE_TOKENS)
        result = (firehose_fn or deals_firehose.harvest)(api, pages=min(max(pages_affordable, 0), 4)) \
            if pages_affordable > 0 else {"asins": [], "tokens_spent": 0}
    except Exception as e:
        log.warning("dealfeed harvest failed (non-fatal): %s", e)
        result = {"asins": [], "tokens_spent": 0}
    spent += result.get("tokens_spent") or 0
    for d in result.get("asins") or []:
        a = d.get("asin")
        if a and a not in seen:
            seen.add(a)
            out.append({"asin": a, "category": d.get("category"), "sample_source": "dealfeed"})
            counts["dealfeed"] += 1

    # 2) explore — brand-agnostic, gets whatever's left after dealfeed's REAL spend (a true
    #    waterfall — no longer reserves a separate onpolicy share up front).
    explore_budget = max(0, budget_tokens - spent)
    explore_asins, explore_spent = sample_asins_explore(api, explore_budget, find_fn=find_fn)
    spent += explore_spent
    for d in explore_asins:
        a = d.get("asin")
        if a and a not in seen:
            seen.add(a)
            out.append({"asin": a, "category": d.get("category"), "sample_source": "explore"})
            counts["explore"] += 1

    # 3) onpolicy — the existing brand-seeded mechanism, unchanged, whatever budget remains.
    onpolicy_budget = max(0, budget_tokens - spent)
    onpolicy_asins, onpolicy_spent = sample_asins_on_policy(
        api, budget_tokens=onpolicy_budget, target=max(0, target - len(out)), find_fn=find_fn)
    spent += onpolicy_spent
    for a in onpolicy_asins:
        if a not in seen:
            seen.add(a)
            out.append({"asin": a, "category": None, "sample_source": "onpolicy"})
            counts["onpolicy"] += 1

    return out[:target], spent, counts


def run_backtest(api=None, token_cap: Optional[int] = None, target: int = TARGET_ASINS,
                 history_fn: Optional[Callable] = None, find_fn: Optional[Callable] = None,
                 firehose_fn: Optional[Callable] = None, persist: bool = True) -> Dict[str, Any]:
    """Orchestrate one backtest run under the token cap, RESUMABLE across days (a state file records
    processed ASINs + spend + rows written, so a re-run continues toward the ~50k-row corpus rather
    than restarting). NEVER raises — returns an honest status dict.

    history_fn(asins, api) -> [raw keepa products]; find_fn is the Product Finder; firehose_fn is
    deals_firehose.harvest (Session 55). All three injectable for tests (no live Keepa spent in
    this repo) and for collect_hourly.py's wait=False burst wrappers."""
    import keepa_client
    if not config.have_keepa():
        return {"status": "disabled", "reason": "no KEEPA_KEY (backtest needs live history pulls)",
                "rows_written": 0}
    cap = token_cap if token_cap is not None else backtest_token_cap()
    if api is None:
        try:
            api = keepa_client.get_client()
        except Exception as e:
            return {"status": "error", "reason": keepa_client.redact_err(e), "rows_written": 0}
    if history_fn is None:
        history_fn = keepa_client.query_history

    state = _load_state()
    processed = set(state.get("processed_asins", []))
    # Review fix (2026-07-08, live incident): this used to be one `spent` variable, loaded from
    # persisted state and compared directly against `cap` (this run's own tiny token_cap, e.g.
    # 11-20 on a burst — collect_hourly.py's tier 3 only ever gets the hourly leftover, never
    # backtest_token_cap()'s big campaign ceiling). That was harmless ONLY because the state
    # file never actually survived between GitHub Actions runs (fixed 2026-07-08, "Persist
    # backtest resume state to Supabase Storage") -- `spent` was always a fresh 0 at the start of
    # every run, so `cap - spent == cap`. Now that persistence genuinely works, `spent_tokens` is
    # a real CUMULATIVE lifetime total that only grows, so `cap - spent` goes negative almost
    # immediately and STAYS at 0 forever after — LIVE-CONFIRMED (run 28910293641, 2026-07-08
    # 01:15 UTC): token_cap=15, lifetime spent=111, sample_asins_stratified got
    # budget_tokens=max(0,15-111)=0, and every run since would repeat this permanently. Split
    # the two concepts: `lifetime_spent` (persisted, monotonic, reporting-only) vs
    # `spent_this_run` (starts at 0 every call, gates every budget decision below).
    lifetime_spent = int(state.get("spent_tokens", 0))
    spent_this_run = 0
    rows_written = int(state.get("rows_written", 0))
    row_composition = dict(state.get("row_composition") or {})

    # 1) stratified sample — dealfeed + explore (brand-agnostic) + onpolicy (unchanged, brand-
    #    seeded), budget-waterfalled (Session 55, learning.sampling). Product Finder/search/deal
    #    spend all count against the same cap. Reserved to at most SAMPLE_TOKEN_RESERVE_FRACTION
    #    of `cap` (see that constant's docstring) so sampling can never eat the ENTIRE run budget
    #    and leave nothing for step 2 below to actually convert into rows.
    sample_budget = max(0, cap - int(cap * SAMPLE_TOKEN_RESERVE_FRACTION))
    sample_rows, sample_spent, sample_composition = sample_asins_stratified(
        api, budget_tokens=sample_budget, target=target, find_fn=find_fn,
        firehose_fn=firehose_fn)
    spent_this_run += sample_spent
    asin_source = {r["asin"]: r["sample_source"] for r in sample_rows}
    asins = [r["asin"] for r in sample_rows]
    todo = [a for a in asins if a not in processed]

    # 2) pull history + build rows, batched, until the cap bites (resumable — capped ASINs remain
    #    for the next day's run, reported as `deferred`).
    import datalake
    datalake.set_run_context("backtest")
    built = 0
    deferred = 0
    i = 0
    while i < len(todo):
        # Session 55 review fix: _ENRICH_BATCH (100) is a REQUEST-SIZE ceiling, not a promise
        # that 100 tokens are actually available — the Keepa Pro plan's bank caps at 60, so the
        # old `if spent + _ENRICH_BATCH > cap: break` check made the hourly cloud collector's
        # tier-3 backtest defer its ENTIRE todo list on the very first iteration of every run
        # (spent=0, cap<=60, 0+100>60 always true) and NEVER pull a single history batch. Size
        # the batch to what's ACTUALLY affordable right now — the live bank AND the remaining
        # run budget — so a low-token hourly burst still gets some rows instead of zero.
        available = keepa_client.current_tokens_left(api)
        headroom = max(0, cap - spent_this_run)
        if available is None:
            # Can't read the bank — degrade to trusting the run's own cap headroom (same
            # fallback philosophy as keepa_client._guard_batch's "can't read, trust the caller").
            batch_size = min(_ENRICH_BATCH, headroom)
        else:
            batch_size = min(_ENRICH_BATCH,
                            max(available, 0) // max(1, keepa_client.HISTORY_TOKENS_PER_ASIN),
                            headroom)
        if batch_size <= 0:
            deferred = len(todo) - i
            break
        batch = todo[i:i + batch_size]
        i += batch_size
        before = keepa_client._tokens_consumed(api)
        try:
            products = history_fn(batch, api=api) or []
        except Exception as e:
            log.warning("backtest history pull failed (non-fatal): %s", keepa_client.redact_err(e))
            products = []
        after = keepa_client._tokens_consumed(api)
        delta = keepa_client._delta(before, after)
        # ACTUAL measured spend when the counter is readable (matches sample_asins_on_policy's
        # own delta-based accounting) — NOT len(batch), which charged for ASINs even when the
        # guard inside history_fn truncated or skipped the request entirely (phantom spend that
        # was inflating the persisted state and starving future runs' budgets for no reason).
        # Falls back to the requested batch size (an honest worst-case, never an undercount)
        # only when the counter itself can't be read.
        spent_this_run += delta if isinstance(delta, int) and delta >= 0 else len(batch)
        parsed = []
        for product in products:
            if not isinstance(product, dict) or not product.get("asin"):
                continue
            hist, static = parse_keepa_history(product)
            parsed.append((product["asin"], hist, static))

        # Review fix (2026-07-06): ONE bulk Trends prefetch per BATCH (up to _ENRICH_BATCH
        # ASINs) instead of build_rows_for_asin's old per-ASIN live fetch (up to 2 sequential
        # Supabase calls per ASIN, no cross-ASIN caching) — that N+1 was the root cause of the
        # hourly collector's tier-3 backtest step hanging past keepa-collect.yml's 10-minute job
        # timeout once there were real ASINs to process. A prefetch failure degrades to an empty
        # cache (each ASIN falls through to its own live fetch, the old behavior), never blocks.
        trend_cache: Dict[str, Any] = {}
        try:
            from signals import trends as signals_trends
            terms = sorted({static.get(k) for _, _, static in parsed
                           for k in ("brand", "category") if static.get(k)})
            if terms:
                trend_cache = signals_trends.prefetch_series(terms)
        except Exception as e:
            log.warning("trends bulk prefetch failed for batch (non-fatal): %s", e)

        rows: List[Dict[str, Any]] = []
        batch_asins: List[str] = []
        for asin, hist, static in parsed:
            src = asin_source.get(asin, "onpolicy")
            new_rows = build_rows_for_asin(asin, hist, static, sample_source=src,
                                          trend_cache=trend_cache)
            rows += new_rows
            batch_asins.append(asin)
        if persist and rows:
            upserted = db.upsert_backtest_rows(rows)
            built += upserted
            if upserted == 0:
                # Upsert failed (e.g. migration 010/011 not applied / network): do NOT mark these
                # ASINs processed — resume would then skip them forever with ZERO rows stored,
                # a silent training-data hole (Review 2026-07-05). Their raw histories are in
                # the lake, so the retry next run costs dedupe-cheap tokens only.
                batch_asins = []
            else:
                for r in rows:
                    row_composition[r["sample_source"]] = row_composition.get(r["sample_source"], 0) + 1
        else:
            built += len(rows)
            for r in rows:
                row_composition[r["sample_source"]] = row_composition.get(r["sample_source"], 0) + 1
        processed.update(batch_asins)

    rows_written += built
    lifetime_spent += spent_this_run
    datalake.flush("backtest")
    if persist:
        _save_state({"processed_asins": sorted(processed), "spent_tokens": lifetime_spent,
                     "rows_written": rows_written, "row_composition": row_composition})

    return {"status": "ok", "asins_sampled": len(asins), "asins_processed": len(processed),
            "rows_written": built, "rows_total": rows_written, "tokens_spent": spent_this_run,
            "token_cap": cap, "deferred_asins": deferred,
            "sample_composition": sample_composition, "row_composition": row_composition,
            "supabase_rows": db.count_backtest_rows() if persist else built,
            "supabase_rows_by_source": db.backtest_rows_by_source() if persist else row_composition}
