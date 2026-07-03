"""
evaluation.py — statistical + business metrics and drift.

The paper specifies: PR-AUC (positives are rare), precision/recall@k and NDCG@k for
the ranking queue, calibration error (we threshold probabilities to alert), and
drift detection (PSI) to trigger retraining. These are used by the champion/
challenger gate and the monitoring job.
"""
from __future__ import annotations

from typing import Dict, List, Sequence

try:
    import numpy as np
    from sklearn.metrics import average_precision_score, ndcg_score
    _SK = True
except Exception:  # pragma: no cover
    _SK = False


def pr_auc(y_true: Sequence[int], y_score: Sequence[float]) -> float:
    """Area under the precision-recall curve (a.k.a. average precision)."""
    if not _SK or len(set(y_true)) < 2:
        return float("nan")
    return float(average_precision_score(list(y_true), list(y_score)))


def precision_recall_at_k(y_true: Sequence[int], y_score: Sequence[float], k: int) -> Dict[str, float]:
    order = sorted(range(len(y_score)), key=lambda i: y_score[i], reverse=True)[:k]
    topk = [y_true[i] for i in order]
    tp = sum(topk)
    total_pos = sum(y_true) or 1
    return {"precision_at_k": tp / max(len(topk), 1), "recall_at_k": tp / total_pos}


def ndcg_at_k(y_true: Sequence[int], y_score: Sequence[float], k: int) -> float:
    if not _SK or len(y_true) < 2:
        return float("nan")
    try:
        return float(ndcg_score([list(y_true)], [list(y_score)], k=k))
    except Exception:
        return float("nan")


def calibration_error(y_true: Sequence[int], y_prob: Sequence[float], bins: int = 10) -> float:
    """Expected Calibration Error: weighted gap between confidence and accuracy."""
    if not _SK or not len(y_true):
        return float("nan")
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.asarray(y_prob, dtype=float)
    edges = np.linspace(0, 1, bins + 1)
    ece = 0.0
    n = len(y_true)
    for i in range(bins):
        m = (y_prob >= edges[i]) & (y_prob < edges[i + 1] if i < bins - 1 else y_prob <= edges[i + 1])
        if m.sum() == 0:
            continue
        conf = y_prob[m].mean()
        acc = y_true[m].mean()
        ece += (m.sum() / n) * abs(conf - acc)
    return float(ece)


def psi(expected: Sequence[float], actual: Sequence[float], bins: int = 10) -> float:
    """
    Population Stability Index between a baseline (expected) and current (actual)
    distribution of a feature. >0.2 typically signals material drift.
    """
    if not _SK or len(expected) == 0 or len(actual) == 0:
        return float("nan")
    expected = np.asarray(expected, dtype=float)
    actual = np.asarray(actual, dtype=float)
    quantiles = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1)))
    if len(quantiles) < 2:
        return 0.0
    e_perc, _ = np.histogram(expected, bins=quantiles)
    a_perc, _ = np.histogram(actual, bins=quantiles)
    e_perc = np.clip(e_perc / max(e_perc.sum(), 1), 1e-6, None)
    a_perc = np.clip(a_perc / max(a_perc.sum(), 1), 1e-6, None)
    return float(np.sum((a_perc - e_perc) * np.log(a_perc / e_perc)))


def population_drift(baseline_rows: List[Dict], current_rows: List[Dict],
                    columns: List[str], threshold: float) -> Dict[str, float]:
    """Per-feature PSI; returns {feature: psi} for any feature above threshold."""
    drifted = {}
    for c in columns:
        e = [r.get(c) for r in baseline_rows if r.get(c) is not None]
        a = [r.get(c) for r in current_rows if r.get(c) is not None]
        if len(e) >= 10 and len(a) >= 10:
            val = psi(e, a)
            if val == val and val >= threshold:  # not NaN and above threshold
                drifted[c] = round(val, 4)
    return drifted
