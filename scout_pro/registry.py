"""
registry.py — model versioning + champion/challenger promotion.

Gated retraining, not uncontrolled online learning: every retrain produces a
versioned CHALLENGER, which is only promoted to CHAMPION if it beats the current
champion's cross-validated PR-AUC by at least config.PROMOTION_MIN_GAIN. The first
ever model is promoted automatically. All versions + metrics are kept for audit.
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Any, Dict, Optional, Tuple

import config
import database as db
import models


def _version() -> str:
    return dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")


def _model_path(name: str, version: str) -> str:
    return os.path.join(config.MODEL_REGISTRY_DIR, name, f"{version}.joblib")


def get_champion(name: str = "classifier"):
    """Return (model, record) for the current champion, or (None, None)."""
    rec = db.registry_champion(name)
    if not rec:
        return None, None
    return models.load_model(rec["path"]), rec


def train_and_gate(name: str = "classifier") -> Dict[str, Any]:
    """
    Train a challenger from accumulated labels and decide promotion.
    Returns an audit dict describing what happened.
    """
    db.init_db()
    import labels  # local import avoids a cycle (labels -> features -> db)
    rows = labels.training_rows()

    model, metrics = models.train_classifier(rows)
    if model is None:
        return {"promoted": False, "trained": False, "reason": metrics.get("reason"),
                "labels": len(rows)}

    version = _version()
    path = _model_path(name, version)
    models.save_model(model, path)
    db.registry_add(name, version, metrics.get("model", "?"), path, metrics, is_champion=False)

    champ = db.registry_champion(name)
    challenger_auc = metrics.get("pr_auc_cv")

    # First model ever -> promote automatically.
    if champ is None:
        db.registry_promote(name, version)
        return {"promoted": True, "first_model": True, "version": version, "metrics": metrics}

    champ_auc = (champ.get("metrics") or {}).get("pr_auc_cv")
    # If we can't compare (NaN/None), keep the incumbent to be safe.
    if challenger_auc is None or champ_auc is None:
        return {"promoted": False, "version": version, "reason": "no comparable PR-AUC; kept champion",
                "challenger_metrics": metrics}

    gain = round(challenger_auc - champ_auc, 4)
    if gain >= config.PROMOTION_MIN_GAIN:
        db.registry_promote(name, version)
        return {"promoted": True, "version": version, "pr_auc_gain": gain,
                "challenger_pr_auc": challenger_auc, "champion_pr_auc": champ_auc}
    return {"promoted": False, "version": version, "pr_auc_gain": gain,
            "reason": f"gain {gain} < {config.PROMOTION_MIN_GAIN}; kept champion",
            "challenger_pr_auc": challenger_auc, "champion_pr_auc": champ_auc}


def train_auxiliary() -> Dict[str, Any]:
    """Train+save ranker and a units regressor as 'latest' (no gate needed)."""
    import labels
    rows = labels.training_rows()
    out: Dict[str, Any] = {}
    ranker = models.train_ranker(rows)
    if ranker is not None:
        v = _version()
        p = _model_path("ranker", v)
        models.save_model(ranker, p)
        db.registry_add("ranker", v, "LGBMRanker", p, {"n": len(rows)}, is_champion=True)
        db.registry_promote("ranker", v)
        out["ranker"] = v
    reg = models.train_quantile_regressor(rows, target="units_sold", alpha=0.5)
    if reg is not None:
        v = _version()
        p = _model_path("regressor_units", v)
        models.save_model(reg, p)
        db.registry_add("regressor_units", v, "quantile", p, {"n": len(rows)}, is_champion=True)
        db.registry_promote("regressor_units", v)
        out["regressor_units"] = v
    return out
