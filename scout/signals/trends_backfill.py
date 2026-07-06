"""
scout/signals/trends_backfill.py — Session 55's one-time 5-year Trends backfill.

Two phases, run once (then collect_weekly's regular cadence keeps the corpus current):

  1. backfill_vocabulary(): pull each tracked term's FULL 5-year historical series
     (trends.backfill_term) so the corpus has real coverage before the next scheduled retrain,
     instead of waiting ~5 years for collect_weekly's weekly cadence to accumulate it.
  2. backfill_backtest_rows(): for every EXISTING backtest_rows row, recompute calendar + trend
     features at THAT ROW'S OWN simulation_date (never today — leakage-safe, the same boundary
     scout/backtest.py's live feature builder enforces) and patch its stored features_snapshot
     with the new keys, re-upserting the WHOLE row on its existing (asin, simulation_date)
     natural key so nothing else about the row changes.

SCOPE NOTE: leads/shadow_outcomes rows are NOT backfilled by this module — their exact
capture-date columns weren't confirmed with the same certainty as backtest_rows.simulation_date
within this session's scope, so backfilling them is a follow-up rather than a guess. backtest_rows
is the highest-volume corpus (the ~50k-row target) and the one the user's spec named explicitly.

NOT YET LIVE-RUN (Session 55): built + unit-tested (mocked pytrends client, mocked Supabase) —
the actual live pass (real 5-year pulls across ~200+ terms, then patching however many real
backtest_rows exist) is a manual/cron step to run once this code is reviewed, matching this
project's established "built, not yet live-verified" pattern for anything needing a live external
call this session couldn't safely make (the Keepa account was in negative balance throughout).
"""
from __future__ import annotations

import datetime as _dt
import logging
from typing import Any, Callable, Dict, List, Optional

import db
from signals import trends

log = logging.getLogger("scout.signals.trends_backfill")


def backfill_vocabulary(client=None, sleep_fn=None,
                        vocabulary_fn: Optional[Callable] = None) -> Dict[str, Any]:
    """Phase 1: pull the full 5-year series for every tracked term (trends.vocabulary()), one
    term at a time, per-term isolated (one failing term never blocks the rest). NEVER raises."""
    terms = (vocabulary_fn or trends.vocabulary)()
    ok, failed = [], []
    total_rows = 0
    for term_kind, term in terms:
        result = trends.backfill_term(term, term_kind, client=client, sleep_fn=sleep_fn)
        if result.get("status") == "ok":
            ok.append(term)
            total_rows += result.get("rows_stored") or 0
        else:
            failed.append(term)
    return {"status": "ok", "terms_backfilled": len(ok), "terms_failed": len(failed),
           "failed_terms": failed, "rows_stored": total_rows}


def _as_of_from_row(row: Dict[str, Any]) -> Optional[_dt.date]:
    sim = row.get("simulation_date")
    if not sim:
        return None
    try:
        return _dt.date.fromisoformat(str(sim)[:10])
    except ValueError:
        return None


def backfill_row_features(row: Dict[str, Any], brand_series=None, category_series=None
                          ) -> Optional[Dict[str, Any]]:
    """Pure function: given ONE existing backtest_rows row (dict with at least simulation_date
    and features_snapshot), returns the row with its features_snapshot patched with freshly
    computed calendar/trend features AT THE ROW'S OWN as-of date — or None if the row has no
    usable simulation_date (never fabricates an as-of). Series are injectable so a caller can
    pre-fetch once per (brand, category) across many rows sharing a term, same optimization as
    scout/backtest.py's _fetch_trend_series."""
    as_of = _as_of_from_row(row)
    if as_of is None:
        return None
    snapshot = dict(row.get("features_snapshot") or {})
    brand = snapshot.get("brand") or row.get("brand")
    category = snapshot.get("category") or row.get("category")

    try:
        from signals import calendar as signals_calendar
        snapshot.update(signals_calendar.calendar_features(as_of))
    except Exception as e:
        log.warning("calendar_features failed for %s (non-fatal): %s", row.get("asin"), e)

    try:
        brand_t = trends.trends_features(brand, as_of, series=brand_series) if brand else {}
        cat_t = trends.trends_features(category, as_of, series=category_series) if category else {}
        snapshot.update({
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
        })
    except Exception as e:
        log.warning("trends_features failed for %s (non-fatal): %s", row.get("asin"), e)

    patched = dict(row)
    patched["features_snapshot"] = snapshot
    return patched


def backfill_backtest_rows(rows: Optional[List[Dict[str, Any]]] = None,
                           read_fn: Optional[Callable] = None,
                           write_fn: Optional[Callable] = None) -> Dict[str, Any]:
    """Phase 2: patch every existing backtest_rows row's features_snapshot with date-correct
    calendar/trend features, re-upserting on the row's existing (asin, simulation_date) natural
    key. Fetches each distinct (brand, category)'s Trends series ONCE (not once per row) — the
    same N+1 avoidance as scout/backtest.py's live path. NEVER raises; a row with no usable
    simulation_date is skipped and counted honestly, never silently dropped without report."""
    if rows is None:
        rows = (read_fn or db.all_backtest_rows_for_backfill)()
    if not rows:
        return {"status": "ok", "rows_read": 0, "rows_patched": 0, "rows_skipped": 0}

    series_cache: Dict[str, List[Any]] = {}

    def _cached_series(term: Optional[str]):
        if not term:
            return []
        if term not in series_cache:
            try:
                raw = db.trends_series_for(term)
                series_cache[term] = [(_dt.date.fromisoformat(r["week_start"]), float(r["interest"]))
                                      for r in raw]
            except Exception as e:
                log.warning("trends series fetch failed for %r (non-fatal): %s", term, e)
                series_cache[term] = []
        return series_cache[term]

    patched_rows = []
    skipped = 0
    for row in rows:
        snapshot = row.get("features_snapshot") or {}
        brand = snapshot.get("brand") or row.get("brand")
        category = snapshot.get("category") or row.get("category")
        patched = backfill_row_features(
            row, brand_series=_cached_series(brand), category_series=_cached_series(category))
        if patched is None:
            skipped += 1
            continue
        patched_rows.append(patched)

    write = write_fn or db.upsert_backtest_rows
    written = write(patched_rows) if patched_rows else 0
    return {"status": "ok", "rows_read": len(rows), "rows_patched": written,
           "rows_skipped": skipped, "distinct_terms_fetched": len(series_cache)}
