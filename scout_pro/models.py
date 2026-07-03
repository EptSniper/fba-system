"""
models.py — the layered model stack (paper's recommended initial pipeline).

  1. Calibrated viability classifier  -> P(90-day success), isotonic-calibrated
  2. Quantile regressors               -> expected units / contribution margin
  3. LambdaMART ranker                 -> orders candidates for the alert queue

LightGBM is the primary engine (binary, quantile, lambdarank); scikit-learn is a
full fallback so the system runs without LightGBM. With no trained model the
pipeline falls back to the transparent rule score. Models persist via joblib;
versioning/champion-challenger lives in registry.py.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import config
import evaluation
from features import FEATURE_COLUMNS

try:
    import numpy as np
    import joblib
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_predict
    _SK = True
except Exception:  # pragma: no cover
    _SK = False

try:
    import lightgbm as lgb
    _LGB = True
except Exception:  # pragma: no cover
    _LGB = False


def available() -> bool:
    return _SK


def engine() -> str:
    return "lightgbm" if _LGB else ("sklearn" if _SK else "none")


# ---------------------------------------------------------------------------
# matrix helpers
# ---------------------------------------------------------------------------
def _num(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def build_X(rows: List[Dict[str, Any]]):
    return np.array([[_num(r.get(c)) for c in FEATURE_COLUMNS] for r in rows], dtype=float)


# ---------------------------------------------------------------------------
# 1. Calibrated viability classifier
# ---------------------------------------------------------------------------
def _base_classifier(n: int, n_pos: int, n_neg: int):
    if _LGB:
        # Params adapted from the paper; min_data_in_leaf scaled for small data.
        spw = float(min(max(n_neg / max(n_pos, 1), 2), 10))
        return lgb.LGBMClassifier(
            objective="binary", learning_rate=0.03, num_leaves=31, max_depth=8,
            min_child_samples=max(5, min(200, n // 10)), subsample=0.8,
            colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=1.0,
            n_estimators=400, scale_pos_weight=spw, verbosity=-1,
        )
    if n >= 60:
        return GradientBoostingClassifier(random_state=42)
    return LogisticRegression(max_iter=1000, class_weight="balanced")


def train_classifier(rows: List[Dict[str, Any]]) -> Tuple[Optional[Any], Dict[str, Any]]:
    """Fit an isotonic/sigmoid-calibrated viability classifier. Returns (model, metrics)."""
    if not _SK:
        return None, {"trained": False, "reason": "scikit-learn not installed"}
    rows = [r for r in rows if r.get("label") in (0, 1)]
    n = len(rows)
    if n < config.MIN_LABELS_TO_TRAIN:
        return None, {"trained": False, "reason": f"need >= {config.MIN_LABELS_TO_TRAIN} labels, have {n}"}
    y = np.array([int(r["label"]) for r in rows])
    if len(set(y.tolist())) < 2:
        return None, {"trained": False, "reason": "need both success and failure labels"}
    X = build_X(rows)
    w = np.array([_num(r.get("weight", 1.0)) for r in rows])
    n_pos, n_neg = int(y.sum()), int((1 - y).sum())

    base = _base_classifier(n, n_pos, n_neg)
    # isotonic needs reasonable data; use sigmoid (Platt) when small
    method = "isotonic" if n >= 200 else "sigmoid"
    folds = min(3, n_pos, n_neg)
    folds = max(folds, 2)
    try:
        calib = CalibratedClassifierCV(estimator=base, method=method, cv=folds)
    except TypeError:  # older sklearn
        calib = CalibratedClassifierCV(base_estimator=base, method=method, cv=folds)
    try:
        calib.fit(X, y, sample_weight=w)
    except Exception:
        calib.fit(X, y)

    # honest evaluation: cross-validated PR-AUC + calibration error
    metrics: Dict[str, Any] = {"trained": True, "engine": engine(), "model": "calibrated_" + type(base).__name__,
                               "calibration": method, "n_samples": n, "n_pos": n_pos, "n_neg": n_neg}
    try:
        proba_cv = cross_val_predict(calib, X, y, cv=folds, method="predict_proba")[:, 1]
        metrics["pr_auc_cv"] = round(evaluation.pr_auc(y.tolist(), proba_cv.tolist()), 3)
        metrics["calibration_error"] = round(evaluation.calibration_error(y.tolist(), proba_cv.tolist()), 3)
        metrics["ndcg_at_10"] = round(evaluation.ndcg_at_k(y.tolist(), proba_cv.tolist(), 10), 3)
    except Exception as e:
        metrics["pr_auc_cv"] = None
        metrics["eval_note"] = f"cv eval skipped: {e}"
    return calib, metrics


def predict_proba(model, feature_rows: List[Dict[str, Any]]) -> Optional[List[float]]:
    """Calibrated P(success) per row, or None if no usable model."""
    if model is None or not _SK:
        return None
    try:
        X = build_X(feature_rows)
        proba = model.predict_proba(X)
        classes = list(getattr(model, "classes_", [0, 1]))
        idx = classes.index(1) if 1 in classes else len(classes) - 1
        return [float(p[idx]) for p in proba]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 2. Quantile regressors (expected units / contribution margin)
# ---------------------------------------------------------------------------
def train_quantile_regressor(rows: List[Dict[str, Any]], target: str,
                             alpha: float = 0.5) -> Optional[Any]:
    """Median/upper-quantile forecast for a realized target (units_sold/margin)."""
    if not _SK:
        return None
    rows = [r for r in rows if r.get(target) is not None]
    if len(rows) < config.MIN_LABELS_TO_TRAIN:
        return None
    X = build_X(rows)
    y = np.array([_num(r.get(target)) for r in rows])
    if _LGB:
        m = lgb.LGBMRegressor(objective="quantile", alpha=alpha, learning_rate=0.03,
                              num_leaves=63, max_depth=10, min_child_samples=20,
                              subsample=0.8, colsample_bytree=0.8, n_estimators=400, verbosity=-1)
    else:
        m = GradientBoostingRegressor(loss="quantile", alpha=alpha, random_state=42)
    m.fit(X, y)
    return m


def predict_regressor(model, feature_rows: List[Dict[str, Any]]) -> Optional[List[float]]:
    if model is None or not _SK:
        return None
    try:
        return [float(v) for v in model.predict(build_X(feature_rows))]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 3. LambdaMART ranker
# ---------------------------------------------------------------------------
def train_ranker(rows: List[Dict[str, Any]]) -> Optional[Any]:
    """LambdaMART candidate ranker (LightGBM). Returns None without LightGBM —
    the pipeline then ranks by calibrated probability, which is a fine first stage."""
    if not _LGB:
        return None
    rows = [r for r in rows if r.get("label") in (0, 1)]
    if len(rows) < config.MIN_LABELS_TO_TRAIN:
        return None
    X = build_X(rows)
    y = np.array([int(r["label"]) for r in rows])
    ranker = lgb.LGBMRanker(objective="lambdarank", metric="ndcg",
                            learning_rate=0.05, num_leaves=63, max_depth=10,
                            min_child_samples=20, subsample=0.8, colsample_bytree=0.7,
                            n_estimators=400, label_gain=[0, 1], verbosity=-1)
    ranker.fit(X, y, group=[len(rows)])  # single query group (all candidates)
    return ranker


def predict_rank_scores(model, feature_rows: List[Dict[str, Any]]) -> Optional[List[float]]:
    if model is None or not _LGB:
        return None
    try:
        return [float(v) for v in model.predict(build_X(feature_rows))]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# persistence + blending
# ---------------------------------------------------------------------------
def save_model(model, path: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    joblib.dump(model, path)
    return path


def load_model(path: str):
    if not _SK or not path or not os.path.exists(path):
        return None
    try:
        return joblib.load(path)
    except Exception:
        return None


def blended_score(rule_score: float, proba: Optional[float], weight: Optional[float] = None) -> float:
    """Mix transparent rule score (0-100) with calibrated model probability (0-1)."""
    if proba is None:
        return round(float(rule_score), 1)
    w = config.MODEL_BLEND_WEIGHT if weight is None else weight
    return round((1 - w) * float(rule_score) + w * (proba * 100.0), 1)
