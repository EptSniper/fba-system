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
    """The first non-None value at day >= target — used only as windows_for()'s cheap
    label-EXISTENCE pre-filter (the observed future is ALLOWED here; this is the label side,
    not the feature side). label_at() itself no longer reads the label value this way — see
    _point_in_effect()."""
    for day, v in series:
        if day >= target and v is not None:
            return v
    return None


LABEL_TRACKING_TOLERANCE_DAYS = 30  # how far before the horizon Keepa tracking may have stopped


def _point_in_effect(series: Series, at: int) -> Tuple[Optional[int], Optional[float]]:
    """The LAST point (day, value — INCLUDING a None/out-of-stock marker) strictly before `at`.
    Keepa csv series are change-point encoded: a point exists only when the value CHANGES, so
    the last point before a day is the value genuinely in effect ON that day (last observation
    carried forward). ML audit fix (2026-07-09): label_at() used to take the FIRST point at any
    day >= horizon with NO upper bound — a slow-moving product's 'price at +60d' could really be
    a price from months later, and an out-of-stock-at-horizon product silently borrowed its next
    future in-stock price instead of being censored."""
    day_at, val_at = None, None
    for day, v in series:
        if day >= at:
            break
        day_at, val_at = day, v
    return day_at, val_at


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
    via the SAME fee math (scoring.net_proceeds) the shadow tracker and live pipeline use.

    ML audit fix (2026-07-09): the label price is now the value IN EFFECT at the horizon
    (last-observation-carried-forward — correct for Keepa's change-point encoding), not the
    first change at ANY day after it (unbounded — a 'day-60' label could really be a price from
    months later). Two censoring rules, both honest skips (would_have_profited=None, the window
    never becomes a row) rather than fabricated labels: (1) out-of-stock in effect AT the
    horizon — there is no sale price to label with, and OOS-at-horizon products are
    disproportionately the LOSERS, so borrowing their next future in-stock price systematically
    inflated the positive rate; (2) Keepa tracking stopped more than
    LABEL_TRACKING_TOLERANCE_DAYS before the horizon (delisted/untracked — the carried-forward
    value is no longer evidence). `censored` is reported so run summaries can count what was
    skipped instead of silently thinning.

    Cowork leakage/labeling audit fix (2026-07-13, Mehmet-approved): would_have_profited used to
    be a bare `est_profit > 0` — with landed_cost fixed at OA_COGS_FRACTION (50%) of price_then,
    net proceeds ~70% of price, a product could fall ~28% and STILL label "profitable" (any
    positive $ at all). Live-measured: 91% positive, near-constant within several categories
    (95-97%), carrying almost no learnable signal — the label mostly encoded "did the price not
    crash" plus a generous fixed COGS assumption, not real sourcing edge. Now mirrors the SAME
    gate the live buy pipeline actually uses (scoring.py's oa_hard_reject/score_product_oa):
    profit >= CRITERIA_OA['min_profit_per_unit'] (default $3) AND roi >= min_roi (0.30, or the
    grocery exception 0.25) — a window only labels "would have profited" if it would have
    actually cleared the real buy bar, not merely broken even. `roi` is now also returned
    (est_profit / landed_cost) for visibility. NOTE: this only affects windows built going
    forward — existing backtest_rows keep their prior label until a deliberate backfill runs;
    see AI_COLLABORATION_JOURNAL.md Session 64 for the scope of what was and wasn't relabeled."""
    price = hist.get("price", [])
    offers = hist.get("offers", [])
    horizon_day = as_of + horizon
    last_tracked_day = price[-1][0] if price else None
    tracked_near_horizon = (last_tracked_day is not None
                           and last_tracked_day >= horizon_day - LABEL_TRACKING_TOLERANCE_DAYS)
    _, price_in_effect = _point_in_effect(price, horizon_day + 1)
    price_at_h = price_in_effect if tracked_near_horizon else None
    _, offers_in_effect = _point_in_effect(offers, horizon_day + 1)
    net = scoring.net_proceeds(price_at_h, weight_lb, category=category)
    est_profit = would = roi = None
    if net is not None and landed_cost is not None:
        est_profit = round(net - landed_cost, 2)
        roi = round(est_profit / landed_cost, 4) if landed_cost > 0 else None
        would = consistent_label(est_profit, landed_cost, category)
    return {
        "price_at_horizon": price_at_h,
        "offers_at_horizon": _int_or_none(offers_in_effect),
        "est_profit": est_profit,
        "roi": roi,
        "would_have_profited": would,
        "censored": price_at_h is None,
    }


def consistent_label(est_profit: Optional[float], landed_cost: Optional[float],
                     category: Optional[str]) -> Optional[bool]:
    """The CURRENT would_have_profited definition (profit >= CRITERIA_OA['min_profit_per_unit']
    AND roi >= min_roi, 0.25 for grocery), derived from already-known economics rather than
    re-simulating a window. The ONE place both label_at() (write time, above) and any reader
    recomputing a historical row's label from its stored est_profit/landed_cost (read time —
    labels.py's backtest tier) call this exact formula, so the two can never drift apart.

    ML rigor directive (2026-07-13, per Codex's audit + Cowork's corrected walk-forward): rows
    written before the 2026-07-13 label fix (Session 64) have a would_have_profited column that
    may still reflect the OLD `est_profit > 0` definition — mixing that with rows written after
    the fix, in the same training set, is exactly the label-cohort-mixing artifact that made the
    first walk-forward's AUC untrustworthy. Rather than an in-place UPDATE on the live
    backtest_rows table (a bulk production-data mutation Mehmet explicitly declined), a reader
    can always get the CURRENT, consistent definition by calling this function on the row's own
    stored est_profit/landed_cost/category — never touching the stored would_have_profited value
    itself. Returns None (not a guess) when profit/cost aren't both known."""
    if est_profit is None or landed_cost is None or landed_cost <= 0:
        return None
    roi = est_profit / landed_cost
    is_grocery = (category or "").strip().lower() == "grocery"
    min_roi = config.OA_GROCERY_MIN_ROI if is_grocery else config.CRITERIA_OA["min_roi"]
    min_profit = config.CRITERIA_OA["min_profit_per_unit"]
    return est_profit >= min_profit and roi >= min_roi


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


def split_by_time(rows: List[Dict[str, Any]], val_fraction: float = 0.3
                 ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Chronological split: the LATEST simulation_date rows become validation, everything earlier
    is training — tests whether the model generalizes FORWARD in time, which split_by_asin (a
    same-time GROUP split, deliberately not time-based — see ml-doctrine.md §4) does not.

    Unlike split_by_asin, the SAME ASIN's earlier window may sit in train while its later window
    sits in val here — that is the realistic forward-prediction scenario this split exists to
    check, not leakage (each row's own features_snapshot is already point-in-time-safe regardless
    of which side of any split it lands on). Deterministic given the input order (stable sort by
    simulation_date, ties broken by asin) — no Math.random."""
    sorted_rows = sorted(rows, key=lambda r: (str(r.get("simulation_date") or ""), r.get("asin") or ""))
    n_val = max(1, int(round(len(sorted_rows) * val_fraction))) if sorted_rows else 0
    if n_val >= len(sorted_rows):
        return [], sorted_rows
    return sorted_rows[:-n_val], sorted_rows[-n_val:]


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


def _fetch_remote_state(strict: bool = False) -> Dict[str, Any]:
    """The resume state (processed ASINs, spend, rows written), persisted in Supabase Storage —
    see _load_state()'s docstring for why. {} on any failure/missing env — never raises, a
    missing remote state just means 'start fresh', same as an empty local file always meant.

    ``strict=True`` is reserved for the hourly backlog preflight: an actual remote read failure
    raises a generic error so telemetry can report an unknown count instead of a false zero.
    Missing credentials or a genuinely absent object still mean there is no shared remote state.
    """
    try:
        import requests
        supa = os.getenv("SUPABASE_URL", "").rstrip("/")
        if not supa or not os.getenv("SUPABASE_SERVICE_KEY"):
            return {}
        r = requests.get(f"{supa}/storage/v1/object/{_STATE_BUCKET}/{_STATE_STORAGE_PATH}",
                         headers=_state_storage_headers(), timeout=15)
        if r.status_code == 404:
            return {}
        if r.status_code != 200:
            raise RuntimeError(f"backtest state HTTP {r.status_code}")
        state = r.json() or {}
        if not isinstance(state, dict):
            raise ValueError("backtest state payload is not an object")
        return state
    except Exception as e:
        log.warning("backtest remote state fetch failed (non-fatal): %s", e)
        if strict:
            raise RuntimeError("backtest remote state unavailable") from e
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


def _load_state(strict: bool = False) -> Dict[str, Any]:
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
    return _fetch_remote_state(strict=True) if strict else _fetch_remote_state()


def pending_backlog_count() -> int:
    """Count distinct, not-yet-processed ASINs already awaiting history pulls.

    The hourly collector uses this cheap preflight before deciding whether live discovery should
    spend any of the current Keepa bank. It shares run_backtest's persisted resume state and makes
    no Keepa request.
    """
    state = _load_state(strict=True)
    if not isinstance(state, dict):
        return 0
    processed = set(state.get("processed_asins") or [])
    return len({
        item.get("asin")
        for item in (state.get("pending") or [])
        if isinstance(item, dict) and item.get("asin") and item["asin"] not in processed
    })


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


# ML de-bias fix (2026-07-09, live incident): sample_asins_explore()'s category loop below used
# to always start at cats[0] on every call -- with its share of the sampling budget usually small
# (dealfeed takes its cut first in the waterfall) and each category costing ~10 tokens, only the
# first 1-2 configured categories ever got a real attempt, run after run. A separate persisted
# cursor (own Supabase Storage path, NOT folded into _load_state()/_save_state()'s dict --
# run_backtest() reads/writes that whole dict exactly once per call, so a second independent
# read-modify-write from inside this function would race and could clobber it) fixes the same
# structural bias deals_firehose.harvest() had.
_EXPLORE_CURSOR_BUCKET = "models"
_EXPLORE_CURSOR_STORAGE_PATH = "backtest/explore_cursor.json"


def _fetch_remote_explore_cursor() -> int:
    try:
        import requests
        supa = os.getenv("SUPABASE_URL", "").rstrip("/")
        if not supa or not os.getenv("SUPABASE_SERVICE_KEY"):
            return 0
        r = requests.get(
            f"{supa}/storage/v1/object/{_EXPLORE_CURSOR_BUCKET}/{_EXPLORE_CURSOR_STORAGE_PATH}",
            headers=_state_storage_headers(), timeout=15)
        if r.status_code != 200:
            return 0
        v = (r.json() or {}).get("cursor")
        return int(v) if isinstance(v, (int, float)) else 0
    except Exception as e:
        log.warning("explore rotation cursor fetch failed (non-fatal, restarting at 0): %s", e)
        return 0


def _upload_remote_explore_cursor(cursor: int) -> bool:
    try:
        import requests
        supa = os.getenv("SUPABASE_URL", "").rstrip("/")
        if not supa or not os.getenv("SUPABASE_SERVICE_KEY"):
            return False
        r = requests.post(
            f"{supa}/storage/v1/object/{_EXPLORE_CURSOR_BUCKET}/{_EXPLORE_CURSOR_STORAGE_PATH}",
            headers={**_state_storage_headers(), "x-upsert": "true",
                    "Content-Type": "application/json"},
            data=json.dumps({"cursor": cursor}).encode("utf-8"), timeout=30,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        log.warning("explore rotation cursor upload failed (non-fatal): %s", e)
        return False


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
        # `spent + SEARCH_TOKENS_PER_TERM > budget`, not `spent >= budget` (fix 2026-07-09,
        # noted live in Session 57: the old post-hoc check only stopped AFTER overspending —
        # each term costs a flat ~SEARCH_TOKENS_PER_TERM on this Pro plan, so a 15-token budget
        # spent 20. Pre-check the KNOWN per-call cost against what actually remains instead.
        if len(asins) >= target or spent + keepa_client.SEARCH_TOKENS_PER_TERM > budget_tokens:
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
    consulted. Returns ([{"asin","category"}], tokens_spent).

    ML de-bias fix (2026-07-09, live incident): rotation now starts from a cursor persisted
    ACROSS runs (see _fetch_remote_explore_cursor()'s docstring) instead of always restarting at
    cats[0] — under this function's typically small budget share, that meant only the first 1-2
    configured categories ever got a real attempt, forever."""
    if find_fn is None:
        import keepa_client
        find_fn = keepa_client.find_candidates
    cats = categories if categories is not None else (sampling_config().get("categories") or [])

    rotation = list(cats)
    cursor = 0
    if rotation:
        cursor = _fetch_remote_explore_cursor() % len(rotation)
        rotation = rotation[cursor:] + rotation[:cursor]

    out: List[Dict[str, Any]] = []
    seen = set()
    spent = 0
    attempted = 0
    import keepa_client
    for cat in rotation:
        # Pre-check the KNOWN flat per-term cost against what actually remains (fix 2026-07-09,
        # same as sample_asins_on_policy): the old post-hoc `spent >= budget` only stopped AFTER
        # overspending — a 1-9 token leftover still bought a full ~10-token term, silently
        # eating the history-loop reserve SAMPLE_TOKEN_RESERVE_FRACTION exists to guarantee.
        if spent + keepa_client.SEARCH_TOKENS_PER_TERM > budget_tokens:
            break
        attempted += 1
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
    if rotation:
        _upload_remote_explore_cursor((cursor + attempted) % len(rotation))
    return out, spent


def sample_asins_storefront(api, budget_tokens: int,
                            seller_fn: Optional[Callable] = None
                            ) -> Tuple[List[Dict[str, Any]], int]:
    """Keepa throughput plan Action D (2026-07-11, fba-scout-strategist): a full 3P storefront's
    ASIN list (hundreds of ASINs) for ~SELLER_QUERY_TOKENS_ESTIMATE tokens via Keepa's
    seller_query — the cheapest, most diverse breadth source left on this Pro plan once
    dealfeed's day-to-day deal overlap grows (Product Finder stays REQUEST_REJECTED). Brand-
    agnostic by construction: sellers come from deals_firehose's pool, itself populated
    opportunistically from whatever buybox_seller ids collect_hourly.py's enrich() calls
    already returned for OTHER reasons — no brand list is ever consulted here. Rotates through
    the pool via a persisted cursor (same cross-run pattern as the category/secondary-axis/
    explore cursors) so a small budget share still eventually reaches every known seller instead
    of always querying the same handful first. Returns ([{"asin","category":None}], tokens_spent)
    — empty/0 whenever the pool is empty, the budget can't afford even one query, or Keepa
    fails (never raises)."""
    import deals_firehose
    if seller_fn is None:
        import keepa_client
        seller_fn = keepa_client.seller_asins
    pool = deals_firehose._fetch_remote_seller_pool()
    if not pool:
        return [], 0

    rotation = list(pool)
    cursor = deals_firehose._fetch_remote_seller_cursor() % len(rotation)
    rotation = rotation[cursor:] + rotation[:cursor]

    import keepa_client
    per_query_cost = keepa_client.SELLER_QUERY_TOKENS_ESTIMATE
    out: List[Dict[str, Any]] = []
    seen = set()
    spent = 0
    attempted = 0
    for seller_id in rotation:
        if spent + per_query_cost > budget_tokens:
            break
        attempted += 1
        before = keepa_client._tokens_consumed(api)
        try:
            asins = seller_fn(seller_id, api=api)
        except Exception as e:
            log.warning("storefront sampling failed for seller %s (non-fatal): %s", seller_id, e)
            asins = []
        after = keepa_client._tokens_consumed(api)
        d = keepa_client._delta(before, after)
        spent += d if isinstance(d, int) and d > 0 else per_query_cost
        for a in asins or []:
            if a not in seen:
                seen.add(a)
                out.append({"asin": a, "category": None})
    if rotation:
        deals_firehose._upload_remote_seller_cursor((cursor + attempted) % len(rotation))
    return out, spent


def sample_asins_stratified(api, budget_tokens: int, target: int = TARGET_ASINS,
                            find_fn: Optional[Callable] = None,
                            firehose_fn: Optional[Callable] = None,
                            seller_fn: Optional[Callable] = None
                            ) -> Tuple[List[Dict[str, Any]], int, Dict[str, int]]:
    """The brand-agnostic data-sampling plan (Session 55, +storefront Session 60): four
    independent sources under ONE budget, waterfalled in priority order — dealfeed FIRST (the
    cheapest ASIN diversity available on this Pro plan, ~5 tokens/150-deal page), then storefront
    (a full 3P seller's catalog, ~10 tokens/hundreds of ASINs — the plan's cheapest NEW lever once
    dealfeed's day-to-day overlap grows), then explore (category-keyword search, brand-agnostic,
    ~10 tokens/term), then the EXISTING onpolicy brand-seeded sample (unchanged mechanism — kept
    as the ranker's onpolicy-vs-explore comparison baseline; buy-discovery's OWN seeding in
    pipeline.py/discovery_hints.py is a completely separate path, untouched by this).
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
    counts = {"dealfeed": 0, "storefront": 0, "explore": 0, "onpolicy": 0}

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

    # 2) storefront — a full 3P seller's catalog (Keepa throughput plan Action D), gets whatever's
    #    left after dealfeed's REAL spend. Degrades to a no-op (0 asins, 0 spent) until the seller
    #    pool has at least one entry — the pool only grows opportunistically as enrich() calls
    #    happen elsewhere, so a brand-new deployment simply skips this arm for a while rather than
    #    erroring.
    storefront_budget = max(0, budget_tokens - spent)
    storefront_asins, storefront_spent = sample_asins_storefront(
        api, storefront_budget, seller_fn=seller_fn)
    spent += storefront_spent
    for d in storefront_asins:
        a = d.get("asin")
        if a and a not in seen:
            seen.add(a)
            out.append({"asin": a, "category": d.get("category"), "sample_source": "storefront"})
            counts["storefront"] += 1

    # 3) explore — brand-agnostic, gets whatever's left after dealfeed/storefront's REAL spend (a
    #    true waterfall — no longer reserves a separate onpolicy share up front).
    explore_budget = max(0, budget_tokens - spent)
    explore_asins, explore_spent = sample_asins_explore(api, explore_budget, find_fn=find_fn)
    spent += explore_spent
    for d in explore_asins:
        a = d.get("asin")
        if a and a not in seen:
            seen.add(a)
            out.append({"asin": a, "category": d.get("category"), "sample_source": "explore"})
            counts["explore"] += 1

    # 4) onpolicy — the existing brand-seeded mechanism, unchanged, whatever budget remains.
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


def _interleave_by_category(pending: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Round-robin `pending` across its distinct `category` values (stable FIFO within each
    category), so a run_backtest() budget that can only afford a fraction of the backlog spreads
    across whatever categories are actually queued instead of fully draining whichever category
    happens to sit first. A single dealfeed rotation slot can hand over 100-250+ ASINs of ONE
    category at once (deals_firehose pulls a full page per slot); undoing that clustering here is
    what actually fixes cross-category breadth, since the rotation upstream already rotates fine —
    it's this backlog's drain ORDER that was re-concentrating it. No-op (returns as-is) for an
    empty or single-category backlog."""
    buckets: Dict[Any, List[Dict[str, Any]]] = {}
    order: List[Any] = []
    for p in pending:
        key = p.get("category")
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(p)
    if len(order) <= 1:
        return pending
    interleaved: List[Dict[str, Any]] = []
    while any(buckets[key] for key in order):
        for key in order:
            if buckets[key]:
                interleaved.append(buckets[key].pop(0))
    return interleaved


def run_backtest(api=None, token_cap: Optional[int] = None, target: int = TARGET_ASINS,
                 history_fn: Optional[Callable] = None, find_fn: Optional[Callable] = None,
                 firehose_fn: Optional[Callable] = None, seller_fn: Optional[Callable] = None,
                 persist: bool = True) -> Dict[str, Any]:
    """Orchestrate one backtest run under the token cap, RESUMABLE across days (a state file records
    processed ASINs + spend + rows written, so a re-run continues toward the ~50k-row corpus rather
    than restarting). NEVER raises — returns an honest status dict.

    history_fn(asins, api) -> [raw keepa products]; find_fn is the Product Finder; firehose_fn is
    deals_firehose.harvest (Session 55); seller_fn is keepa_client.seller_asins (Session 60's
    storefront source). All four injectable for tests (no live Keepa spent in this repo) and for
    collect_hourly.py's wait=False burst wrappers."""
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
    # Keepa throughput plan Action B (2026-07-11): a history-pull token is spent per ASIN
    # regardless of outcome, but windows_for() needs >=MIN_HISTORY_DAYS before AND a label point
    # at +LABEL_HORIZON_DAYS after -- an ASIN with too little Keepa tracking history yields ZERO
    # rows for its 1-token cost. Live-measured: 26.1% (177/677) of processed ASINs across the
    # corpus. No free pre-check exists (Keepa's /deal feed doesn't return trackingSince), so this
    # doesn't prevent the waste -- it makes the PER-SOURCE rate queryable instead of hidden,
    # matching the project's "no silent caps" principle, and lets a persistently-wasteful source
    # be deprioritized later with real evidence instead of a guess.
    zero_row_by_source = dict(state.get("zero_row_by_source") or {})

    # 0) drain the persisted PENDING backlog first (fba-ml-data-engineer, 2026-07-10 — the
    #    audit's top efficiency finding): every run used to re-sample ~600 fresh candidates
    #    while the cap only affords pulling ~20-130 histories, then THREW AWAY the deferred
    #    remainder — roughly half of every tier-3 budget re-bought the discovery of
    #    mostly-already-known ASINs. The un-pulled remainder now persists in the same state
    #    blob; sampling is SKIPPED entirely whenever the backlog already exceeds what this
    #    run's whole cap could pull, so on backlogged runs the full budget converts to rows.
    #
    #    Full-crew audit, 2026-07-11 (fba-scout-strategist, live-confirmed): draining this
    #    backlog in raw FIFO/insertion order let ONE dealfeed rotation slot's whole ASIN batch
    #    (100-250+ ASINs, since deals_firehose hands over a full page per category) monopolize
    #    every backtest run's small per-run pull budget (~20-130 histories) for MANY CONSECUTIVE
    #    HOURS before the backlog even reached the next category — live Supabase query showed
    #    4 straight hourly runs 100% "tools" (07-10 11:00-18:00), then a full switch to
    #    "grocery"/"office"/"sports". The hourly dealfeed rotation itself was already rotating
    #    correctly; this was a purely downstream throughput mismatch. _interleave_by_category
    #    round-robins the backlog across whatever categories are actually queued so a fixed
    #    per-run budget spreads across them immediately instead of fully draining one first.
    pending = _interleave_by_category([p for p in (state.get("pending") or [])
                                       if p.get("asin") and p["asin"] not in processed])
    import keepa_client as _kc
    affordable = max(1, cap // max(1, _kc.HISTORY_TOKENS_PER_ASIN))
    sampling_skipped = len(pending) >= affordable

    # 1) stratified sample — dealfeed + explore (brand-agnostic) + onpolicy (unchanged, brand-
    #    seeded), budget-waterfalled (Session 55, learning.sampling). Product Finder/search/deal
    #    spend all count against the same cap. Reserved to at most SAMPLE_TOKEN_RESERVE_FRACTION
    #    of `cap` (see that constant's docstring) so sampling can never eat the ENTIRE run budget
    #    and leave nothing for step 2 below to actually convert into rows.
    if sampling_skipped:
        log.info("backtest: pending backlog (%d) >= this run's affordable pulls (%d) — "
                "skipping sampling, full cap goes to history pulls", len(pending), affordable)
        sample_rows, sample_spent = [], 0
        sample_composition = {"dealfeed": 0, "storefront": 0, "explore": 0, "onpolicy": 0}
    else:
        sample_budget = max(0, cap - int(cap * SAMPLE_TOKEN_RESERVE_FRACTION))
        sample_rows, sample_spent, sample_composition = sample_asins_stratified(
            api, budget_tokens=sample_budget, target=target, find_fn=find_fn,
            firehose_fn=firehose_fn, seller_fn=seller_fn)
    spent_this_run += sample_spent
    # Backlog items drain FIRST (they were already paid for), then fresh samples. asin_source
    # carries each item's original sample_source tag either way.
    asin_source = {p["asin"]: p.get("sample_source") or "onpolicy" for p in pending}
    asin_category = {p["asin"]: p.get("category") for p in pending}
    for r in sample_rows:
        asin_source.setdefault(r["asin"], r["sample_source"])
        asin_category.setdefault(r["asin"], r.get("category"))
    asins = [p["asin"] for p in pending] + [r["asin"] for r in sample_rows
                                            if r["asin"] not in {p["asin"] for p in pending}]
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
        batch_zero_row_srcs: List[str] = []
        for asin, hist, static in parsed:
            src = asin_source.get(asin, "onpolicy")
            new_rows = build_rows_for_asin(asin, hist, static, sample_source=src,
                                          trend_cache=trend_cache)
            rows += new_rows
            batch_asins.append(asin)
            if not new_rows:
                batch_zero_row_srcs.append(src)
        if persist and rows:
            upserted = db.upsert_backtest_rows(rows)
            built += upserted
            if upserted == 0:
                # Upsert failed (e.g. migration 010/011 not applied / network): do NOT mark these
                # ASINs processed — resume would then skip them forever with ZERO rows stored,
                # a silent training-data hole (Review 2026-07-05). Their raw histories are in
                # the lake, so the retry re-spends HISTORY_TOKENS_PER_ASIN per ASIN (the lake dedupe saves STORAGE, not tokens) — acceptable because a silent training-data hole is worse than the token cost.
                batch_asins = []
                batch_zero_row_srcs = []
            else:
                for r in rows:
                    row_composition[r["sample_source"]] = row_composition.get(r["sample_source"], 0) + 1
        else:
            built += len(rows)
            for r in rows:
                row_composition[r["sample_source"]] = row_composition.get(r["sample_source"], 0) + 1
        for src in batch_zero_row_srcs:
            zero_row_by_source[src] = zero_row_by_source.get(src, 0) + 1
        processed.update(batch_asins)

    rows_written += built
    lifetime_spent += spent_this_run
    datalake.flush("backtest")
    # fba-ml-data-engineer (2026-07-10): persist the un-pulled remainder as the next run's
    # backlog instead of discarding it — includes failed-upsert batches (deliberately not in
    # `processed`, so they re-queue too). Capped so the blob can't grow unbounded; each entry
    # keeps its original sample_source/category tag for honest row attribution when drained.
    PENDING_BACKLOG_CAP = 3000
    remainder = [{"asin": a, "sample_source": asin_source.get(a) or "onpolicy",
                  "category": asin_category.get(a)}
                 for a in todo if a not in processed][:PENDING_BACKLOG_CAP]
    if persist:
        _save_state({"processed_asins": sorted(processed), "spent_tokens": lifetime_spent,
                     "rows_written": rows_written, "row_composition": row_composition,
                     "zero_row_by_source": zero_row_by_source, "pending": remainder})

    return {"status": "ok", "asins_sampled": len(asins), "asins_processed": len(processed),
            "pending_drained": len(pending), "pending_remaining": len(remainder),
            "sampling_skipped": sampling_skipped,
            "rows_written": built, "rows_total": rows_written, "tokens_spent": spent_this_run,
            "token_cap": cap, "deferred_asins": deferred,
            "sample_composition": sample_composition, "row_composition": row_composition,
            "zero_row_by_source": zero_row_by_source,
            "supabase_rows": db.count_backtest_rows() if persist else built,
            "supabase_rows_by_source": db.backtest_rows_by_source() if persist else row_composition}
