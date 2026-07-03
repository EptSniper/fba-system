"""
labels.py — the two parallel truth systems.

WEAK public-proxy labels (from Keepa/public snapshots) drive DISCOVERY. They never
pretend to know private margins. STRONG realized labels (your own account outcomes,
or analyst decisions until SP-API is wired) are what should ultimately drive buying
and retraining. The paper warns teams fail when they collapse these too early.

Also enforces three labeling rules: censor stockout windows, never leak post-launch
PPC into a pre-launch model, and exclude/negative-label compliance-blocked products.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select

import config
import database as db
import features as feat
import gates

WEAK_VERSION = "weak-v1"
STRONG_VERSION = "strong-v1"

# analyst decision -> realized success (None = skip / no label)
DECISION_TO_LABEL = {
    "approve": True,
    "reject": False,
    "false_positive": False,
    "margin_issue": False,
    "compliance_issue": False,
    "supplier_issue": False,
    "defer": None,
}


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def weak_label(f: Dict[str, Any], snapshot: Dict[str, Any]) -> Tuple[float, bool, Dict[str, float]]:
    """Compute the weak public-proxy success score and its components."""
    rank_mean = f.get("rank_mean_30", 0.0) or 0.0
    vol_norm = _clamp((f.get("rank_vol_30", 0.0) or 0.0) / (rank_mean + 1.0))
    slope_sig = 1.0 if (f.get("rank_slope_30", 0.0) or 0.0) < 0 else 0.5
    rank_stability = _clamp(0.5 * (1 - vol_norm) + 0.3 * f.get("rank_percentile_cat", 0.5) + 0.2 * slope_sig)

    price_resilience = _clamp(f.get("price_resilience", 0.0))
    buybox_continuity = _clamp(1.0 - (f.get("oos_90", 0.0) or 0.0) / 100.0)

    rv = f.get("review_velocity_30", 0.0) or 0.0
    if rv <= 0:
        review_health = 0.2
    elif rv > 200:
        review_health = 0.3          # suspicious spike -> risk, not reward
    else:
        review_health = _clamp(rv / 50.0)

    offer_crowding = _clamp((f.get("offer_count", 0.0) or 0.0) / max(config.CRITERIA["max_offers"], 1))
    comp_risk, _ = gates.compliance_risk(snapshot)

    w = config.WEAK_LABEL_WEIGHTS
    score = (w["rank_stability"] * rank_stability
             + w["price_resilience"] * price_resilience
             + w["buybox_continuity"] * buybox_continuity
             + w["review_velocity_health"] * review_health
             - w["offer_crowding_penalty"] * offer_crowding
             - w["compliance_risk_penalty"] * comp_risk)
    score = round(_clamp(score), 4)
    components = {
        "rank_stability": round(rank_stability, 3),
        "price_resilience": round(price_resilience, 3),
        "buybox_continuity": round(buybox_continuity, 3),
        "review_velocity_health": round(review_health, 3),
        "offer_crowding": round(offer_crowding, 3),
        "compliance_risk": round(comp_risk, 3),
    }
    return score, (score >= config.WEAK_SUCCESS_THRESHOLD), components


def strong_label(realized: Dict[str, Any]) -> Optional[bool]:
    """Strong realized success from owned-account outcomes over a horizon."""
    s = config.STRONG_LABEL
    if realized.get("compliance_flag"):
        return False
    try:
        return bool(
            realized.get("contribution_margin", 0) >= s["min_contribution_margin"]
            and realized.get("units_sold", 0) >= s["min_units"]
            and realized.get("featured_offer_share", 0) >= s["min_featured_offer_share"]
            and realized.get("return_rate", 1.0) <= s["max_return_rate"]
        )
    except Exception:
        return None


def write_weak_labels(feature_rows: List[Dict[str, Any]],
                      snapshots_by_asin: Dict[str, Dict[str, Any]]) -> int:
    """Persist weak proxy labels (discovery training signal) with captured features."""
    today = dt.date.today()
    n = 0
    for f in feature_rows:
        asin = f.get("asin")
        snap = snapshots_by_asin.get(asin, {})
        score, success, _ = weak_label(f, snap)
        comp_risk, _ = gates.compliance_risk(snap)
        db.upsert_label({
            "asin": asin, "marketplace": config.KEEPA_DOMAIN,
            "label_end_date": today, "horizon_days": config.PRIMARY_HORIZON,
            "label_version": WEAK_VERSION,
            "success_proxy": success, "success_realized": None,
            "proxy_score": score, "contribution_margin": f.get("margin_est"),
            "units_sold": int(f.get("est_sales", 0) or 0), "return_rate": None,
            "compliance_flag": comp_risk >= 1.0, "censored": False,
            "features": {c: f.get(c) for c in feat.FEATURE_COLUMNS},
        })
        n += 1
    return n


def record_outcome(asin: str, decision: Optional[str] = None,
                   realized: Optional[Dict[str, Any]] = None, notes: str = "",
                   analyst_id: str = "operator") -> Dict[str, Any]:
    """
    Record a STRONG label from either an analyst decision or realized account data.
    Captures the ASIN's current features so the training row is self-contained.
    """
    db.init_db()
    # capture current features (graceful if no snapshot history yet)
    try:
        frows = feat.build_features([asin])
    except Exception:
        frows = []
    fr = frows[0] if frows else {c: None for c in feat.FEATURE_COLUMNS}

    if realized is not None:
        label = strong_label(realized)
        compliance_flag = bool(realized.get("compliance_flag"))
        censored = bool(realized.get("censored"))
        contribution = realized.get("contribution_margin")
        units = realized.get("units_sold")
        returns = realized.get("return_rate")
    else:
        label = DECISION_TO_LABEL.get((decision or "").lower())
        compliance_flag = decision in ("compliance_issue",)
        censored = False
        contribution = fr.get("margin_est")
        units = int(fr.get("est_sales", 0) or 0)
        returns = None
        db.add_feedback(asin, decision or "reject", notes=notes, analyst_id=analyst_id)

    if label is None:   # 'defer' -> no training label
        return {"asin": asin, "labeled": False, "reason": "deferred / no label"}

    db.upsert_label({
        "asin": asin, "marketplace": config.KEEPA_DOMAIN,
        "label_end_date": dt.date.today(), "horizon_days": config.PRIMARY_HORIZON,
        "label_version": STRONG_VERSION,
        "success_proxy": None, "success_realized": bool(label),
        "proxy_score": None, "contribution_margin": contribution,
        "units_sold": units, "return_rate": returns,
        "compliance_flag": compliance_flag, "censored": censored,
        "features": {c: fr.get(c) for c in feat.FEATURE_COLUMNS},
    })
    return {"asin": asin, "labeled": True, "success_realized": bool(label)}


def training_rows(prefer_strong: bool = True) -> List[Dict[str, Any]]:
    """
    Assemble labeled feature rows for the classifier. Prefers STRONG realized labels;
    falls back to WEAK proxy labels for ASINs without a realized outcome. Excludes
    compliance-flagged and stockout-censored windows. Strong labels get higher weight.
    """
    t = db.product_label_window
    with db.get_engine().connect() as conn:
        rows = conn.execute(select(t).where(t.c.compliance_flag != True,  # noqa: E712
                                            t.c.censored != True)).mappings().all()  # noqa: E712
    by_asin: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        r = dict(r)
        asin = r["asin"]
        is_strong = r["success_realized"] is not None
        keep = by_asin.get(asin)
        # prefer strong over weak; otherwise most recent
        if keep is None:
            by_asin[asin] = r
        else:
            keep_strong = keep["success_realized"] is not None
            if is_strong and not keep_strong:
                by_asin[asin] = r
            elif is_strong == keep_strong and r["label_end_date"] >= keep["label_end_date"]:
                by_asin[asin] = r

    out = []
    for r in by_asin.values():
        feats = r.get("features") or {}
        if isinstance(feats, str):
            import json
            try:
                feats = json.loads(feats)
            except Exception:
                feats = {}
        if r["success_realized"] is not None:
            label = int(bool(r["success_realized"]))
            weight = 3.0
        elif r["success_proxy"] is not None and prefer_strong:
            label = int(bool(r["success_proxy"]))
            weight = 1.0
        else:
            continue
        row = {c: feats.get(c) for c in feat.FEATURE_COLUMNS}
        row["label"] = label
        row["weight"] = weight
        # realized regression targets (for the quantile regressors), when present
        row["units_sold"] = r.get("units_sold")
        row["contribution_margin"] = r.get("contribution_margin")
        out.append(row)
    return out
