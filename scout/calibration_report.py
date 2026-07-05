"""
calibration_report.py — honest calibration + promotion report (System Blueprint Prompt 3.1).

Writes learning-hub/tracking/calibration-report.md. NEVER silently promotes a model — it states
"NOT enough data to promote" until the threshold in ai-brain.json (learning.minLabeledRows) is
met AND both outcome classes are represented, exactly per the guardrail this prompt spells out.

Scope note: scout_pro/ has its own richer champion/challenger + calibration machinery
(scout_pro/models.py, registry.py, evaluation.py), but that pipeline's own Postgres/SQLite
tables are currently EMPTY — no scout_pro ingest has ever run, so there is nothing there to
calibrate. This report instead exercises the SAME kind of checks (sample size, class balance,
calibration readiness) against the data that IS actually accumulating: scout/'s Supabase +
local-ledger leads via labels.py. Once scout_pro accumulates its own real snapshots/labels, its
own evaluation.py/registry.py are the right tool for that surface — this report does not
duplicate or replace that machinery, it fills the gap while it's unpopulated.
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Any, Dict, List

import labels

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_PATH = os.path.join(HERE, "..", "learning-hub", "tracking", "calibration-report.md")


def calibration_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """A minimal, dependency-light calibration check: split, fit a logistic regression on the
    pre-decision features, and bucket predicted probabilities against actual outcome rate.
    Returns {"available": False, "reason": ...} rather than fabricating a curve from
    insufficient data or a missing dependency."""
    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import train_test_split
        from sklearn.calibration import calibration_curve
    except ImportError:
        return {"available": False, "reason": "scikit-learn not installed"}

    if len(rows) < 10:
        return {"available": False, "reason": f"only {len(rows)} rows — too few for a held-out split"}

    feature_keys = sorted({k for r in rows for k, v in r["features"].items() if isinstance(v, (int, float))})
    if len(feature_keys) < 2:
        return {"available": False, "reason": "fewer than 2 numeric pre-decision features present"}

    X = np.array([[float(r["features"].get(k) or 0.0) for k in feature_keys] for r in rows])
    y = np.array([1 if r["label"] else 0 for r in rows])

    # stratify raises ValueError outright when the minority class has <2 members — a state the
    # upstream refused-gate (n_pos>0 and n_neg>0) legitimately allows. Refuse honestly instead
    # of crashing the report at the first realistic milestone dataset (Review 2026-07-05).
    minority = int(min((y == 1).sum(), (y == 0).sum()))
    if minority < 2:
        return {"available": False,
                "reason": f"minority class has only {minority} row(s) — too few for a stratified split"}

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42, stratify=y
    )
    if len(set(y_train)) < 2 or len(set(y_test)) < 2:
        return {"available": False, "reason": "train/test split left one class empty"}

    clf = LogisticRegression(max_iter=1000).fit(X_train, y_train)
    proba = clf.predict_proba(X_test)[:, 1]
    acc = clf.score(X_test, y_test)
    try:
        frac_pos, mean_pred = calibration_curve(y_test, proba, n_bins=min(5, len(y_test)))
        curve = list(zip([round(float(x), 2) for x in mean_pred], [round(float(x), 2) for x in frac_pos]))
    except Exception:
        curve = None

    return {
        "available": True, "feature_keys": feature_keys,
        "train_n": len(X_train), "test_n": len(X_test),
        "held_out_accuracy": round(float(acc), 3), "calibration_curve": curve,
    }


def generate_report() -> str:
    assembled = labels.assemble_training_rows()
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"## {now} — calibration + promotion check", "",
        f"- Trainable rows (feature snapshot + a label): **{assembled['trainable_count']}**",
        f"- Labeled rows total (incl. local-ledger outcomes with no feature snapshot): {assembled['labeled_count']}",
        f"- Class balance: {assembled['positive']} positive / {assembled['negative']} negative",
        f"- Minimum required (ai-brain.json learning.minLabeledRows): {assembled['min_required']}",
        "",
    ]

    # Per-quality-tier breakdown (DATA_ENGINE_PLAN.md V1) — gold=realized, silver=shadow proxy.
    # Reported separately, NEVER blended, so a silver-heavy metric can't masquerade as validated.
    by_tier = assembled.get("by_tier") or {}
    if by_tier:
        lines.append("- Label quality tiers (trainable):")
        for tier in ("gold", "silver", "bronze", "backtest"):
            t = by_tier.get(tier)
            if t:
                lines.append(f"  - **{tier}**: {t['total']} ({t['positive']} pos / {t['negative']} neg)")
        if assembled.get("silver_count"):
            lines.append(f"- ⚠ {assembled['silver_caveat']}")
        if assembled.get("backtest_available"):
            lines.append(f"- **backtest** (held SEPARATE, not in this diagnostic): "
                         f"{assembled['backtest_available']} hindsight rows — the weakest tier "
                         f"(simulated buy cost, no execution); trained on by the V3 ranker only.")
        lines.append("")

    if assembled["refused"]:
        lines.append(f"**Verdict: NOT enough data to promote.** {assembled['reason']}.")
        lines.append("")
        lines.append("The scout runs on the transparent rule score alone until this changes — "
                     "no model was fit, nothing was promoted.")
    else:
        summary = calibration_summary(assembled["rows"])
        if not summary.get("available"):
            lines.append(f"**Verdict: NOT enough data to promote.** Sample size clears the floor, "
                         f"but calibration itself isn't ready yet: {summary.get('reason')}.")
        else:
            lines.append(f"Held out {summary['test_n']} of {summary['train_n'] + summary['test_n']} "
                         f"rows for testing. Held-out accuracy: **{summary['held_out_accuracy']*100:.0f}%**.")
            if summary.get("calibration_curve"):
                lines.append("")
                lines.append("| predicted P(success) | actual success rate |")
                lines.append("|---|---|")
                for pred, actual in summary["calibration_curve"]:
                    lines.append(f"| {pred} | {actual} |")
            lines.append("")
            lines.append(f"**Verdict: still NOT promoted.** This is a diagnostic fit for visibility, "
                         f"not a promotion decision — scout_pro's champion/challenger gate "
                         f"(PROMOTION_MIN_GAIN) is the actual bar for replacing the rule engine, and "
                         f"that requires far more than the {assembled['trainable_count']} rows "
                         f"available right now. Nothing was auto-applied.")
    lines.append("")
    return "\n".join(lines)


def write_report() -> str:
    block = generate_report()
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    header = ("# Calibration & promotion report (append-only)\n\n"
             "Generated by `scout/calibration_report.py` (System Blueprint Prompt 3.1). Each run "
             "appends a dated block below. Diagnostic only — it never changes ai-brain.json or "
             "promotes a model; it reports whether there's enough real data to even consider it.\n\n")
    if not os.path.exists(REPORT_PATH):
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            f.write(header)
    with open(REPORT_PATH, "a", encoding="utf-8") as f:
        f.write(block + "\n---\n\n")
    return block


if __name__ == "__main__":
    # ASCII-safe stdout: the report block contains U+26A0 once silver labels exist, and a
    # redirected/scheduled stdout on Windows is cp1252 — a raw print would UnicodeEncodeError
    # AFTER the file was already written, making a successful run exit non-zero.
    print(write_report().encode("ascii", "replace").decode())
