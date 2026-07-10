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
import socket
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
    """AUC + top-N precision/lift for one scorer. None scores rank last. AUC is None when only
    one class is present (never fabricated).

    ML audit fix (2026-07-09): the raw winners_in_top count is information-free at this corpus's
    ~77-94% positive base rate (random ordering expects ~7.7-9.4/10 — the committed 2026-07-05
    report proved it: a champion with AUC 0.329, WORSE than random, still scored 10/10). Every
    surface now gets base_rate/precision_at_top/lift_at_top so the count can be read against
    chance: lift 1.0 = indistinguishable from random ordering."""
    import numpy as np
    from sklearn.metrics import roc_auc_score
    s = np.array([(-1e18 if v is None else float(v)) for v in scores])
    y = np.array(y)
    auc = float(roc_auc_score(y, s)) if len(set(y.tolist())) > 1 else None
    order = np.argsort(-s)
    top = order[:top_n]
    n_top = min(top_n, len(y))
    base_rate = round(float(y.mean()), 3) if len(y) else None
    precision = round(float(y[top].sum()) / n_top, 3) if n_top else None
    lift = (round(precision / base_rate, 2) if precision is not None and base_rate else None)
    return {"auc": auc, "winners_in_top": int(y[top].sum()), "top_n": n_top,
            "base_rate": base_rate, "precision_at_top": precision, "lift_at_top": lift}


def auc_delta_ci(champ_scores: List[Optional[float]], chall_scores: List[Optional[float]],
                 y: List[int], n_boot: int = 500) -> Optional[Dict[str, float]]:
    """Paired bootstrap 95% CI of (challenger AUC − champion AUC) on the SHARED validation
    slice (ML audit fix, 2026-07-09): the Hanley-McNeil SE of a single AUC at this corpus's
    val sizes (~0.03-0.05) exceeds PROMOTION_AUC_MARGIN (0.02), so a point-estimate margin win
    can be pure noise — the gate now also demands the CI's lower bound clear zero. Deterministic
    (fixed-seed RNG — this runs inside the reproducible training path). None when either scorer
    can't produce an AUC (single-class slice) — never fabricated."""
    import numpy as np
    from sklearn.metrics import roc_auc_score
    y_arr = np.array(y)
    if len(set(y_arr.tolist())) < 2:
        return None
    champ = np.array([(-1e18 if v is None else float(v)) for v in champ_scores])
    chall = np.array([(-1e18 if v is None else float(v)) for v in chall_scores])
    rng = np.random.RandomState(42)
    deltas = []
    n = len(y_arr)
    for _ in range(n_boot):
        idx = rng.randint(0, n, n)
        y_b = y_arr[idx]
        if len(set(y_b.tolist())) < 2:
            continue  # a resample with one class can't score — skip, never fabricate
        deltas.append(float(roc_auc_score(y_b, chall[idx]) - roc_auc_score(y_b, champ[idx])))
    if len(deltas) < n_boot // 2:
        return None  # too many degenerate resamples for an honest interval
    lo, hi = np.percentile(deltas, [2.5, 97.5])
    return {"delta_low": round(float(lo), 4), "delta_high": round(float(hi), 4),
            "delta_mean": round(float(np.mean(deltas)), 4), "n_boot": len(deltas)}


PROMOTION_AUC_MARGIN = 0.02
PROMOTION_CONSECUTIVE_WINS_REQUIRED = 3
PROMOTION_MIN_VAL_ROWS = 150  # small-sample-caution threshold, either split


def verdict_line(champ: Dict[str, Any], chall: Dict[str, Any], margin: float = PROMOTION_AUC_MARGIN) -> str:
    """The explicit champion/challenger verdict (V3 spec wording). The challenger must BEAT the
    champion's AUC by `margin` to even claim a win — and a win still only REQUESTS promotion."""
    ca, xa = champ.get("auc"), chall.get("auc")
    if ca is None or xa is None:
        return "VERDICT: INCONCLUSIVE (single-class validation slice) — challenger stays shadow."
    if xa > ca + margin:
        return ("VERDICT: CHALLENGER WINS on held-out AUC — promotion requires human approval "
                "(flip scoring.rankingChampion via fba-brain-updater; nothing was auto-applied).")
    return "VERDICT: CHALLENGER LOSES — stays shadow."


def _run_won(run: Dict[str, Any]) -> Optional[bool]:
    """None (inconclusive) breaks a consecutive-wins streak the same as a loss — a refused or
    single-class run doesn't confirm the streak continued.

    ML audit fix (2026-07-09): a prior run now counts as a WIN only if its recorded
    time-held-out split ALSO confirmed (migration 015 persists it) — the streak exists to prove
    consistency on the same evidence the gate demands of THIS run, so a prior win with no
    recorded forward-generalization evidence (pre-015 rows: NULL) is inconclusive, not a win.
    That means the streak honestly restarts from the first post-015 run rather than crediting
    historical wins the gate can no longer verify on both axes."""
    if run.get("refused"):
        return None
    ca, xa = run.get("champion_auc"), run.get("challenger_auc")
    if ca is None or xa is None:
        return None
    if not (xa > ca + PROMOTION_AUC_MARGIN):
        return False
    tsc, tsx = run.get("time_split_champion_auc"), run.get("time_split_challenger_auc")
    if tsc is None or tsx is None:
        return None  # no recorded time-split evidence — can't confirm the streak on both axes
    return tsx > tsc + PROMOTION_AUC_MARGIN


