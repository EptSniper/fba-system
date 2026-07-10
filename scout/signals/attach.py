"""
scout/signals/attach.py — attach the CURRENT (as-of-today) calendar/Trends/eBay signal features
onto already-enriched product dicts, shared by EVERY live scoring path.

fba-feature-engineer (2026-07-10, ML audit MAJOR): this lived only in collect_hourly.py, so the
pipeline.run_once path (run_scout.py CLI / any non-hourly scan) scored candidates with NaN for
18 of the challenger's 28 inputs (train/serve skew) AND its shadow enqueues wrote silver rows
missing every signal field — including day_of_week, a pure date function backtest rows always
carry, i.e. a per-path label-tier fingerprint (doctrine §4). One shared producer ends both.
"""
from __future__ import annotations

import datetime as _dt
import logging
from typing import Any, Dict, List

log = logging.getLogger("scout.signals.attach")


def attach_signal_features(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Session 55 — attach the CURRENT (as-of-today) calendar/Trends/eBay signal features onto
    each already-enriched product dict in place, so they flow into feature_snapshot the same way
    every other pre-decision field does (db.feature_snapshot reads PRE_DECISION_FEATURES off
    whatever keys are present on `p`). Best-effort and per-product isolated — one product's
    signal lookup failing never drops the batch; a per-run cache avoids re-fetching the same
    brand/category Trends series once per product when several share one."""
    today = _dt.date.today()
    try:
        from signals import calendar as signals_calendar
        cal_feats = signals_calendar.calendar_features(today)
    except Exception as e:
        log.warning("calendar_features failed (non-fatal): %s", e)
        cal_feats = {}

    signals_trends = None
    try:
        from signals import trends as signals_trends  # noqa: F401
    except Exception as e:
        log.warning("signals.trends unavailable (non-fatal): %s", e)

    signals_ebay = None
    try:
        from signals import ebay as signals_ebay  # noqa: F401
    except Exception as e:
        log.warning("signals.ebay unavailable (non-fatal): %s", e)

    # Review fix (2026-07-06): ONE bulk Supabase call for every distinct brand/category term in
    # this whole batch, instead of one live trends_features() call per term (each falling
    # through to its own individual db.trends_series_for() read). That per-term N+1 — up to
    # ~120 sequential live HTTP round trips for a full 60-candidate scan — was the root cause of
    # the hourly collector hanging past keepa-collect.yml's 10-minute job timeout once the Keepa
    # bank actually had real work to do: every run since the overdraw guard let the bank recover
    # got force-killed mid-flight, never reaching finish_run() (see run_hourly_collect()).
    trend_cache: Dict[str, Dict[str, Any]] = {}
    if signals_trends:
        terms = sorted({p[k] for p in products for k in ("brand", "category") if p.get(k)})
        try:
            series_by_term = signals_trends.prefetch_series(terms) if terms else {}
        except Exception as e:
            log.warning("trends bulk prefetch failed (non-fatal): %s", e)
            series_by_term = {}
        for term in terms:
            try:
                trend_cache[term] = signals_trends.trends_features(term, today, series=series_by_term.get(term, []))
            except Exception as e:
                log.warning("trends_features failed for %r (non-fatal): %s", term, e)
                trend_cache[term] = {}

    def _cached_trend(term: str) -> Dict[str, Any]:
        return trend_cache.get(term, {})

    for p in products:
        p.update(cal_feats)
        if signals_trends:
            brand_t = _cached_trend(p["brand"]) if p.get("brand") else {}
            cat_t = _cached_trend(p["category"]) if p.get("category") else {}
            p["brand_trend_ratio"] = brand_t.get("interest_now_vs_90d_avg")
            p["brand_trend_slope"] = brand_t.get("slope_4wk")
            p["brand_trend_seasonal_z"] = brand_t.get("seasonal_z")
            p["brand_trend_spike"] = brand_t.get("spike_flag")
            p["brand_trend_stale"] = brand_t.get("stale", True)
            p["category_trend_ratio"] = cat_t.get("interest_now_vs_90d_avg")
            p["category_trend_slope"] = cat_t.get("slope_4wk")
            p["category_trend_seasonal_z"] = cat_t.get("seasonal_z")
            p["category_trend_spike"] = cat_t.get("spike_flag")
            p["category_trend_stale"] = cat_t.get("stale", True)
        if signals_ebay and signals_ebay.enabled() and p.get("upc"):
            try:
                eb = signals_ebay.ebay_features(p["upc"], p.get("price"))
            except Exception as e:
                log.warning("ebay_features failed for %s (non-fatal): %s", p.get("asin"), e)
                eb = {}
            p["ebay_active_listing_count"] = eb.get("ebay_active_listing_count")
            p["median_active_price_vs_amazon_ratio"] = eb.get("median_active_price_vs_amazon_ratio")
            p["ebay_stale"] = eb.get("ebay_stale", True)
    return products
