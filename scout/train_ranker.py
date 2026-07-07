"""
scout/train_ranker.py — hourly training + champion/challenger evaluation (cloud or local).

Runs in GitHub Actions (.github/workflows/train-ranker.yml, hourly at :41 — tightened from every
6h on 2026-07-07 to match keepa-collect.yml's own hourly cadence, so a fresh backtest row never
waits more than ~1h before the next skip-if-unchanged check considers it) and locally. One cycle:
pull training rows from Supabase (all tiers, labels.py) -> train the CHALLENGER (LightGBM,
class-balanced, small-data-adaptive hyperparameters, NaN-native missing-value handling — Session
55 review fix; was scikit-learn LogisticRegression before that) -> compare it against the
CHAMPION (the deterministic triage formula, scoring.triage_score) on a held-out BY-ASIN split ->
append learning-hub/tracking/ranker-report.md -> upload the model artifact + report to the
Supabase storage bucket `models/` (ranker/<date>/ + a stable ranker/current/) -> post a summary
to the brain-proposals Discord stream.

NON-NEGOTIABLES (test-enforced by tests/test_train_ranker.py):
  * NO AUTOMATIC PROMOTION, regardless of where training ran: this script NEVER writes
    ai-brain.json. Promotion happens only when Mehmet flips the brain key
    scoring.rankingChampion via fba-brain-updater; until then the trained model is shadow-only.
  * Refuses honestly below the data floor (brain learning.minLabeledRows, both classes present)
    — a refusal exits 0 with a "not enough data" report, never a fabricated metric.
  * Tier honesty: metrics are reported per label_quality tier; backtest rows are the weakest
    tier and the report says so every time.

Live consumer (Session 55 review fix): once promoted, scout/pipeline.py's _evaluate()/
_rank_winners() actually score and order candidates with this model — see load_challenger()/
challenger_score() below. Before this fix nothing in the codebase ever read the trained
artifact; the champion/challenger comparison had no way to affect anything even when promoted.

Local side: run_daily calls fetch_current_model() at cycle start (best-effort) so the local
pipeline always has the latest cloud-trained champion candidate on disk for shadow use.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

REPORT_PATH = os.path.join(HERE, "..", "learning-hub", "tracking", "ranker-report.md")
MODELS_DIR = os.path.join(HERE, "..", "learning-hub", "models", "ranker")
BRAIN_PATH = os.path.join(HERE, "..", "learning-hub", "data", "ai-brain.json")
BUCKET = "models"
FINGERPRINT_NAME = "fingerprint.json"

# Numeric subset of db.PRE_DECISION_FEATURES — the ONLY model inputs (leakage contract).
ORIGINAL_NUMERIC_FEATURES = ("price", "weight_lb", "sales_rank", "est_sales", "offers",
                             "avg_price_90", "avg_offers_90", "avg_sales_rank_90", "oos_90",
                             "amazon_bb_share")

# Session 55's free signal-type features (scout/signals/) — kept as a SEPARATE tuple (rather
# than folded silently into ORIGINAL_NUMERIC_FEATURES) so render_report()'s "new signals"
# section can report exactly this set's fitted importance: each earns its seat via evidence
# after the first retrain, or gets flagged for removal — the same kill-rule as everything else
# in this project, never assumed useful just because it was added. Boolean fields (is_bts_window,
# *_trend_spike, *_stale) convert via vectorize_one()'s float(True)=1.0/float(False)=0.0, no
# special handling needed.
#
# Review fix (2026-07-06): the three *_stale flags (brand_trend_stale, category_trend_stale,
# ebay_stale) are now REAL model inputs, not excluded metadata — a stale last-known Trends value
# (the source went dark for weeks) should read differently to the model than a fresh one, and
# excluding the flag entirely made that impossible to learn. nearest_major_holiday_name/upc stay
# excluded (strings, not usable by a numeric feature vector).
NEW_SIGNAL_FEATURES = (
    "days_to_prime_day", "weeks_to_q4_arrival_deadline", "days_to_nearest_major_holiday",
    "is_bts_window", "day_of_week",
    "brand_trend_ratio", "brand_trend_slope", "brand_trend_seasonal_z", "brand_trend_spike",
    "brand_trend_stale",
    "category_trend_ratio", "category_trend_slope", "category_trend_seasonal_z", "category_trend_spike",
    "category_trend_stale",
    "ebay_active_listing_count", "median_active_price_vs_amazon_ratio", "ebay_stale",
)
NUMERIC_FEATURES = ORIGINAL_NUMERIC_FEATURES + NEW_SIGNAL_FEATURES


# --- dataset -----------------------------------------------------------------
def build_dataset() -> Dict[str, Any]:
    """Training rows from Supabase via labels.py (gold + silver + backtest — the ranker is the
    one consumer that opts backtest in, per DATA_ENGINE_PLAN.md V2/V3)."""
    import labels
    assembled = labels.assemble_training_rows(include_silver=True, include_backtest=True)
    return assembled


FINGERPRINT_SAMPLE_SIZE = 500  # bounded row-content sample — see training_set_fingerprint()


def _fingerprint_row_identity(r: Dict[str, Any]) -> str:
    return "|".join(str(x) for x in (
        r.get("asin"), r.get("source"), r.get("label"), r.get("label_quality"),
        r.get("simulation_date") or r.get("checkpoint_day") or "",
    ))


def _fingerprint_row_content(r: Dict[str, Any]) -> str:
    feats = r.get("features") or {}
    feat_str = "|".join(f"{k}={feats.get(k)}" for k in sorted(feats.keys()))
    return _fingerprint_row_identity(r) + "::" + feat_str


def training_set_fingerprint(assembled: Dict[str, Any]) -> Dict[str, Any]:
    """A signature of the CURRENT training set — row identity + row CONTENT + the model's own
    input schema, so the every-6h skip-if-unchanged guard can't stay blind to a change that
    doesn't touch row identity.

    Found on review (2026-07-06): the original version hashed ONLY each row's identifying tuple
    (asin/source/label/label_quality/date) — never the feature VALUES. scout/signals/
    trends_backfill.py patches features_snapshot IN PLACE on those exact same natural keys (same
    asin/simulation_date/label, different feature content), and this session also expanded
    NUMERIC_FEATURES from 10 to 25 fields — neither would have changed the old fingerprint at
    all, so the skip guard would have suppressed every retrain after either change indefinitely.

    Now: `schema_version` hashes NUMERIC_FEATURES itself, so ANY code change to what the model
    trains on (an addition, removal, or reorder) busts the fingerprint even if the underlying
    rows are byte-identical. `content_hash` still hashes every row's identity (cheap, and alone
    already detects additions/removals) PLUS a bounded, deterministic SAMPLE of up to
    FINGERPRINT_SAMPLE_SIZE rows' actual feature values (evenly spaced across the identity-sorted
    order, so the sample is stable regardless of Supabase's own return order) — cheap even at
    the ~50k-row corpus target, and now sensitive to a backfill rewriting content in place."""
    rows = assembled.get("rows") or []
    schema_version = hashlib.sha256("|".join(NUMERIC_FEATURES).encode("utf-8")).hexdigest()[:16]

    identity_keys = sorted(_fingerprint_row_identity(r) for r in rows)

    sorted_rows = sorted(rows, key=lambda r: _fingerprint_row_identity(r))
    n = len(sorted_rows)
    if n <= FINGERPRINT_SAMPLE_SIZE:
        sample_rows = sorted_rows
    else:
        step = n / FINGERPRINT_SAMPLE_SIZE
        sample_rows = [sorted_rows[int(i * step)] for i in range(FINGERPRINT_SAMPLE_SIZE)]
    content_sample = sorted(_fingerprint_row_content(r) for r in sample_rows)

    digest = hashlib.sha256(
        ("\n".join(identity_keys) + "\n---\n" + "\n".join(content_sample)).encode("utf-8")
    ).hexdigest()
    return {
        "row_count": len(rows),
        "bronze_count": len(assembled.get("bronze_rows") or []),
        "schema_version": schema_version,
        "content_hash": digest,
    }


def fetch_last_fingerprint() -> Optional[Dict[str, Any]]:
    """The previous run's training_set_fingerprint(), stored next to the model artifacts in
    Supabase storage (ranker/current/fingerprint.json). None on a first-ever run, missing env, or
    any failure — never raises; a missing fingerprint just means "don't skip, nothing to compare"."""
    try:
        import requests
        supa = os.getenv("SUPABASE_URL", "").rstrip("/")
        if not supa or not os.getenv("SUPABASE_SERVICE_KEY"):
            return None
        r = requests.get(f"{supa}/storage/v1/object/{BUCKET}/ranker/current/{FINGERPRINT_NAME}",
                         headers=_storage_headers(), timeout=15)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception as e:
        print(f"[train_ranker] fetch_last_fingerprint failed (non-fatal): {type(e).__name__}")
        return None


def upload_fingerprint(fp: Dict[str, Any]) -> bool:
    """Store this run's fingerprint next to the model, for the NEXT run's skip-check. Best-effort
    — never raises. Runs regardless of refused/trained outcome so a repeated refusal with no new
    data also correctly skips next time instead of re-posting the same refusal every cadence."""
    try:
        import requests
        supa = os.getenv("SUPABASE_URL", "").rstrip("/")
        if not supa or not os.getenv("SUPABASE_SERVICE_KEY"):
            return False
        try:
            r = requests.post(f"{supa}/storage/v1/bucket", headers=_storage_headers(),
                              json={"id": BUCKET, "name": BUCKET, "public": False}, timeout=15)
            if r.status_code not in (200, 201) and "already exists" not in r.text.lower():
                print(f"[train_ranker] bucket create: HTTP {r.status_code} (continuing)")
        except Exception as e:
            print(f"[train_ranker] bucket create failed (continuing): {type(e).__name__}")
        r = requests.post(
            f"{supa}/storage/v1/object/{BUCKET}/ranker/current/{FINGERPRINT_NAME}",
            headers={**_storage_headers(), "x-upsert": "true", "Content-Type": "application/json"},
            data=json.dumps(fp).encode("utf-8"), timeout=30,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"[train_ranker] upload_fingerprint failed (non-fatal): {type(e).__name__}")
        return False


def vectorize_one(features: Optional[Dict[str, Any]]):
    """The SAME per-row feature-vector construction build_matrix() uses, for a SINGLE row.
    Shared by both training-time (build_matrix) and live-scoring-time (challenger_score)
    vectorization so the two paths can never silently drift apart.

    Review fix (2026-07-06): a genuinely missing value is now NaN, not 0.0. The old
    `float(v or 0.0)` collided a real "we don't know" with a real, meaningful zero —
    days_to_prime_day=0 means "the window opens today"; day_of_week=0 means Monday;
    ebay_active_listing_count=0 means "confirmed zero active listings", not "no data". LightGBM (the current
    challenger classifier, train_and_evaluate) handles NaN NATIVELY — it learns which split
    direction missing values should default to from the data itself, rather than the model
    being handed a fabricated number it can't tell apart from a real one. Booleans
    (is_bts_window, *_trend_spike, *_stale) still convert cleanly via float(True)=1.0/
    float(False)=0.0 — only an ACTUAL None becomes NaN."""
    import numpy as np
    out = []
    for k in NUMERIC_FEATURES:
        v = (features or {}).get(k)
        out.append(float(v) if v is not None else float("nan"))
    return np.array(out)


def build_matrix(rows: List[Dict[str, Any]]) -> Tuple[Any, Any]:
    """Rows -> (X, y) over NUMERIC_FEATURES only, via vectorize_one (None -> NaN, not 0.0)."""
    import numpy as np
    X = np.array([vectorize_one(r.get("features")) for r in rows])
    y = np.array([1 if r["label"] else 0 for r in rows])
    return X, y


def champion_scores(rows: List[Dict[str, Any]]) -> List[Optional[float]]:
    """The CHAMPION: the deterministic triage formula, computed from the same pre-decision
    features. None (can't rank) sorts to the bottom, matching pipeline behavior."""
    import scoring
    out = []
    for r in rows:
        f = r.get("features") or {}
        out.append(scoring.triage_score(
            {"price": f.get("price"), "est_sales": f.get("est_sales"),
             "weight_lb": f.get("weight_lb")}, category=f.get("category")))
    return out


# --- evaluation ---------------------------------------------------------------
def rank_metrics(scores: List[Optional[float]], y: List[int], top_n: int = 10) -> Dict[str, Any]:
    """AUC + winners-in-top-N for one scorer. None scores rank last. AUC is None when only one
    class is present (never fabricated)."""
    import numpy as np
    from sklearn.metrics import roc_auc_score
    s = np.array([(-1e18 if v is None else float(v)) for v in scores])
    y = np.array(y)
    auc = float(roc_auc_score(y, s)) if len(set(y.tolist())) > 1 else None
    order = np.argsort(-s)
    top = order[:top_n]
    return {"auc": auc, "winners_in_top": int(y[top].sum()), "top_n": min(top_n, len(y))}


def verdict_line(champ: Dict[str, Any], chall: Dict[str, Any], margin: float = 0.02) -> str:
    """The explicit champion/challenger verdict (V3 spec wording). The challenger must BEAT the
    champion's AUC by `margin` to even claim a win — and a win still only REQUESTS promotion."""
    ca, xa = champ.get("auc"), chall.get("auc")
    if ca is None or xa is None:
        return "VERDICT: INCONCLUSIVE (single-class validation slice) — challenger stays shadow."
    if xa > ca + margin:
        return ("VERDICT: CHALLENGER WINS on held-out AUC — promotion requires human approval "
                "(flip scoring.rankingChampion via fba-brain-updater; nothing was auto-applied).")
    return "VERDICT: CHALLENGER LOSES — stays shadow."


def bronze_agreement(clf, scaler, bronze_rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """AUXILIARY metric only (Mehmet's directive, Session 55): how often the trained model's
    verdict matches the human's OWN buy/pass decision on bronze (decision-only, no realized
    outcome yet) rows. This is NOT a training signal and never influences the relevance target —
    bronze rows never entered Xtr/ytr/Xva/yva. A HIGH agreement rate could just mean the model
    learned the operator's own bias, not the market, so it is reported with that caveat every
    time, never treated as validation. None when there are no bronze rows to score.

    scaler is optional (None for the current LightGBM challenger, which needs no scaling —
    kept as a parameter for a linear model's StandardScaler, tree-based or otherwise)."""
    if not bronze_rows:
        return None
    Xb, yb = build_matrix(bronze_rows)
    if len(Xb) == 0:
        return None
    Xb_input = scaler.transform(Xb) if scaler is not None else Xb
    preds = clf.predict(Xb_input)
    agree = float((preds == yb).mean())
    return {"n": len(bronze_rows), "agreement_rate": round(agree, 3)}


def source_breakdown(val_rows: List[Dict[str, Any]], proba: List[float]) -> Dict[str, Any]:
    """Per sample_source rank_metrics on the SAME held-out slice/predictions (Session 55,
    learning.sampling): lets the report compare onpolicy vs explore vs dealfeed performance
    separately, never blended. Rows without a sample_source (gold/silver rows, which predate this
    tagging) are grouped under 'n/a'. A group with only one class present is reported as a count
    only — AUC stays None rather than fabricated."""
    by_source: Dict[str, List[int]] = {}
    for i, r in enumerate(val_rows):
        src = r.get("sample_source") or "n/a"
        by_source.setdefault(src, []).append(i)
    out: Dict[str, Any] = {}
    for src, idxs in by_source.items():
        y_sub = [1 if val_rows[i]["label"] else 0 for i in idxs]
        p_sub = [float(proba[i]) for i in idxs]
        if len(set(y_sub)) < 2:
            out[src] = {"n": len(idxs), "auc": None}
        else:
            out[src] = {"n": len(idxs), **rank_metrics(p_sub, y_sub, top_n=min(10, len(idxs)))}
    return out


def new_signal_importance(clf) -> Dict[str, float]:
    """Each Session 55 signal feature's fitted importance — the evidence render_report()'s 'new
    signals' section shows so a human can decide keep-or-cut.

    Prefers LightGBM's feature_importances_ (split-count/gain based, normalized to a 0-1 share
    of the model's total — a rough parity with 25 features means "average" is ~0.04, so the
    existing 0.05 near-zero threshold still reads as "below average use"). Falls back to a
    linear model's signed .coef_ for backward compatibility with any OLDER saved artifact still
    on disk. {} when the model exposes neither."""
    importances = getattr(clf, "feature_importances_", None)
    if importances is not None and len(importances):
        total = float(sum(importances)) or 1.0
        return {name: round(float(importances[i]) / total, 4)
               for i, name in enumerate(NUMERIC_FEATURES) if name in NEW_SIGNAL_FEATURES}
    coefs = getattr(clf, "coef_", None)
    if coefs is None:
        return {}
    row = coefs[0] if hasattr(coefs, "__len__") and len(coefs) else coefs
    return {name: round(float(row[i]), 4) for i, name in enumerate(NUMERIC_FEATURES)
           if name in NEW_SIGNAL_FEATURES}


def _lightgbm_params(n_train: int) -> Dict[str, int]:
    """Small-data-aware LightGBM hyperparameters. The actual training corpus today is a few
    hundred rows (not yet the ~50k target), and LightGBM's stock defaults (min_child_samples=20,
    num_leaves=31) badly underfit anything under a few hundred rows — LIVE-VERIFIED: a cleanly
    separable 42-row synthetic fixture scores AUC=0.5 (learns nothing at all) with stock
    defaults, AUC=1.0 with these scaled-down values. Scales back up toward LightGBM's own
    defaults as the corpus grows toward the target, so nothing needs to change by hand later."""
    return {
        "min_child_samples": max(1, min(20, n_train // 10)),
        "num_leaves": max(3, min(31, n_train // 3)),
    }


def train_and_evaluate(assembled: Dict[str, Any]) -> Dict[str, Any]:
    """The full training cycle on already-pulled rows. Pure of I/O to Supabase/Discord — callable
    from tests with synthetic rows.

    Challenger model (review fix, 2026-07-06): LightGBM, not scikit-learn's LogisticRegression —
    the project's own long-planned "V3 LightGBM later" step, brought forward because it's what
    makes vectorize_one's NaN-for-missing fix actually usable: LightGBM handles NaN NATIVELY
    (learns the best split direction for missing values from the data itself); scikit-learn's
    StandardScaler/LogisticRegression reject NaN outright. Tree-based models are scale-
    invariant, so there's no scaler at all now ("scaler": None in the returned dict — every
    consumer of this dict already treats a None scaler as "skip the transform step")."""
    import backtest  # split_by_asin — the same leakage-safe splitter V2 tests enforce
    import lightgbm as lgb

    rows = assembled["rows"]
    if assembled.get("refused"):
        return {"refused": True, "reason": assembled["reason"], "by_tier": assembled.get("by_tier", {})}

    train, val = backtest.split_by_asin(rows, val_fraction=0.3)
    if not train or not val:
        return {"refused": True, "reason": "by-ASIN split left an empty side", "by_tier": assembled.get("by_tier", {})}
    Xtr, ytr = build_matrix(train)
    Xva, yva = build_matrix(val)
    if len(set(ytr.tolist())) < 2:
        return {"refused": True, "reason": "training side has one class after the by-ASIN split",
                "by_tier": assembled.get("by_tier", {})}

    clf = lgb.LGBMClassifier(class_weight="balanced", random_state=42, verbosity=-1,
                             **_lightgbm_params(len(Xtr))).fit(Xtr, ytr)
    proba = clf.predict_proba(Xva)[:, 1]

    chall = rank_metrics([float(p) for p in proba], yva.tolist())
    champ = rank_metrics(champion_scores(val), yva.tolist())
    return {
        "refused": False,
        "model": clf, "scaler": None, "features": list(NUMERIC_FEATURES),
        "train_rows": len(train), "val_rows": len(val),
        "train_asins": len({r["asin"] for r in train if r.get("asin")}),
        "val_asins": len({r["asin"] for r in val if r.get("asin")}),
        "by_tier": assembled.get("by_tier", {}),
        "champion": champ, "challenger": chall,
        "verdict": verdict_line(champ, chall),
        "silver_caveat": assembled.get("silver_caveat", ""),
        "bronze_agreement": bronze_agreement(clf, None, assembled.get("bronze_rows") or []),
        "bronze_caveat": assembled.get("bronze_caveat", ""),
        "by_source": source_breakdown(val, [float(p) for p in proba]),
        "new_signal_importance": new_signal_importance(clf),
    }


# --- report -------------------------------------------------------------------
def render_report(result: Dict[str, Any]) -> str:
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"## {now} — ranker training + champion/challenger", ""]
    tiers = result.get("by_tier") or {}
    if tiers:
        tier_bits = [f"{t}: {c['total']} ({c['positive']} pos/{c['negative']} neg)"
                     for t, c in sorted(tiers.items())]
        lines.append("- Label tiers: " + "; ".join(tier_bits))
    if result.get("refused"):
        lines += ["", f"**REFUSED to train:** {result['reason']}.",
                  "No model was fit; nothing was uploaded or promoted.", ""]
        return "\n".join(lines)
    ch, xl = result["champion"], result["challenger"]
    lines += [
        f"- Split BY ASIN: train {result['train_rows']} rows / {result['train_asins']} asins; "
        f"val {result['val_rows']} rows / {result['val_asins']} asins",
        f"- CHAMPION (deterministic triage): AUC {ch['auc'] if ch['auc'] is not None else 'n/a'}"
        f" · winners in top {ch['top_n']}: {ch['winners_in_top']}",
        f"- CHALLENGER (classical model, shadow): AUC {xl['auc'] if xl['auc'] is not None else 'n/a'}"
        f" · winners in top {xl['top_n']}: {xl['winners_in_top']}",
        "",
        f"**{result['verdict']}**",
        "",
        "Caveats: backtest rows are the weakest tier (simulated buy cost, no execution/"
        "sell-through); " + (result.get("silver_caveat") or ""),
        "Promotion is HUMAN-ONLY via the brain key scoring.rankingChampion — this job never "
        "touches ai-brain.json.", "",
    ]
    by_source = result.get("by_source") or {}
    if len(by_source) > 1 or (by_source and "n/a" not in by_source):
        lines.append("- Sampling-source breakdown (held-out slice, same model — never blended):")
        for src, m in sorted(by_source.items()):
            auc_str = m["auc"] if m.get("auc") is not None else "n/a (single class in slice)"
            lines.append(f"  - **{src}**: n={m['n']}, AUC {auc_str}")
        lines.append("")
    bronze = result.get("bronze_agreement")
    if bronze:
        lines.append(
            f"- Bronze agreement (auxiliary, NOT a training signal): the model agrees with the "
            f"operator's own buy/pass decision on {bronze['agreement_rate']*100:.0f}% of "
            f"{bronze['n']} decision-only row(s). {result.get('bronze_caveat') or ''}")
        lines.append("")
    importance = result.get("new_signal_importance") or {}
    if importance:
        lines.append("- New signals (Trends/calendar/eBay, Session 55) — normalized feature "
                     "importance (LightGBM feature_importances_, share of total splits; "
                     "< 0.05 flagged as a removal candidate, human decides — same kill-rule as "
                     "everything else):")
        for name, coef in sorted(importance.items(), key=lambda kv: -abs(kv[1])):
            flag = "" if abs(coef) >= 0.05 else " ⚠ near-zero"
            lines.append(f"  - {name}: {coef}{flag}")
        lines.append("")
    return "\n".join(lines)


def append_report(block: str) -> None:
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    if not os.path.exists(REPORT_PATH):
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            f.write("# Ranker report (append-only)\n\nGenerated by scout/train_ranker.py "
                    "(cloud: .github/workflows/train-ranker.yml). Diagnostic + shadow only — "
                    "promotion requires a human brain edit.\n\n")
    with open(REPORT_PATH, "a", encoding="utf-8") as f:
        f.write(block + "\n---\n\n")


# --- artifacts + Supabase storage ----------------------------------------------
def save_artifacts(result: Dict[str, Any], out_dir: str) -> List[str]:
    """Persist model.joblib + metrics.json into out_dir. Returns the file paths."""
    import joblib
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    meta = {k: result[k] for k in ("train_rows", "val_rows", "train_asins", "val_asins",
                                   "by_tier", "champion", "challenger", "verdict", "features",
                                   "by_source", "bronze_agreement", "new_signal_importance")}
    meta["trained_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    meta["model_kind"] = "LightGBM (class-balanced, small-data-adaptive hyperparameters; NaN-native missing-value handling — Session 55 review fix)"
    mpath = os.path.join(out_dir, "model.joblib")
    joblib.dump({"model": result["model"], "scaler": result["scaler"],
                 "features": result["features"], "meta": meta}, mpath)
    paths.append(mpath)
    jpath = os.path.join(out_dir, "metrics.json")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, default=str)
    paths.append(jpath)
    return paths


def _storage_headers() -> Dict[str, str]:
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def upload_to_storage(paths: List[str], date_prefix: str) -> int:
    """Upload artifacts to the private `models` bucket, twice each: versioned
    ranker/<date>/... AND the stable ranker/current/... the local fetch reads. Creates the
    bucket if missing. Returns files uploaded (0 on any hard failure — never raises)."""
    import requests
    supa = os.getenv("SUPABASE_URL", "").rstrip("/")
    if not supa or not os.getenv("SUPABASE_SERVICE_KEY"):
        print("[train_ranker] no Supabase env — skipping storage upload")
        return 0
    try:
        r = requests.post(f"{supa}/storage/v1/bucket", headers=_storage_headers(),
                          json={"id": BUCKET, "name": BUCKET, "public": False}, timeout=15)
        if r.status_code not in (200, 201) and "already exists" not in r.text.lower():
            print(f"[train_ranker] bucket create: HTTP {r.status_code} (continuing)")
    except Exception as e:
        print(f"[train_ranker] bucket create failed (continuing): {type(e).__name__}")
    n = 0
    import mimetypes
    for path in paths:
        name = os.path.basename(path)
        for prefix in (f"ranker/{date_prefix}", "ranker/current"):
            try:
                with open(path, "rb") as f:
                    r = requests.post(
                        f"{supa}/storage/v1/object/{BUCKET}/{prefix}/{name}",
                        headers={**_storage_headers(), "x-upsert": "true",
                                 "Content-Type": mimetypes.guess_type(name)[0] or "application/octet-stream"},
                        data=f.read(), timeout=60)
                r.raise_for_status()
                n += 1
            except Exception as e:
                print(f"[train_ranker] upload failed ({prefix}/{name}): {type(e).__name__}")
    return n


def fetch_current_model(dest_dir: Optional[str] = None) -> Optional[str]:
    """Download the current champion-candidate (ranker/current/model.joblib) from Supabase
    storage to learning-hub/models/ranker/current/ so the local pipeline has the latest
    cloud-trained model at run start. Best-effort: returns the local path or None; NEVER raises
    (called from run_daily — a storage hiccup must not touch the cycle)."""
    try:
        import requests
        supa = os.getenv("SUPABASE_URL", "").rstrip("/")
        if not supa or not os.getenv("SUPABASE_SERVICE_KEY"):
            return None
        dest_dir = dest_dir or os.path.join(MODELS_DIR, "current")
        os.makedirs(dest_dir, exist_ok=True)
        got = None
        for name in ("model.joblib", "metrics.json"):
            r = requests.get(f"{supa}/storage/v1/object/{BUCKET}/ranker/current/{name}",
                             headers=_storage_headers(), timeout=30)
            if r.status_code != 200:
                continue
            p = os.path.join(dest_dir, name)
            with open(p, "wb") as f:
                f.write(r.content)
            if name == "model.joblib":
                got = p
        return got
    except Exception as e:
        print(f"[train_ranker] fetch_current_model failed (non-fatal): {type(e).__name__}")
        return None


# --- LIVE CONSUMER (review fix, 2026-07-06) -------------------------------------
# Until this fix, nothing in the codebase ever read the cloud-trained ranker artifact this whole
# module exists to produce: training ran, evaluated, and uploaded a champion/challenger
# comparison every cadence, but no live scoring path could ever act on it. This section is that
# reader — gated entirely on the human-only brain key scoring.rankingChampion, so shadow mode
# (the "rule" default) stays byte-identical to today's behavior; the challenger only touches
# anything once a human has explicitly promoted it via fba-brain-updater.
_challenger_cache: Dict[str, Any] = {"loaded": False, "model": None}


def reset_challenger_cache() -> None:
    """Test/process hygiene — the cache is per-process and loaded at most once per run
    otherwise, so a burst scoring many candidates doesn't re-read the artifact per candidate."""
    _challenger_cache["loaded"] = False
    _challenger_cache["model"] = None


def ranking_champion() -> str:
    """ai-brain.json scoring.rankingChampion — 'rule' (default, shadow-only) or 'challenger'
    (a human has explicitly promoted the trained ranker). ANY missing/unrecognized value
    defaults to 'rule' — shadow mode is always the safe fallback, never an accidental promotion
    from an absent key or a brain typo."""
    try:
        with open(BRAIN_PATH, encoding="utf-8") as f:
            value = ((json.load(f) or {}).get("scoring") or {}).get("rankingChampion")
        if value in ("rule", "challenger"):
            return value
    except Exception:
        pass
    return "rule"


def load_challenger(force: bool = False) -> Optional[Dict[str, Any]]:
    """The cloud-trained ranker artifact (model.joblib: {model, scaler, features, meta}), for
    LIVE scoring — NOT the training/evaluation path above. Returns None (never raises) whenever
    rankingChampion isn't 'challenger', or the artifact can't be found/loaded/doesn't have the
    expected shape — every failure mode degrades to "score with the rule/triage formula exactly
    as if nothing were ever promoted," never a crash and never a silent wrong-shaped prediction.
    Cached per-process (see reset_challenger_cache) so repeated calls within one run/burst don't
    re-read the artifact per candidate."""
    if _challenger_cache["loaded"] and not force:
        return _challenger_cache["model"]
    _challenger_cache["loaded"] = True
    _challenger_cache["model"] = None
    if ranking_champion() != "challenger":
        return None
    try:
        import joblib
    except Exception:
        print("[train_ranker] joblib unavailable — can't load the promoted challenger, "
             "falling back to the rule score")
        return None
    local_path = os.path.join(MODELS_DIR, "current", "model.joblib")
    if not os.path.exists(local_path):
        # Not present locally (a fresh cloud runner, or run_daily hasn't fetched this cycle yet)
        # — best-effort live download, the SAME mechanism run_daily.py already uses at cycle
        # start, so this is a fallback rather than the common path.
        fetched = fetch_current_model()
        if fetched:
            local_path = fetched
    if not os.path.exists(local_path):
        print("[train_ranker] scoring.rankingChampion=challenger but no model artifact is "
             "available locally or in storage — falling back to the rule score")
        return None
    try:
        loaded = joblib.load(local_path)
        if not isinstance(loaded, dict) or "model" not in loaded or "scaler" not in loaded:
            print(f"[train_ranker] challenger artifact at {local_path} has an unexpected shape "
                 "— falling back to the rule score")
            return None
        _challenger_cache["model"] = loaded
        return loaded
    except Exception as e:
        print(f"[train_ranker] load_challenger failed (non-fatal, falls back to the rule "
             f"score): {type(e).__name__}")
        return None


def challenger_score(champion: Optional[Dict[str, Any]],
                     features: Optional[Dict[str, Any]]) -> Optional[float]:
    """The promoted challenger's probability for one candidate's pre-decision features. None
    (never raises) when no champion is loaded or scoring fails for any reason — callers fall
    back to the rule/triage score exactly as if nothing were promoted. NEVER affects any hard
    gate (score>=threshold, compliance/safety checks) — those stay rule-based always; this only
    ever feeds an ORDERING decision, and only when explicitly promoted.

    champion["scaler"] is optional (None for the current LightGBM challenger, which needs no
    scaling — tree-based models are scale-invariant; kept for a future/older linear model)."""
    if not champion:
        return None
    try:
        X = vectorize_one(features).reshape(1, -1)
        scaler = champion.get("scaler")
        Xs = scaler.transform(X) if scaler is not None else X
        proba = champion["model"].predict_proba(Xs)[:, 1]
        return float(proba[0])
    except Exception as e:
        print(f"[train_ranker] challenger_score failed (non-fatal): {type(e).__name__}")
        return None


# --- Discord -------------------------------------------------------------------
def post_summary(result: Dict[str, Any]) -> bool:
    """One embed to the brain-proposals stream (it's a PROPOSAL surface: the verdict may suggest
    promotion, a human decides). Honest no-op when the webhook isn't configured."""
    import discord_router
    if result.get("refused"):
        embed = {"title": "🤖 Ranker training: refused (not enough data)",
                 "description": result["reason"], "color": 0x8B9BB0}
    else:
        ch, xl = result["champion"], result["challenger"]
        tiers = "; ".join(f"{t}: {c['total']}" for t, c in sorted((result.get("by_tier") or {}).items()))
        embed = {
            "title": "🤖 Ranker trained (shadow) — champion vs challenger",
            "color": 0x3987E5,
            "description": (
                f"Rows: {result['train_rows']}+{result['val_rows']} (by-ASIN split) · tiers: {tiers}\n"
                f"**Champion (triage formula):** AUC {ch['auc'] if ch['auc'] is not None else 'n/a'}, "
                f"{ch['winners_in_top']}/{ch['top_n']} winners in top\n"
                f"**Challenger (model):** AUC {xl['auc'] if xl['auc'] is not None else 'n/a'}, "
                f"{xl['winners_in_top']}/{xl['top_n']} winners in top\n\n{result['verdict']}\n\n"
                "Promotion is human-only: brain key `scoring.rankingChampion` (fba-brain-updater)."),
        }
    return discord_router.send("brain_proposals", [embed], username="FBA Scout — Ranker")


# --- entry point -----------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Train the shadow ranker + champion/challenger eval.")
    ap.add_argument("--out-dir", default=os.environ.get(
        "RANKER_OUT_DIR", os.path.join(MODELS_DIR, _dt.date.today().isoformat())))
    ap.add_argument("--dry-run", action="store_true", help="no uploads, no Discord post")
    args = ap.parse_args(argv)

    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(HERE, ".env"))
    except Exception:
        pass

    assembled = build_dataset()
    fp = training_set_fingerprint(assembled)

    if not args.dry_run:
        last_fp = fetch_last_fingerprint()
        if last_fp is not None and fp == last_fp:
            print(f"[train_ranker] no new data since last run (row_count={fp['row_count']}) — "
                 "skipped (no Discord post, no training)")
            return 0

    result = train_and_evaluate(assembled)
    block = render_report(result)
    append_report(block)
    print(block.encode("ascii", "replace").decode())

    artifact_upload_ok = True  # nothing to upload when refused/dry-run — not a failure
    if not result.get("refused") and not args.dry_run:
        paths = save_artifacts(result, args.out_dir)
        uploaded = upload_to_storage(paths, _dt.date.today().isoformat())
        print(f"[train_ranker] artifacts: {len(paths)} saved, {uploaded} uploaded to storage")
        artifact_upload_ok = uploaded > 0
    if not args.dry_run:
        if artifact_upload_ok:
            # Stored regardless of refused/trained so a repeated refusal with no new data also
            # skips next time, instead of re-posting the same "not enough data" message every
            # cadence. Skipped when a REAL training run's artifact upload failed (review fix,
            # 2026-07-06): storing the fingerprint then would freeze the skip guard believing
            # this data was already trained on, while ranker/current/ actually stays stale or
            # missing — the next tick would see fp == last_fp and skip forever instead of
            # retrying the upload.
            upload_fingerprint(fp)
        else:
            print("[train_ranker] artifact upload failed — NOT storing the fingerprint, so the "
                 "next run retries training+upload instead of silently freezing a stale model")
        post_summary(result)
    # A refusal is an HONEST outcome, not a failure — exit 0 so the scheduled job stays green
    # until data exists; real errors raise and exit non-zero via the traceback.
    return 0


if __name__ == "__main__":
    sys.exit(main())