def promotion_gate(result: Dict[str, Any], recent_runs: List[Dict[str, Any]],
                   content_hash: Optional[str] = None) -> Dict[str, Any]:
    """Whether this run's challenger win is ACTUALLY promotion-ready (ML de-bias audit,
    2026-07-09; design reviewed with fba-ranker-architect) — a single run's win is not enough:
    run 4 flipped from losing to winning (~0.73 vs ~0.69 AUC) on only ~186 val rows the SAME run
    a de-bias fix widened category coverage from 4 to 13 — promising, not proof. Requires ALL of:

      1. This run's primary (by-ASIN GROUP split) win by PROMOTION_AUC_MARGIN.
      2. CONSECUTIVE wins: the challenger also won, by the same margin, on the
         PROMOTION_CONSECUTIVE_WINS_REQUIRED-1 recorded runs immediately before this one — a
         strict run of consecutive wins, not a majority (a 2-of-3 record that tolerates a loss in
         between isn't "consistent," it's "more wins than losses"). An inconclusive/refused run
         breaks the streak. Fewer prior runs than required -> not yet consistent, honestly so.
      3. The time-held-out split (result["time_split"] — forward generalization, a DIFFERENT axis
         than the by-ASIN group split) ALSO shows a win by the same margin.

    Also flags small-sample caution (either split's val_rows below PROMOTION_MIN_VAL_ROWS)
    regardless of whether the gate is otherwise satisfied — the corpus is still small and, right
    now, still actively de-biasing (composition shifting run over run), which is weaker
    consistency evidence than the same streak on a stable corpus.

    This function only shapes the REPORT/Discord recommendation text. scoring.rankingChampion is
    never written here or anywhere in this file — a human always makes the actual promotion call
    via fba-brain-updater.

    ML audit fix (2026-07-09): `content_hash` (this run's training-set fingerprint hash) guards
    against STREAK PADDING — training is fully deterministic (random_state=42, hash/sort-based
    splits), so a re-run on an identical dataset reproduces the identical win. Prior runs whose
    recorded content_hash duplicates this run's (or an already-counted one) are collapsed before
    the streak walk: a win only extends the streak when the training set actually changed."""
    champ, chall = result.get("champion") or {}, result.get("challenger") or {}
    ca, xa = champ.get("auc"), chall.get("auc")
    margin_win = ca is not None and xa is not None and xa > ca + PROMOTION_AUC_MARGIN
    # ML audit fix (2026-07-09, no-uncertainty-treatment finding): the single-AUC standard error
    # at these val sizes (~0.03-0.05, Hanley-McNeil) EXCEEDS the 0.02 point-estimate margin, so
    # a margin win alone can be pure noise. When a paired-bootstrap CI on the AUC delta is
    # available, the win must also clear it (CI lower bound > 0 — the gap is distinguishable
    # from zero at 95%). No CI (single-class slice / degenerate resamples) -> margin-only,
    # honestly weaker, and the reason says which standard was applied.
    ci = result.get("auc_delta_ci")
    ci_clears = ci is None or ci.get("delta_low", -1) > 0
    primary_win = margin_win and ci_clears

    seen_hashes = {content_hash} if content_hash else set()
    distinct_prior: List[Dict[str, Any]] = []
    for r in recent_runs:
        h = r.get("content_hash")
        if h and h in seen_hashes:
            continue  # duplicate dataset — the same deterministic result, not new evidence
        if h:
            seen_hashes.add(h)
        distinct_prior.append(r)

    consecutive_wins = 0
    for won in [primary_win] + [_run_won(r) for r in distinct_prior]:
        if not won:
            break
        consecutive_wins += 1
    consistent = consecutive_wins >= PROMOTION_CONSECUTIVE_WINS_REQUIRED

    time_split = result.get("time_split") or {}
    ts_champ, ts_chall = time_split.get("champion_auc"), time_split.get("challenger_auc")
    time_split_win = (ts_champ is not None and ts_chall is not None
                     and ts_chall > ts_champ + PROMOTION_AUC_MARGIN)

    val_rows = result.get("val_rows") or 0
    time_val_rows = time_split.get("val_rows") or 0
    small_sample = val_rows < PROMOTION_MIN_VAL_ROWS or time_val_rows < PROMOTION_MIN_VAL_ROWS

    ready = primary_win and consistent and time_split_win
    if not primary_win:
        if margin_win and not ci_clears:
            reason = (f"challenger beat the margin on the primary split but the bootstrap 95% "
                     f"CI on the AUC gap does not clear zero (low {ci.get('delta_low')}) — "
                     f"statistically indistinguishable from noise at this val size")
        else:
            reason = "challenger did not win this run's primary (by-ASIN) split"
    elif not consistent:
        reason = (f"won {consecutive_wins}/{PROMOTION_CONSECUTIVE_WINS_REQUIRED} needed "
                 f"CONSECUTIVE distinct-dataset runs (including this one) — needs a run of "
                 f"wins on changing data, not just this one")
    elif not time_split:
        reason = ("primary split + consistency both pass, but no time-held-out split was "
                 "computable this run (corpus too small/single-class for a chronological split)")
    elif not time_split_win:
        reason = (f"primary split win + consistent across recent runs, but the time-held-out "
                 f"(forward-generalization) split does NOT confirm it (champion "
                 f"{ts_champ}, challenger {ts_chall})")
    else:
        reason = ("primary split win (bootstrap CI clears zero) + consistent across distinct-"
                 "dataset runs + time-held-out split confirms it")
        # Standing caveat the docstring promises (ML audit 2026-07-09): every streak run trains
        # on a DIFFERENT corpus snapshot while de-biasing is active — say so in the READY text
        # itself, not only when samples are small.
        reason += (" — note: each streak run trained on a different corpus snapshot "
                  "(composition still shifting during de-bias); weaker evidence than the same "
                  "streak on a stable corpus")
    if small_sample:
        reason += (f" — SMALL-SAMPLE CAUTION: val_rows={val_rows}, "
                  f"time_split val_rows={time_val_rows} (below {PROMOTION_MIN_VAL_ROWS})")

    return {
        "ready": ready, "reason": reason, "primary_win": primary_win,
        "margin_win": margin_win, "ci_clears": ci_clears,
        "consecutive_wins": consecutive_wins,
        "consecutive_wins_required": PROMOTION_CONSECUTIVE_WINS_REQUIRED,
        "time_split_win": time_split_win, "small_sample": small_sample,
    }


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


