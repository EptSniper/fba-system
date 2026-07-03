"""
model.py — OPTIONAL machine-learning layer (scikit-learn).

This is the part that "learns." It is strictly optional:
  * With NO trained model, predict_proba() returns None and the pipeline runs on
    the transparent rule score from scoring.py alone.
  * Once you have labeled enough outcomes (config.MIN_LABELS_TO_TRAIN), train()
    fits a classifier on the features that correlated with your real winners and
    persists it with joblib. From then on, blended_score() mixes the rule score
    with the model's probability.

Honest note: a model only improves when you feed it labeled outcomes. There is no
autonomous magic — more honest labels -> a better model.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import config

# Guard sklearn/joblib imports so the rest of the system loads without them.
try:
    import numpy as np
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    import joblib
    _SKLEARN = True
except Exception:  # pragma: no cover
    _SKLEARN = False

# Feature order is FIXED — train and predict must agree on it.
#
# rule_score was REMOVED (Code Review 2026-07-02, Finding B4): it is the scout's OWN composite
# judgment about this exact candidate, so training a model to predict a human label FROM the
# scout's own score — whose blended output then decides what gets posted — is precisely the
# self-confirmation loop this project's leakage doctrine bans elsewhere (db.py's
# PRE_DECISION_FEATURES allowlist explicitly excludes rule_score/blended_score/verdict for the
# same reason). This is a SEPARATE, legacy feature set from PRE_DECISION_FEATURES (this loop
# predates and isn't yet unified with labels.py's leakage-safe path) — margin_est stays: it's a
# deterministic calculation from pre-decision facts (price/weight/fees), not a judgment call.
FEATURES = ["price", "est_sales", "reviews", "rating", "weight_lb", "offers", "margin_est"]


def features_from(product: Dict[str, Any], rule_score: float,
                  margin: Optional[float]) -> List[float]:
    """Build a fixed-order feature vector, imputing 0.0 for missing values.

    `rule_score` is accepted for call-site backward compatibility but deliberately NOT
    included in the returned vector — see the FEATURES leakage note above."""
    del rule_score  # intentionally unused — kept as a parameter, not as a feature
    return [
        _num(product.get("price")),
        _num(product.get("est_sales")),
        _num(product.get("reviews")),
        _num(product.get("rating")),
        _num(product.get("weight_lb")),
        _num(product.get("offers")),
        _num(margin),
    ]


def _num(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def available() -> bool:
    return _SKLEARN


def load_model(path: Optional[str] = None):
    if not _SKLEARN:
        return None
    path = path or config.MODEL_PATH
    try:
        return joblib.load(path)
    except Exception:
        return None


def predict_proba(features: List[float], model=None,
                  path: Optional[str] = None) -> Optional[float]:
    """
    Probability (0-1) that a product is a 'good' pick.
    Returns None if sklearn is missing or no trained model exists -> caller falls
    back to the rule score.
    """
    if not _SKLEARN:
        return None
    model = model or load_model(path)
    if model is None:
        return None
    try:
        proba = model.predict_proba(np.array([features], dtype=float))[0]
        # class order is model.classes_; find the column for label 1
        classes = list(getattr(model, "classes_", [0, 1]))
        idx = classes.index(1) if 1 in classes else len(classes) - 1
        return float(proba[idx])
    except Exception:
        return None


def train(labeled_rows: List[Dict[str, Any]],
          path: Optional[str] = None) -> Dict[str, Any]:
    """
    Fit a classifier on labeled outcome rows and persist it.

    labeled_rows: dicts with the FEATURES keys plus an int 'label' (1 good / 0 bad).
    Picks GradientBoosting when there's enough data, else LogisticRegression
    (more stable on tiny datasets). Returns a small report dict.
    """
    if not _SKLEARN:
        return {"trained": False, "reason": "scikit-learn/joblib not installed"}

    path = path or config.MODEL_PATH
    rows = [r for r in labeled_rows if r.get("label") in (0, 1)]
    n = len(rows)
    if n < config.MIN_LABELS_TO_TRAIN:
        return {"trained": False, "reason": f"need >= {config.MIN_LABELS_TO_TRAIN} labels, have {n}"}

    labels = [int(r["label"]) for r in rows]
    if len(set(labels)) < 2:
        return {"trained": False, "reason": "need both good (1) and bad (0) labels to learn"}

    X = np.array([[_num(r.get(f)) for f in FEATURES] for r in rows], dtype=float)
    y = np.array(labels, dtype=int)

    # GradientBoosting shines with more data; LogisticRegression is safer when small.
    if n >= 60:
        clf = GradientBoostingClassifier(random_state=42)
        kind = "GradientBoostingClassifier"
    else:
        clf = LogisticRegression(max_iter=1000)
        kind = "LogisticRegression"

    clf.fit(X, y)
    joblib.dump(clf, path)

    train_acc = float(clf.score(X, y))
    return {
        "trained": True,
        "model": kind,
        "n_samples": n,
        "n_good": int(sum(labels)),
        "n_bad": int(n - sum(labels)),
        "train_accuracy": round(train_acc, 3),
        "path": path,
    }


def blended_score(rule_score: float, proba: Optional[float],
                  weight: Optional[float] = None) -> float:
    """
    Combine the transparent rule score (0-100) with the model probability (0-1).
    If no model probability is available, the rule score is returned unchanged.
    """
    if proba is None:
        return round(float(rule_score), 1)
    w = config.MODEL_BLEND_WEIGHT if weight is None else weight
    model_score = proba * 100.0
    return round((1 - w) * float(rule_score) + w * model_score, 1)
