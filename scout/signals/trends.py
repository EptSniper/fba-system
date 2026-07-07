"""
scout/signals/trends.py — weekly Google Trends collector + features (Session 55, free
signal-type features).

pytrends is an UNOFFICIAL scraping wrapper around Google Trends' internal API (no official API
exists) — treated accordingly: every live call goes through _fetch_with_backoff (exponential
backoff + per-request jitter across MAX_RETRIES attempts). A week that still fails after retries
degrades HONESTLY: trends_features() below falls back to the last stored value and flags the
result stale=True rather than blocking the caller or fabricating a fresh number.

Vocabulary (ai-brain.json learning.sampling + db.recent_brand_vocabulary): every brand seen
recently in leads/deal_hints (rolling, capped ~200 — the oldest brands age out as newer ones push
the cap) + the ~10 learning.sampling categories.

LEAKAGE SAFETY: trends_features(term, as_of, ...) only ever reads weekly points whose ENTIRE
aggregation window has closed strictly before as_of (`d + WEEK_LENGTH_DAYS <= as_of` — a weekly
point aggregates a whole week, not a single day; see trends_features' own docstring for the
2026-07-06 review fix that tightened this from a same-day `d < as_of` check). This is what makes
the 5-year backfill (trends_backfill.py) safe to run against historical rows: the SAME function
computes a live feature today and a historical feature for a 2024 backtest window, and can never
see either's future.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import random
import time
from typing import Any, Dict, List, Optional, Tuple

import db

log = logging.getLogger("scout.signals.trends")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAIN_PATH = os.path.join(HERE, "..", "learning-hub", "data", "ai-brain.json")

DEFAULT_TIMEFRAME = "today 5-y"   # pytrends' own syntax for "the trailing 5 years"
MAX_VOCAB_BRANDS = 200
MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 2.0
SPIKE_THRESHOLD = 2.0
STALE_AFTER_DAYS = 14   # a week's worth of slack past the expected weekly refresh cadence
WEEK_LENGTH_DAYS = 7    # a Trends weekly bucket aggregates [week_start, week_start+6]

try:
    from pytrends.request import TrendReq
    _PYTRENDS = True
except Exception:  # pragma: no cover - optional dependency, not installed in every environment
    TrendReq = None
    _PYTRENDS = False


def _require_pytrends():
    if not _PYTRENDS:
        raise ImportError("The 'pytrends' package is not installed. Run: pip install pytrends")


def get_client():
    """Construct a pytrends TrendReq client. Raises a clear error if the package is missing —
    callers (collect_weekly/backfill_term) catch this the same way they catch any other
    per-term failure, never crashing a batch over one missing dependency."""
    _require_pytrends()
    return TrendReq(hl="en-US", tz=360)


def sampling_config() -> Dict[str, Any]:
    """learning.sampling from the brain (this module only needs `categories`). {} if unavailable."""
    try:
        with open(BRAIN_PATH, encoding="utf-8") as f:
            brain = json.load(f) or {}
        return (brain.get("learning") or {}).get("sampling") or {}
    except Exception:
        return {}


def vocabulary(max_brands: int = MAX_VOCAB_BRANDS) -> List[Tuple[str, str]]:
    """[(term_kind, term), ...] — the ~10 learning.sampling categories + up to `max_brands`
    recently-seen brands. Categories first (a stable, small set); brands second (the rolling,
    capped part of the vocabulary)."""
    cats = sampling_config().get("categories") or []
    out: List[Tuple[str, str]] = [("category", c) for c in cats]
    out += [("brand", b) for b in db.recent_brand_vocabulary(limit=max_brands)]
    return out


def _jittered_backoff(attempt: int) -> float:
    return BASE_BACKOFF_SECONDS * (2 ** attempt) + random.uniform(0, 1.0)


def _dataframe_to_weekly_series(df, term: str) -> List[Tuple[_dt.date, float]]:
    """pytrends' interest_over_time() returns a pandas DataFrame indexed by timestamp, one
    column per keyword + 'isPartial'. Converts to [(week_start_date, interest_value), ...],
    dropping the trailing partial-week point (pytrends flags the CURRENT, still-accumulating
    week as isPartial=True — including it would plant a noisy, not-yet-final value at the
    series' leading edge)."""
    out: List[Tuple[_dt.date, float]] = []
    for idx, row in df.iterrows():
        if bool(row.get("isPartial", False)):
            continue
        val = row.get(term)
        if val is None:
            continue
        d = idx.date() if hasattr(idx, "date") else idx
        out.append((d, float(val)))
    return out


def fetch_weekly_interest(client, term: str, timeframe: str = DEFAULT_TIMEFRAME,
                          max_retries: int = MAX_RETRIES,
                          sleep_fn=None) -> Optional[List[Tuple[_dt.date, float]]]:
    """One term's weekly interest-over-time series, with exponential backoff + jitter across
    `max_retries` attempts. Returns None (never raises) once retries are exhausted — the caller
    degrades to the last stored value rather than blocking or fabricating a number. sleep_fn is
    injectable so tests never actually sleep."""
    sleep_fn = sleep_fn or time.sleep
    last_err: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            client.build_payload([term], timeframe=timeframe)
            df = client.interest_over_time()
            if df is None or df.empty:
                return []
            return _dataframe_to_weekly_series(df, term)
        except Exception as e:
            last_err = e
            if attempt < max_retries - 1:
                sleep_fn(_jittered_backoff(attempt))
    log.warning("pytrends fetch failed for %r after %d attempts: %s", term, max_retries, last_err)
    return None


def collect_weekly(terms: Optional[List[Tuple[str, str]]] = None, client=None,
                   sleep_fn=None) -> Dict[str, Any]:
    """Fetch + store one fresh weekly point per (term_kind, term), per-term isolated — one
    failing term never blocks the rest of the batch (same philosophy as backtest.py's per-brand
    sampling loop). terms defaults to vocabulary(). NEVER raises."""
    if terms is None:
        terms = vocabulary()
    if client is None:
        try:
            client = get_client()
        except Exception as e:
            return {"status": "disabled", "reason": str(e), "fetched": [], "failed": [], "rows_stored": 0}

    fetched: List[str] = []
    failed: List[str] = []
    rows: List[Dict[str, Any]] = []
    for term_kind, term in terms:
        try:
            series = fetch_weekly_interest(client, term, sleep_fn=sleep_fn)
        except Exception as e:
            log.warning("collect_weekly: unexpected error for %r (non-fatal): %s", term, e)
            series = None
        if series is None:
            failed.append(term)
            continue
        fetched.append(term)
        for d, v in series:
            rows.append({"term": term, "term_kind": term_kind,
                        "week_start": d.isoformat() if hasattr(d, "isoformat") else str(d),
                        "interest": v})
    stored = db.upsert_trends_series(rows) if rows else 0
    return {"status": "ok", "fetched": fetched, "failed": failed, "rows_stored": stored}


def backfill_term(term: str, term_kind: str, client=None,
                  timeframe: str = DEFAULT_TIMEFRAME, sleep_fn=None) -> Dict[str, Any]:
    """Pull ONE term's full historical series (default 5 years — Google Trends serves this
    directly in one call, no need to reconstruct week-by-week) and store it. A ONE-TIME cost per
    term, not a recurring one — collect_weekly's regular cadence only needs the latest week
    after this has run once."""
    if client is None:
        try:
            client = get_client()
        except Exception as e:
            return {"term": term, "status": "disabled", "reason": str(e), "rows_stored": 0}
    series = fetch_weekly_interest(client, term, timeframe=timeframe, sleep_fn=sleep_fn)
    if series is None:
        return {"term": term, "status": "failed", "rows_stored": 0}
    rows = [{"term": term, "term_kind": term_kind,
            "week_start": d.isoformat() if hasattr(d, "isoformat") else str(d), "interest": v}
           for d, v in series]
    stored = db.upsert_trends_series(rows) if rows else 0
    return {"term": term, "status": "ok", "rows_stored": stored, "weeks": len(rows)}


# --- features (leakage-safe: only ever reads points strictly before as_of) ------------------
def trends_features(term: str, as_of: _dt.date,
                    series: Optional[List[Tuple[_dt.date, float]]] = None) -> Dict[str, Any]:
    """interest_now_vs_90d_avg / slope_4wk / seasonal_z / spike_flag for `term` at `as_of`,
    using ONLY weekly points whose ENTIRE aggregation window has closed strictly before as_of.
    series is injectable (already-fetched from Supabase in bulk, e.g. by trends_backfill.py) or
    defaults to a live db.trends_series_for() read. `stale` is True when the most recent
    available point is more than STALE_AFTER_DAYS old — a failed live refresh still leaves the
    LAST KNOWN values usable, just honestly flagged, never silently blocking or fabricating a
    fresher number.

    LEAKAGE FIX (review, 2026-07-06): a Trends weekly point aggregates search interest over
    [week_start, week_start + WEEK_LENGTH_DAYS - 1] — a whole week, not a single day. The
    original boundary (`d < as_of`) admitted the bucket CONTAINING as_of whenever its week_start
    happened to fall before as_of, even though that bucket's own aggregation window still
    extends PAST as_of for any as_of that isn't itself a week boundary — leaking up to 6 days of
    future search interest (e.g. a Black-Friday-week spike) into a mid-week backtest simulation
    date. The fix requires the bucket to be FULLY CLOSED (`d + WEEK_LENGTH_DAYS <= as_of`) —
    the same strict leakage boundary scout/backtest.py's feature builder enforces for Keepa
    history, just accounting for a week's own span instead of treating it as a point-in-time."""
    if series is None:
        raw = db.trends_series_for(term, before=as_of.isoformat())
        series = [(_dt.date.fromisoformat(r["week_start"]), float(r["interest"])) for r in raw]
    week_span = _dt.timedelta(days=WEEK_LENGTH_DAYS)
    past = sorted((d, v) for d, v in series if d + week_span <= as_of)
    if not past:
        return {"interest_now_vs_90d_avg": None, "slope_4wk": None, "seasonal_z": None,
                "spike_flag": None, "stale": True}

    latest_date, latest_val = past[-1]
    stale = (as_of - latest_date).days > STALE_AFTER_DAYS

    window90 = [v for d, v in past if (latest_date - d).days <= 90]
    avg90 = sum(window90) / len(window90) if window90 else None
    ratio = round(latest_val / avg90, 3) if avg90 else None

    last4 = [v for _, v in past[-4:]]
    slope = None
    if len(last4) >= 2:
        diffs = [last4[i + 1] - last4[i] for i in range(len(last4) - 1)]
        slope = round(sum(diffs) / len(diffs), 3)

    iso_week = latest_date.isocalendar()[1]
    same_week = [v for d, v in past if d.isocalendar()[1] == iso_week and d.year != latest_date.year]
    seasonal_z = None
    if len(same_week) >= 2:
        mean = sum(same_week) / len(same_week)
        var = sum((x - mean) ** 2 for x in same_week) / len(same_week)
        std = var ** 0.5
        seasonal_z = round((latest_val - mean) / std, 3) if std > 0 else 0.0

    spike = ratio is not None and ratio > SPIKE_THRESHOLD

    return {"interest_now_vs_90d_avg": ratio, "slope_4wk": slope, "seasonal_z": seasonal_z,
           "spike_flag": spike, "stale": stale}


# --- CLI entry point (review fix, 2026-07-06) -----------------------------------------------
# Before this, collect_weekly() had NO scheduled caller anywhere — trends_series stayed
# permanently empty, so all 8 Trends model features were constant-zero at every retrain and the
# ranker report's kill-rule would have flagged them "near-zero — removal candidate" despite
# never having been fed any data. .github/workflows/trends-collect.yml runs this weekly (matching
# Google Trends' own weekly bucket granularity) via `python3 -m signals.trends` from scout/.
def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(HERE, ".env"))
    except Exception:
        pass
    result = collect_weekly()
    print(json.dumps(result, indent=2, default=str))
    # "disabled" (pytrends/env not available) is an HONEST no-op, not a CI failure — same
    # convention as collect_hourly.main()'s "no KEEPA_KEY" case. Per-term failures are tracked
    # in result["failed"] without failing the whole run (per-term isolation is the point).
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