def slice_breakdown(val_rows: List[Dict[str, Any]], proba: List[float],
                    key_fn, max_groups: Optional[int] = None,
                    min_n: int = 1) -> Dict[str, Any]:
    """Per-group rank_metrics on the SAME held-out slice/predictions, grouped by key_fn(row).
    A group with only one class present is reported as a count only — AUC stays None rather
    than fabricated. max_groups keeps only the largest-N groups (by n); min_n drops groups too
    small to say anything about.

    ML audit fix (2026-07-09): generalized from the sample_source-only breakdown so the report
    can ALSO slice by category and brand — ML_DEBIAS_PLAN.md's monitoring section requires
    per-category/per-brand metric slices specifically so a model that only works on
    toys/Crocs is caught BEFORE promotion; until this, only the sample-source slice existed."""
    by_key: Dict[str, List[int]] = {}
    for i, r in enumerate(val_rows):
        by_key.setdefault(key_fn(r), []).append(i)
    groups = sorted(by_key.items(), key=lambda kv: -len(kv[1]))
    if max_groups is not None:
        groups = groups[:max_groups]
    out: Dict[str, Any] = {}
    for key, idxs in groups:
        if len(idxs) < min_n:
            continue
        y_sub = [1 if val_rows[i]["label"] else 0 for i in idxs]
        p_sub = [float(proba[i]) for i in idxs]
        if len(set(y_sub)) < 2:
            out[key] = {"n": len(idxs), "auc": None}
        else:
            out[key] = {"n": len(idxs), **rank_metrics(p_sub, y_sub, top_n=min(10, len(idxs)))}
    return out


def source_breakdown(val_rows: List[Dict[str, Any]], proba: List[float]) -> Dict[str, Any]:
    """Per sample_source rank_metrics on the SAME held-out slice/predictions (Session 55,
    learning.sampling): onpolicy vs explore vs dealfeed, never blended. Rows without a
    sample_source (gold/silver rows, which predate this tagging) group under 'n/a'."""
    return slice_breakdown(val_rows, proba, lambda r: r.get("sample_source") or "n/a")


def new_signal_importance(clf) -> Dict[str, float]:
    """Each Session 55 signal feature's fitted importance — the evidence render_report()'s 'new
    signals' section shows so a human can decide keep-or-cut.

    Prefers LightGBM's feature_importances_ (split-count based, normalized to a 0-1 share of
    the model's total — an exactly-average feature owns 1/len(NUMERIC_FEATURES) ≈ 0.036 at the
    current 28 features; render_report flags anything below HALF that dynamic average, never a
    fixed constant that could sit above average — ML audit fix 2026-07-09). Falls back to a
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


# --- ML de-bias: corpus concentration + caps (2026-07-09, ML_DEBIAS_PLAN.md Lever B) -----------
# Live-measured root cause: the training corpus is 82.5% "toys" / top-5 brands 37% (Crocs 15.6% +
# Jellycat 13.9% alone ~30%) -- a ranker trained on this learns "toys/Crocs/Jellycat", not
# generalizable profit signal. This caps the TRAINING ASSEMBLY only (labels.assemble_training_rows()
# and the raw backtest_rows lake are untouched -- calibration_report.py and any future consumer of
# labels.py still see the TRUE distribution; only this ranker's own train/val split is balanced).
DEFAULT_MAX_BRAND_CORPUS_SHARE = 0.06
DEFAULT_MAX_CATEGORY_CORPUS_SHARE = 0.30
DEFAULT_TOP5_BRAND_SHARE_ALARM = 0.20

# ML_DEBIAS_PLAN.md's "Monitoring" section states these two alarm thresholds directly (not via a
# proposed brain key, unlike the three defaults above) — kept as constants rather than brain-read
# since the plan ties them to a fixed rule ("any category > 30%", "two brands > 25%"), not a
# tunable operational knob.
CATEGORY_CONCENTRATION_ALARM = 0.30
BRAND_CONCENTRATION_ALARM = 0.25


def sampling_caps_config() -> Dict[str, float]:
    """learning.sampling's cap/alarm knobs from the brain, single-sourced like every other
    threshold in this project. NOT YET a real ai-brain.json key as of this fix (proposed via
    fba-brain-updater in learning-hub/tracking/brain-proposals.md, pending Mehmet's approval since
    it changes what the model sees) -- these defaults match the exact values proposed there, so
    the cap is already active with sensible numbers and picks up the brain's own value the moment
    the proposal is approved, with no code change needed either way."""
    try:
        with open(BRAIN_PATH, encoding="utf-8") as f:
            sampling = ((json.load(f) or {}).get("learning") or {}).get("sampling") or {}
    except Exception:
        sampling = {}
    return {
        "max_brand_share": float(sampling.get("maxBrandCorpusShare", DEFAULT_MAX_BRAND_CORPUS_SHARE)),
        "max_category_share": float(sampling.get("maxCategoryCorpusShare", DEFAULT_MAX_CATEGORY_CORPUS_SHARE)),
        "top5_brand_alarm": float(sampling.get("top5BrandShareAlarm", DEFAULT_TOP5_BRAND_SHARE_ALARM)),
    }


# ML audit fix (2026-07-09): db.py documents these three as "LIVE-ONLY (not backfillable)" —
# real values on live-captured (silver/gold) rows, structurally NaN on every backtest row.
# train_and_evaluate neutralizes them whenever training mixes tiers so feature PRESENCE can't
# encode the label tier (doctrine §4).
EBAY_LIVE_ONLY_FEATURES = ("ebay_active_listing_count", "median_active_price_vs_amazon_ratio",
                           "ebay_stale")

# Per-tier sample weights (doctrine §2: "Weight/trust them accordingly; never treat a backtest
# sim label as equal to a real gold outcome"). Brain-overridable via learning.tierWeights —
# these defaults are deliberately conservative multipliers, and bronze stays EXCLUDED from
# training entirely (it's an auxiliary agreement metric, never a label — see bronze_agreement).
DEFAULT_TIER_WEIGHTS = {"backtest": 1.0, "silver": 2.0, "gold": 4.0}


def tier_weights_config() -> Dict[str, float]:
    try:
        with open(BRAIN_PATH, encoding="utf-8") as f:
            tw = ((json.load(f) or {}).get("learning") or {}).get("tierWeights") or {}
    except Exception:
        tw = {}
    return {t: float(tw.get(t, d)) for t, d in DEFAULT_TIER_WEIGHTS.items()}


def tier_sample_weights(rows: List[Dict[str, Any]]):
    """One weight per row from its label_quality tier — passed as sample_weight to the fit,
    composing multiplicatively with class_weight='balanced'. Unknown/missing tiers weigh 1.0
    (the backtest baseline), never 0 (a silent row-drop)."""
    import numpy as np
    tw = tier_weights_config()
    return np.array([tw.get(r.get("label_quality") or "backtest", 1.0) for r in rows])


def _row_brand(r: Dict[str, Any]) -> str:
    return (r.get("features") or {}).get("brand") or "unknown"


def _row_category(r: Dict[str, Any]) -> str:
    return (r.get("features") or {}).get("category") or "unknown"


def corpus_concentration(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Brand/category composition + concentration (HHI, top-brand/top-5 shares, distinct counts)
    for a set of training rows — the measurement ML_DEBIAS_PLAN.md's targets are defined against
    (no category > 30%, no brand > 6%, top-5 < 20%, >= 10 categories). HHI here is the standard
    sum-of-squared-shares on a 0-1 scale (0 = perfectly even, 1 = a single group owns everything)."""
    total = len(rows)
    if total == 0:
        return {"total": 0, "distinct_brands": 0, "distinct_categories": 0,
                "top_brand_share": 0.0, "top5_brand_share": 0.0, "top_category_share": 0.0,
                "hhi_brand": 0.0, "hhi_category": 0.0, "brand_shares": {}, "category_shares": {}}
    brand_counts: Dict[str, int] = {}
    category_counts: Dict[str, int] = {}
    for r in rows:
        b = _row_brand(r)
        c = _row_category(r)
        brand_counts[b] = brand_counts.get(b, 0) + 1
        category_counts[c] = category_counts.get(c, 0) + 1
    brand_shares = {k: v / total for k, v in brand_counts.items()}
    category_shares = {k: v / total for k, v in category_counts.items()}
    sorted_brand_shares = sorted(brand_shares.values(), reverse=True)
    return {
        "total": total,
        "distinct_brands": len(brand_counts),
        "distinct_categories": len(category_counts),
        "top_brand_share": sorted_brand_shares[0] if sorted_brand_shares else 0.0,
        "top5_brand_share": sum(sorted_brand_shares[:5]),
        "top_category_share": max(category_shares.values()) if category_shares else 0.0,
        "hhi_brand": sum(s * s for s in brand_shares.values()),
        "hhi_category": sum(s * s for s in category_shares.values()),
        "brand_shares": brand_shares,
        "category_shares": category_shares,
    }


