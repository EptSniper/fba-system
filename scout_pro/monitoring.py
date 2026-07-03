"""
monitoring.py — drift + data-quality (retrain triggers).

Compares the feature distribution the champion was trained on (baseline = labeled
rows) against the latest ingested snapshots (current) using Population Stability
Index. Material drift (PSI >= config.DRIFT_PSI_THRESHOLD) on key features is one of
the triggers for a gated retrain, alongside the fixed schedule.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List

from sqlalchemy import select

import config
import database as db
import evaluation
import features as feat


def _latest_feature_rows(days: int = 1) -> List[Dict[str, Any]]:
    t = db.asin_snapshot_daily
    cutoff = dt.date.today() - dt.timedelta(days=days)
    with db.get_engine().connect() as conn:
        asins = [r[0] for r in conn.execute(
            select(t.c.asin).where(t.c.snapshot_date >= cutoff).distinct()
        ).all()]
    if not asins:
        return []
    try:
        return feat.build_features(asins)
    except Exception:
        return []


def feature_drift() -> Dict[str, Any]:
    """PSI per feature between labeled baseline and latest snapshots."""
    import labels
    baseline = labels.training_rows()
    current = _latest_feature_rows()
    if len(baseline) < 10 or len(current) < 10:
        return {"drift_checked": False, "reason": "insufficient baseline/current rows",
                "baseline_n": len(baseline), "current_n": len(current)}
    drifted = evaluation.population_drift(baseline, current, feat.FEATURE_COLUMNS,
                                          config.DRIFT_PSI_THRESHOLD)
    return {"drift_checked": True, "drifted_features": drifted,
            "drift_detected": len(drifted) > 0,
            "baseline_n": len(baseline), "current_n": len(current)}


def data_quality(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    """Null-rate per feature for the current batch (cheap whylogs-style profile)."""
    if not rows:
        return {}
    n = len(rows)
    return {c: round(sum(1 for r in rows if r.get(c) in (None, 0)) / n, 3)
            for c in feat.FEATURE_COLUMNS}
