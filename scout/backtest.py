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


def build_rows_for_asin(asin: str, hist: History, static: Dict[str, Any],
                        step_days: int = STEP_DAYS, horizon: int = LABEL_HORIZON_DAYS,
                        min_history: int = MIN_HISTORY_DAYS) -> List[Dict[str, Any]]:
    """Every backtest row for one ASIN (one per simulation window). Each carries the leakage-safe
    feature snapshot, the observed label, and split_key=asin so downstream splits stay BY ASIN."""
    static = dict(static, asin=asin)
    rows = []
    for as_of in windows_for(hist, step_days, horizon, min_history):
        enriched = features_as_of(hist, as_of, static)
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


def _load_state() -> Dict[str, Any]:
    try:
        with open(_state_path(), encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save_state(st: Dict[str, Any]) -> None:
    try:
        import datalake
        os.makedirs(datalake.lake_dir(), exist_ok=True)
        with open(_state_path(), "w", encoding="utf-8") as f:
            json.dump(st, f)
    except Exception as e:
        log.warning("backtest state save failed (non-fatal): %s", e)


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
    except Exception:
        pass
    try:
        import discovery_hints
        seeds += [s for s in (discovery_hints.hinted_brand_seeds() or []) if s not in seeds]
    except Exception:
        pass

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


def run_backtest(api=None, token_cap: Optional[int] = None, target: int = TARGET_ASINS,
                 history_fn: Optional[Callable] = None, find_fn: Optional[Callable] = None,
                 persist: bool = True) -> Dict[str, Any]:
    """Orchestrate one backtest run under the token cap, RESUMABLE across days (a state file records
    processed ASINs + spend + rows written, so a re-run continues toward the ~50k-row corpus rather
    than restarting). NEVER raises — returns an honest status dict.

    history_fn(asins, api) -> [raw keepa products]; find_fn is the Product Finder. Both injectable
    for tests (no live Keepa spent in this repo)."""
    if not config.have_keepa():
        return {"status": "disabled", "reason": "no KEEPA_KEY (backtest needs live history pulls)",
                "rows_written": 0}
    cap = token_cap if token_cap is not None else backtest_token_cap()
    if api is None:
        try:
            import keepa_client
            api = keepa_client.get_client()
        except Exception as e:
            return {"status": "error", "reason": str(e), "rows_written": 0}
    if history_fn is None:
        import keepa_client
        history_fn = keepa_client.query_history

    state = _load_state()
    processed = set(state.get("processed_asins", []))
    spent = int(state.get("spent_tokens", 0))
    rows_written = int(state.get("rows_written", 0))

    # 1) on-policy sample (Product Finder spend counts against the cap)
    asins, sample_spent = sample_asins_on_policy(api, budget_tokens=max(0, cap - spent),
                                                 target=target, find_fn=find_fn)
    spent += sample_spent
    todo = [a for a in asins if a not in processed]

    # 2) pull history + build rows, batched, until the cap bites (resumable — capped ASINs remain
    #    for the next day's run, reported as `deferred`).
    import datalake
    datalake.set_run_context("backtest")
    built = 0
    deferred = 0
    i = 0
    while i < len(todo):
        if spent + _ENRICH_BATCH > cap:
            deferred = len(todo) - i
            break
        batch = todo[i:i + _ENRICH_BATCH]
        i += _ENRICH_BATCH
        try:
            products = history_fn(batch, api=api) or []
        except Exception as e:
            log.warning("backtest history pull failed (non-fatal): %s", e)
            products = []
        spent += len(batch)  # ~1 token/ASIN (confirmed cost recorded by keepa_client on live pull)
        rows: List[Dict[str, Any]] = []
        batch_asins: List[str] = []
        for product in products:
            if not isinstance(product, dict) or not product.get("asin"):
                continue
            hist, static = parse_keepa_history(product)
            rows += build_rows_for_asin(product["asin"], hist, static)
            batch_asins.append(product["asin"])
        if persist and rows:
            upserted = db.upsert_backtest_rows(rows)
            built += upserted
            if upserted == 0:
                # Upsert failed (e.g. migration 010 not applied / network): do NOT mark these
                # ASINs processed — resume would then skip them forever with ZERO rows stored,
                # a silent training-data hole (Review 2026-07-05). Their raw histories are in
                # the lake, so the retry next run costs dedupe-cheap tokens only.
                batch_asins = []
        else:
            built += len(rows)
        processed.update(batch_asins)

    rows_written += built
    datalake.flush("backtest")
    if persist:
        _save_state({"processed_asins": sorted(processed), "spent_tokens": spent,
                     "rows_written": rows_written})

    return {"status": "ok", "asins_sampled": len(asins), "asins_processed": len(processed),
            "rows_written": built, "rows_total": rows_written, "tokens_spent": spent,
            "token_cap": cap, "deferred_asins": deferred,
            "supabase_rows": db.count_backtest_rows() if persist else built}