def apply_corpus_caps(rows: List[Dict[str, Any]], max_brand_share: float,
                      max_category_share: float) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Subsamples `rows` so no single category exceeds max_category_share and no single brand
    exceeds max_brand_share of the ORIGINAL total (ML_DEBIAS_PLAN.md Lever B). Keeps the MOST
    RECENT windows per over-represented group (by simulation_date, descending) rather than
    dropping ASINs outright — an ASIN with many windows in an over-represented category still
    contributes its freshest signal, just not all of it. Category cap applied first (today's
    skew is categorical: 82.5% toys), then brand cap on the result. Returns (capped_rows,
    {"before": concentration, "after": concentration, "dropped": n})."""
    before = corpus_concentration(rows)
    total = before["total"]
    if total == 0:
        return rows, {"before": before, "after": before, "dropped": 0}

    def _cap_by(rows_in: List[Dict[str, Any]], key_fn, max_share: float) -> List[Dict[str, Any]]:
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows_in:
            groups.setdefault(key_fn(r), []).append(r)
        # Nothing to rebalance against when the whole set is one brand/category (a young/small
        # corpus, or a test fixture that isn't exercising diversity at all) -- capping here would
        # only destroy signal, not create diversity the data doesn't contain. Skip the cap
        # entirely in that case rather than aggressively shrinking toward max(1, ...).
        if len(groups) <= 1:
            return rows_in
        max_n = max(1, int(total * max_share))
        out: List[Dict[str, Any]] = []
        for group in groups.values():
            if len(group) <= max_n:
                out.extend(group)
                continue
            # ML audit fix (2026-07-09, leakage-adjacent): this used to keep the MOST RECENT
            # windows per over-represented group — which piled every capped group's survivors
            # into the late end of the pooled timeline, so split_by_time's validation slice
            # (the latest 30%) was DOMINATED by exactly the groups the cap de-emphasized: the
            # gate's forward-generalization check ran on a distorted split. Deterministic
            # hash-based subsampling keeps each group's original date distribution intact
            # (stable across runs, no Math.random — same _stable_hash convention as
            # split_by_asin).
            import backtest as _bt
            group_sorted = sorted(
                group, key=lambda r: _bt._stable_hash(f"{r.get('asin')}|{r.get('simulation_date')}"))
            out.extend(group_sorted[:max_n])
        return out

    capped = _cap_by(rows, _row_category, max_category_share)
    capped = _cap_by(capped, _row_brand, max_brand_share)
    after = corpus_concentration(capped)
    return capped, {"before": before, "after": after, "dropped": total - len(capped)}


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

    # ML de-bias (2026-07-09, ML_DEBIAS_PLAN.md Lever B): cap brand/category concentration in the
    # ASSEMBLY this ranker actually trains/validates on. Applied here (not in labels.py) so
    # calibration_report.py's diagnostic still sees the TRUE uncapped distribution — only this
    # ranker's own split is balanced.
    caps = sampling_caps_config()
    rows, concentration = apply_corpus_caps(
        rows, max_brand_share=caps["max_brand_share"], max_category_share=caps["max_category_share"])

    # ML audit fix (2026-07-09, label-tier encoding): the three eBay features are LIVE-ONLY —
    # structurally absent (NaN) on every backtest row but real values/booleans on live-captured
    # (silver/gold) rows, so their mere PRESENCE would encode the label tier the moment tiers
    # mix in training (doctrine §4: the model must not infer tier from feature presence).
    # Neutralize them to missing for ALL rows whenever the set mixes tiers; single-tier sets
    # keep them (nothing to discriminate). Shallow-copies features — never mutates the caller's
    # rows.
    ebay_neutralized = False
    tiers_present = {r.get("label_quality") or "backtest" for r in rows}
    if len(tiers_present) > 1:
        rows = [{**r, "features": {k: (None if k in EBAY_LIVE_ONLY_FEATURES else v)
                                   for k, v in (r.get("features") or {}).items()}}
               for r in rows]
        ebay_neutralized = True

    train, val = backtest.split_by_asin(rows, val_fraction=0.3)
    if not train or not val:
        return {"refused": True, "reason": "by-ASIN split left an empty side",
                "by_tier": assembled.get("by_tier", {}), "concentration": concentration}
    Xtr, ytr = build_matrix(train)
    Xva, yva = build_matrix(val)
    if len(set(ytr.tolist())) < 2:
        return {"refused": True, "reason": "training side has one class after the by-ASIN split",
                "by_tier": assembled.get("by_tier", {}), "concentration": concentration}

    # ML audit fix (2026-07-09, doctrine §2 "weight/trust tiers accordingly"): gold/silver/
    # backtest rows used to fit at identical per-row weight, so 1455 simulated backtest labels
    # fully drowned the ~70 real-signal silver rows. Per-tier sample weights now compose
    # multiplicatively with class_weight="balanced" (LightGBM applies both).
    w_tr = tier_sample_weights(train)
    clf = lgb.LGBMClassifier(class_weight="balanced", random_state=42, verbosity=-1,
                             **_lightgbm_params(len(Xtr))).fit(Xtr, ytr, sample_weight=w_tr)
    proba = clf.predict_proba(Xva)[:, 1]

    proba_list = [float(p) for p in proba]
    champ_scores_list = champion_scores(val)
    chall = rank_metrics(proba_list, yva.tolist())
    champ = rank_metrics(champ_scores_list, yva.tolist())
    # Paired bootstrap CI on the AUC gap (ML audit 2026-07-09): the single-AUC SE at these val
    # sizes (~0.03-0.05) exceeds the 0.02 point-estimate margin — the gate reads this too.
    delta_ci = auc_delta_ci(champ_scores_list, proba_list, yva.tolist())

    # ML de-bias audit (2026-07-09) — promotion-gate part 2: split_by_asin is a same-time GROUP
    # split (prevents an ASIN's windows straddling train/val) but was never time-based
    # (ml-doctrine.md §4's tracked gap). A time-held-out split additionally tests whether the
    # model generalizes FORWARD, not just to unseen ASINs at the same point in time — a single
    # run's by-ASIN win (e.g. run 4's ~0.73 vs ~0.69 on ~186 val rows) is not proof of that.
    # Best-effort: degrades to None (never blocks the primary training result) if the corpus is
    # too small/single-class for a meaningful chronological split.
    time_split = None
    try:
        # ML audit fix (2026-07-09): silver/gold rows carry no simulation_date, and the sort
        # used to place them as "" — BEFORE every ISO date — guaranteeing the corpus's NEWEST
        # data (live-captured rows) landed in the time-split's TRAIN side: future-period
        # information training the forward-generalization check. Dateless rows are now excluded
        # from this evaluation entirely (they can't be placed on a timeline honestly) and the
        # excluded count is reported, never hidden.
        dated_rows = [r for r in rows if r.get("simulation_date")]
        excluded_dateless = len(rows) - len(dated_rows)
        time_train, time_val = backtest.split_by_time(dated_rows, val_fraction=0.3)
        if time_train and time_val:
            Xtt, ytt = build_matrix(time_train)
            Xtv, ytv = build_matrix(time_val)
            if len(set(ytt.tolist())) >= 2 and len(set(ytv.tolist())) >= 2:
                time_clf = lgb.LGBMClassifier(class_weight="balanced", random_state=42,
                                             verbosity=-1, **_lightgbm_params(len(Xtt))).fit(
                                                 Xtt, ytt, sample_weight=tier_sample_weights(time_train))
                time_proba = time_clf.predict_proba(Xtv)[:, 1]
                time_chall = rank_metrics([float(p) for p in time_proba], ytv.tolist())
                time_champ = rank_metrics(champion_scores(time_val), ytv.tolist())
                time_split = {
                    "train_rows": len(time_train), "val_rows": len(time_val),
                    "champion_auc": time_champ.get("auc"), "challenger_auc": time_chall.get("auc"),
                    "verdict": verdict_line(time_champ, time_chall),
                    "excluded_dateless": excluded_dateless,
                }
    except Exception as e:
        print(f"[train_ranker] time-held-out split evaluation failed (non-fatal, primary result "
             f"unaffected): {type(e).__name__}")

    return {
        "refused": False,
        "model": clf, "scaler": None, "features": list(NUMERIC_FEATURES),
        "train_rows": len(train), "val_rows": len(val),
        "train_asins": len({r["asin"] for r in train if r.get("asin")}),
        "val_asins": len({r["asin"] for r in val if r.get("asin")}),
        "by_tier": assembled.get("by_tier", {}),
        "champion": champ, "challenger": chall,
        "verdict": verdict_line(champ, chall),
        "time_split": time_split,
        "silver_caveat": assembled.get("silver_caveat", ""),
        "bronze_agreement": bronze_agreement(clf, None, assembled.get("bronze_rows") or []),
        "bronze_caveat": assembled.get("bronze_caveat", ""),
        "by_source": source_breakdown(val, proba_list),
        # ML_DEBIAS_PLAN.md monitoring (ML audit 2026-07-09): per-category/per-brand metric
        # slices on the held-out set — the specific safeguard against promoting a model that
        # only works on toys/Crocs. min_n=10: below that a slice AUC is noise, not signal.
        "by_category": slice_breakdown(val, proba_list, _row_category, max_groups=8, min_n=10),
        "by_brand": slice_breakdown(val, proba_list, _row_brand, max_groups=8, min_n=10),
        "auc_delta_ci": delta_ci,
        "tier_weights": tier_weights_config(),
        "ebay_live_only_neutralized": ebay_neutralized,
        "new_signal_importance": new_signal_importance(clf),
        "concentration": concentration,
        # ML_DEBIAS_PLAN.md's exact monitoring spec (raw pre-cap composition, so this reflects
        # whether COLLECTION is still skewed — independent of this run's own assembly-time cap):
        # alarm if any single category > 30%, or two-or-more individual brands each > 25%.
        "concentration_alarm": (
            concentration["before"]["top_category_share"] > CATEGORY_CONCENTRATION_ALARM
            or sum(1 for s in concentration["before"]["brand_shares"].values()
                  if s > BRAND_CONCENTRATION_ALARM) >= 2
        ),
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

    def _topline(m):
        # Lift vs base rate (ML audit 2026-07-09): the raw winners-in-top count is
        # information-free at a ~77-94% positive base rate — print it WITH its chance baseline.
        auc = round(m["auc"], 3) if m.get("auc") is not None else "n/a"
        if m.get("precision_at_top") is not None and m.get("base_rate"):
            return (f"AUC {auc} · top-{m['top_n']} precision {m['precision_at_top']:.2f} vs "
                   f"base {m['base_rate']:.2f} (lift {m['lift_at_top']}x)")
        return f"AUC {auc} · winners in top {m['top_n']}: {m['winners_in_top']}"

    lines += [
        f"- Split BY ASIN: train {result['train_rows']} rows / {result['train_asins']} asins; "
        f"val {result['val_rows']} rows / {result['val_asins']} asins",
        f"- CHAMPION (deterministic triage): {_topline(ch)}",
        f"- CHALLENGER (classical model, shadow): {_topline(xl)}",
    ]
    ci = result.get("auc_delta_ci")
    if ci:
        lines.append(f"- AUC gap (challenger − champion) paired-bootstrap 95% CI: "
                     f"[{ci['delta_low']}, {ci['delta_high']}] (mean {ci['delta_mean']}, "
                     f"{ci['n_boot']} resamples) — a gap whose CI includes zero is noise, not a win")
    lines += [
        "",
        f"**{result['verdict']}**",
        "",
        "Caveats: backtest rows are the weakest tier (simulated buy cost, no execution/"
        "sell-through); " + (result.get("silver_caveat") or ""),
        "Promotion is HUMAN-ONLY via the brain key scoring.rankingChampion — this job never "
        "touches ai-brain.json.", "",
    ]
    tw = result.get("tier_weights")
    if tw:
        neut = (" · eBay live-only features neutralized this run (mixed tiers — presence would "
               "encode the label tier)" if result.get("ebay_live_only_neutralized") else "")
        lines.append(f"- Tier sample-weights (doctrine §2, brain key learning.tierWeights): "
                     + ", ".join(f"{t}={w}" for t, w in sorted(tw.items())) + neut)
        lines.append("")
    ts = result.get("time_split")
    if ts:
        dateless = (f"; {ts['excluded_dateless']} dateless (silver/gold) row(s) excluded — "
                   f"they can't be placed on a timeline honestly"
                   if ts.get("excluded_dateless") else "")
        lines.append(
            f"- Time-held-out split (forward-generalization check — a DIFFERENT axis than the "
            f"by-ASIN group split above; train {ts['train_rows']} / val {ts['val_rows']} rows, "
            f"chronologically split{dateless}): CHAMPION AUC "
            f"{ts['champion_auc'] if ts['champion_auc'] is not None else 'n/a'} · CHALLENGER AUC "
            f"{ts['challenger_auc'] if ts['challenger_auc'] is not None else 'n/a'} — {ts['verdict']}")
        lines.append("")
    gate = result.get("promotion_gate")
    if gate:
        # Small samples get their own STATUS word, not just a buried mid-sentence caution (ML
        # audit 2026-07-09): a human skimming for the bold headline must see the caveat there.
        if gate["ready"]:
            status = ("READY — SMALL-SAMPLE CAUTION, treat as provisional" if gate.get("small_sample")
                     else "READY FOR HUMAN REVIEW")
        else:
            status = "NOT YET PROMOTION-READY"
        lines.append(f"- **Promotion gate: {status}** — {gate['reason']}")
        lines.append("")
    conc = result.get("concentration")
    if conc:
        b, a = conc["before"], conc["after"]
        alarm = " 🚨 **ALARM: category>30% or 2+ brands>25% — collection is still skewed**" if result.get("concentration_alarm") else ""
        lines.append(f"- Corpus concentration (ML_DEBIAS_PLAN.md targets: no category >30%, no "
                     f"brand >6%, top-5 <20%, >=10 categories):{alarm}")
        lines.append(f"  - Before cap: {b['distinct_brands']} brands / {b['distinct_categories']} "
                     f"categories, top-brand {b['top_brand_share']*100:.1f}%, top-5 "
                     f"{b['top5_brand_share']*100:.1f}%, top-category {b['top_category_share']*100:.1f}%, "
                     f"HHI(brand) {b['hhi_brand']:.3f}, HHI(category) {b['hhi_category']:.3f}")
        if conc["dropped"]:
            lines.append(f"  - After assembly-time cap: dropped {conc['dropped']} row(s) from "
                         f"over-represented cells -> {a['distinct_brands']} brands / "
                         f"{a['distinct_categories']} categories, top-brand "
                         f"{a['top_brand_share']*100:.1f}%, top-5 {a['top5_brand_share']*100:.1f}%, "
                         f"top-category {a['top_category_share']*100:.1f}% (raw lake untouched — "
                         f"this cap only shapes what THIS run trains/validates on)")
        else:
            lines.append("  - No cap needed this run (already within targets)")
        cat_shares = sorted(b["category_shares"].items(), key=lambda kv: -kv[1])[:10]
        lines.append("  - Category shares (pre-cap): " +
                     ", ".join(f"{k} {v*100:.1f}%" for k, v in cat_shares))
        lines.append("")
    by_source = result.get("by_source") or {}
    if len(by_source) > 1 or (by_source and "n/a" not in by_source):
        lines.append("- Sampling-source breakdown (held-out slice, same model — never blended):")
        for src, m in sorted(by_source.items()):
            auc_str = m["auc"] if m.get("auc") is not None else "n/a (single class in slice)"
            lines.append(f"  - **{src}**: n={m['n']}, AUC {auc_str}")
        lines.append("")
    # Per-category/per-brand slices (ML audit 2026-07-09, ML_DEBIAS_PLAN.md monitoring): the
    # specific pre-promotion safeguard against a model that only works on toys/Crocs.
    for slice_key, slice_title in (("by_category", "Per-category"), ("by_brand", "Per-brand (top by n)")):
        sl = result.get(slice_key) or {}
        if sl:
            lines.append(f"- {slice_title} held-out slice (n>=10; a slice where the challenger "
                         f"LOSES while winning overall = it only works on the big cells):")
            for key, m in sorted(sl.items(), key=lambda kv: -kv[1]["n"]):
                auc_str = m["auc"] if m.get("auc") is not None else "n/a (single class)"
                lines.append(f"  - **{key}**: n={m['n']}, AUC {auc_str}")
            lines.append("")
    bronze = result.get("bronze_agreement")
    if bronze:
        lines.append(
            f"- Bronze agreement (auxiliary, NOT a training signal): the model agrees with the "
            f"operator's own buy/pass decision on {bronze['agreement_rate']*100:.0f}% of "
            f"{bronze['n']} decision-only row(s) — at predict()'s implicit 0.5 cutoff on "
            f"UNCALIBRATED balanced-class probabilities, so the rate is threshold-dependent, "
            f"not a calibrated accuracy. {result.get('bronze_caveat') or ''}")
        lines.append("")
    importance = result.get("new_signal_importance") or {}
    if importance:
        # ML audit fix (2026-07-09): the old fixed 0.05 flag sat ABOVE the true average share
        # (1/28 features ≈ 0.036), so features earning 25%+ above-average importance were
        # labeled "near-zero removal candidates" — a human following the kill-rule could cut
        # genuinely useful signals. The flag is now half the average share, computed from the
        # actual feature count.
        near_zero = round(0.5 / max(1, len(NUMERIC_FEATURES)), 4)
        lines.append(f"- New signals (Trends/calendar/eBay, Session 55) — normalized feature "
                     f"importance (LightGBM feature_importances_, share of total splits; "
                     f"< {near_zero} = below half the {len(NUMERIC_FEATURES)}-feature average "
                     f"share, flagged as a removal candidate — human decides, same kill-rule "
                     f"as everything else):")
        for name, coef in sorted(importance.items(), key=lambda kv: -abs(kv[1])):
            flag = "" if abs(coef) >= near_zero else " ⚠ below half-average share"
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
    LIVE scoring — NOT the training/evaluation path above. Returns None (never raises) when the
    artifact can't be found/loaded/doesn't have the expected shape — every failure mode degrades
    to "score with the rule/triage formula exactly as if nothing were ever promoted," never a
    crash and never a silent wrong-shaped prediction. Cached per-process (see
    reset_challenger_cache) so repeated calls within one run/burst don't re-read the artifact
    per candidate.

    ML audit fix (2026-07-09, doctrine §5 shadow-by-default — BLOCKER): loading is NO LONGER
    gated on scoring.rankingChampion. Before this fix, load_challenger() returned None unless
    already promoted, so "shadow mode" never actually shadowed: the hourly production path never
    deserialized the model, zero live shadow evidence ever accrued, and the first time the
    model would EVER score a live candidate was in production, post-promotion — the doctrine's
    dead-artifact cautionary tale reopened one hop downstream. Now the artifact is ALWAYS
    best-effort loaded so the challenger scores every candidate in SHADOW (its score is logged
    per lead via the explanation dict, never acted on); the brain key gates ONLY whether
    pipeline._rank_winners uses that score for the real queue ordering — which is the promotion
    decision, and stays human-only."""
    if _challenger_cache["loaded"] and not force:
        return _challenger_cache["model"]
    _challenger_cache["loaded"] = True
    _challenger_cache["model"] = None
    try:
        import joblib
    except Exception:
        print("[train_ranker] joblib unavailable — can't load the ranker artifact, "
             "falling back to the rule score (no shadow scoring this run)")
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
        print("[train_ranker] no ranker artifact available locally or in storage — "
             "falling back to the rule score (no shadow scoring this run)")
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
        conc = result.get("concentration") or {}
        alarmed = bool(result.get("concentration_alarm"))
        conc_line = ""
        if conc:
            b = conc["before"]
            conc_line = (
                f"\n{'🚨 ' if alarmed else ''}Concentration: top-brand {b['top_brand_share']*100:.0f}%, "
                f"top-5 {b['top5_brand_share']*100:.0f}%, top-category {b['top_category_share']*100:.0f}%, "
                f"{b['distinct_brands']} brands / {b['distinct_categories']} categories"
                + (" — **collection still skewed, see ML_DEBIAS_PLAN.md**" if alarmed else ""))
        # ML audit fix (2026-07-09): the gate + time-split used to be computed and then omitted
        # from this embed — the human saw the inviting single-run "CHALLENGER WINS" verdict with
        # none of the evidence the gate exists to demand. This is the PROPOSAL surface, so the
        # gate verdict leads.
        ts = result.get("time_split") or {}
        ts_line = ""
        if ts:
            ts_line = (f"\n**Time-held-out (forward) split:** champion AUC "
                      f"{ts['champion_auc'] if ts['champion_auc'] is not None else 'n/a'} vs challenger "
                      f"{ts['challenger_auc'] if ts['challenger_auc'] is not None else 'n/a'} "
                      f"({ts.get('val_rows')} val rows)")
        gate = result.get("promotion_gate") or {}
        gate_line = ""
        if gate:
            if gate.get("ready"):
                gate_status = ("READY — SMALL-SAMPLE CAUTION, treat as provisional"
                              if gate.get("small_sample") else "READY FOR HUMAN REVIEW")
            else:
                gate_status = "NOT YET PROMOTION-READY"
            gate_line = f"\n**Promotion gate: {gate_status}** — {gate.get('reason')}"
        embed = {
            "title": "🤖 Ranker trained (shadow) — champion vs challenger",
            "color": 0xE24C4C if alarmed else 0x3987E5,
            "description": (
                f"Rows: {result['train_rows']}+{result['val_rows']} (by-ASIN split) · tiers: {tiers}\n"
                f"**Champion (triage formula):** AUC {ch['auc'] if ch['auc'] is not None else 'n/a'}, "
                f"{ch['winners_in_top']}/{ch['top_n']} winners in top\n"
                f"**Challenger (model):** AUC {xl['auc'] if xl['auc'] is not None else 'n/a'}, "
                f"{xl['winners_in_top']}/{xl['top_n']} winners in top\n\n{result['verdict']}"
                f"{ts_line}{gate_line}{conc_line}\n\n"
                "Promotion is human-only: brain key `scoring.rankingChampion` (fba-brain-updater)."),
        }
    return discord_router.send("brain_proposals", [embed], username="FBA Scout — Ranker")


