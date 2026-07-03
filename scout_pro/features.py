"""
features.py — feature engineering (windowed, relative, portfolio-aware).

The paper's core discipline: keep PRE-LAUNCH and POST-LAUNCH feature sets separate
so post-buy signals (PPC, realized conversion) never leak into a sourcing model.
This module builds the PRE-LAUNCH set from public Keepa snapshot history only.

Most-valuable features are windowed/relative, not raw: rolling means/slopes/
volatility of rank/price/reviews/offers, rank-percentile within category,
price-to-buy-box distance, review-velocity, listing-quality, and fee-aware margin.
With a single snapshot (cold start) windows degrade gracefully to current values.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

import config
import database as db
import fees

try:
    import numpy as np
    import pandas as pd
    _PANDAS = True
except Exception:  # pragma: no cover
    _PANDAS = False

# Canonical PRE-LAUNCH feature order. Models train/predict on exactly these.
FEATURE_COLUMNS = [
    "price", "est_sales", "review_count", "rating", "weight_lb", "offer_count",
    "margin_est", "contribution_margin",
    "rank_mean_30", "rank_slope_30", "rank_vol_30", "rank_percentile_cat",
    "price_to_buybox", "price_resilience", "review_velocity_30",
    "offer_accel_30", "image_count", "bullet_count", "oos_90",
]


def _num(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def load_history(asins: List[str]):
    """Return a DataFrame of snapshot history for the given ASINs (or None)."""
    if not _PANDAS:
        return None
    from sqlalchemy import select
    t = db.asin_snapshot_daily
    with db.get_engine().connect() as conn:
        rows = conn.execute(
            select(t).where(t.c.asin.in_(list(asins))).order_by(t.c.snapshot_date)
        ).mappings().all()
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()


def _slope(dates, values) -> float:
    """Per-day linear slope via least squares; 0 if <2 points."""
    if len(values) < 2:
        return 0.0
    x = np.array([(d - dates[0]).days for d in dates], dtype=float)
    y = np.array(values, dtype=float)
    if np.all(x == x[0]):
        return 0.0
    try:
        return float(np.polyfit(x, y, 1)[0])
    except Exception:
        return 0.0


def _window(df, col, days, as_of):
    cutoff = as_of - dt.timedelta(days=days)
    w = df[(df["snapshot_date"] >= cutoff)]
    return w[col].dropna()


def build_features(asins: List[str], as_of: Optional[dt.date] = None) -> List[Dict[str, Any]]:
    """Compute the pre-launch feature vector per ASIN. Returns list of dicts
    with FEATURE_COLUMNS + 'asin' (+ 'category_id' for portfolio percentile)."""
    if not _PANDAS:
        raise ImportError("pandas/numpy required for feature engineering (pip install).")
    hist = load_history(asins)
    out: List[Dict[str, Any]] = []
    if hist is None or hist.empty:
        return out
    hist["snapshot_date"] = pd.to_datetime(hist["snapshot_date"]).dt.date
    as_of = as_of or hist["snapshot_date"].max()

    # category rank distribution at as_of for percentile-within-category
    latest = hist[hist["snapshot_date"] == as_of]
    cat_ranks = latest.dropna(subset=["sales_rank"]).groupby("category_id")["sales_rank"]

    for asin, g in hist.groupby("asin"):
        g = g.sort_values("snapshot_date")
        cur = g.iloc[-1]
        price = cur.get("buy_box_price") or cur.get("price_new_fba") or cur.get("price_amazon")
        weight = cur.get("weight_lb")
        dates = list(g["snapshot_date"])

        rank_30 = _window(g, "sales_rank", 30, as_of)
        price_30 = _window(g, "buy_box_price", 30, as_of)
        rev_30 = _window(g, "review_count", 30, as_of)
        off_30 = _window(g, "offer_count_new", 30, as_of)

        rank_slope = _slope(dates[-len(rank_30):], list(rank_30)) if len(rank_30) >= 2 else 0.0
        rank_vol = float(rank_30.std()) if len(rank_30) >= 2 else 0.0
        price_mean = float(price_30.mean()) if len(price_30) else _num(price)
        price_vol = float(price_30.std()) if len(price_30) >= 2 else 0.0
        price_resilience = max(0.0, 1.0 - (price_vol / price_mean)) if price_mean else 0.0
        review_velocity = (float(rev_30.iloc[-1]) - float(rev_30.iloc[0])) if len(rev_30) >= 2 else 0.0
        offer_accel = (float(off_30.iloc[-1]) - float(off_30.iloc[0])) if len(off_30) >= 2 else 0.0

        # rank percentile within its category (lower rank = better -> invert)
        cat = cur.get("category_id")
        pct = 0.5
        if cat in cat_ranks.groups and cur.get("sales_rank") is not None:
            ranks = cat_ranks.get_group(cat)
            pct = float((ranks > cur["sales_rank"]).mean())  # share of worse-ranked peers

        bb = cur.get("buy_box_price")
        new = cur.get("price_new_fba")
        price_to_buybox = abs(_num(new) - _num(bb)) / _num(bb) if bb else 0.0

        raw = cur.get("raw") or {}
        if isinstance(raw, str):
            try:
                import ast
                raw = ast.literal_eval(raw)
            except Exception:
                raw = {}
        oos_90 = _num(raw.get("outOfStockPercentage90"))

        out.append({
            "asin": asin,
            "category_id": cat,
            "price": _num(price),
            "est_sales": _num(cur.get("est_sales")),
            "review_count": _num(cur.get("review_count")),
            "rating": _num(cur.get("rating")),
            "weight_lb": _num(weight),
            "offer_count": _num(cur.get("offer_count_new")),
            "margin_est": _num(fees.net_margin(price, weight)),
            "contribution_margin": _num(fees.contribution_margin_dollars(price, weight)),
            "rank_mean_30": float(rank_30.mean()) if len(rank_30) else _num(cur.get("sales_rank")),
            "rank_slope_30": rank_slope,
            "rank_vol_30": rank_vol,
            "rank_percentile_cat": pct,
            "price_to_buybox": price_to_buybox,
            "price_resilience": price_resilience,
            "review_velocity_30": review_velocity,
            "offer_accel_30": offer_accel,
            "image_count": _num(cur.get("image_count")),
            "bullet_count": _num(cur.get("bullet_count")),
            "oos_90": oos_90,
        })
    return out


def to_matrix(feature_rows: List[Dict[str, Any]]):
    """Return (X ndarray, asins list) in FEATURE_COLUMNS order for model input."""
    if not _PANDAS:
        raise ImportError("numpy required.")
    asins = [r.get("asin") for r in feature_rows]
    X = np.array([[_num(r.get(c)) for c in FEATURE_COLUMNS] for r in feature_rows], dtype=float)
    return X, asins