def _ranker_run_fields(result: Dict[str, Any], fp: Dict[str, Any]) -> Dict[str, Any]:
    """Builds one migration-013/014/015 ranker_runs row from a train_and_evaluate() result +
    this training set's fingerprint — the durable, queryable record of champion/challenger AUC
    over time that ranker-report.md (cloud runs never commit it back) and the Discord post
    (human-readable, not queryable) never were.

    ML audit fix (2026-07-09): now also persists the gate's full evidence — content_hash
    (streak-padding guard: which dataset produced this run), the time-held-out split AUCs
    (forward generalization, gate part 3), the promotion_gate verdict itself, and the
    before/after-cap concentration payload (migration 014's column, previously never sent —
    it existed solely for this and stayed NULL on every row)."""
    fields: Dict[str, Any] = {
        "host": socket.gethostname(),
        "refused": bool(result.get("refused")),
        "row_count": fp.get("row_count"),
        "content_hash": fp.get("content_hash"),
        "by_tier": result.get("by_tier") or {},
    }
    if result.get("refused"):
        fields["refusal_reason"] = result.get("reason")
        return fields
    champ = result.get("champion") or {}
    chall = result.get("challenger") or {}
    fields.update({
        "train_rows": result.get("train_rows"),
        "train_asins": result.get("train_asins"),
        "val_rows": result.get("val_rows"),
        "val_asins": result.get("val_asins"),
        "champion_auc": champ.get("auc"),
        "champion_winners_in_top": champ.get("winners_in_top"),
        "challenger_auc": chall.get("auc"),
        "challenger_winners_in_top": chall.get("winners_in_top"),
        "verdict": result.get("verdict"),
        "by_source": result.get("by_source") or {},
    })
    ts = result.get("time_split") or {}
    if ts:
        fields.update({
            "time_split_champion_auc": ts.get("champion_auc"),
            "time_split_challenger_auc": ts.get("challenger_auc"),
            "time_split_val_rows": ts.get("val_rows"),
        })
    if result.get("promotion_gate"):
        fields["promotion_gate"] = result["promotion_gate"]
    conc = result.get("concentration")
    if conc:
        # The alarm bool rides inside the jsonb payload rather than a separate column — the
        # dashboard reads the whole payload anyway.
        fields["concentration"] = {**conc, "alarm": bool(result.get("concentration_alarm"))}
    return fields


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
    # ML de-bias audit (2026-07-09) — promotion-gate part 3: the consistency check needs recent
    # ranker_runs history (a DB read), so it's gated by --dry-run the same way every other impure
    # I/O step in this function already is; train_and_evaluate() itself stays pure/DB-free for
    # testability. A dry run's report simply omits the gate section (render_report degrades to
    # skipping it when "promotion_gate" isn't in result).
    if not result.get("refused") and not args.dry_run:
        import db
        # Fetch more priors than strictly needed — promotion_gate collapses duplicate
        # content_hash rows (streak-padding guard), so extra rows are the dedup headroom.
        recent_runs = db.recent_ranker_runs(limit=(PROMOTION_CONSECUTIVE_WINS_REQUIRED - 1) + 5)
        result["promotion_gate"] = promotion_gate(result, recent_runs,
                                                  content_hash=fp.get("content_hash"))
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
        import db
        db.record_ranker_run(**_ranker_run_fields(result, fp))
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
