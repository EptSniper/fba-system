"""
scout/shadow_outcomes.py — the shadow-outcome tracker (DATA_ENGINE_PLAN.md V1).

The time-sensitive one: a shadow label takes 30 days to mature, so every day the scout runs
without enqueueing candidates is a day of "silver" training data that can never be recovered.

Two jobs:
  1. enqueue_survivors(): after each REAL discovery run, enqueue EVERY hard-gate survivor (bought
     or not) with its pre-decision feature snapshot and a frozen "then" market snapshot, for two
     checkpoints — day 30 and day 60. Idempotent (db upsert on asin+run+checkpoint).
  2. run_rechecks(): a weekly job re-pulls the due candidates' Keepa stats (1-token calls, batched
     100), computes whether each WOULD have profited at its ORIGINAL simulated landed cost, and
     writes the proxy label. Respects a daily token cap so it never starves the live scan.

HONEST CAVEAT (carried into every report via labels.py): a shadow label ignores execution and
sell-through — we never actually bought or sold. It is a weaker signal than a realized (gold)
outcome and is always reported as its own 'silver' tier, never blended silently into gold.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
from typing import Any, Dict, List, Optional

import config
import db
import scoring

log = logging.getLogger("scout.shadow_outcomes")

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN_PATH = os.path.join(HERE, "..", "learning-hub", "data", "ai-brain.json")

SHADOW_CHECKPOINTS = (30, 60)  # days after enqueue
DEFAULT_RECHECK_TOKEN_CAP = 80  # Pro-trickle split (GL1): ~80 tokens/day for shadow rechecks
_ENRICH_BATCH = 100             # Keepa's max ASINs/request (1 token each with our field mix)


def _recheck_token_cap() -> int:
    """learning.tokenBudget.shadowRecheckTokens (added by GL1), default 80. Read live from the
    brain so it tracks the token-budget split without a code change."""
    try:
        with open(BRAIN_PATH, encoding="utf-8") as f:
            tb = ((json.load(f) or {}).get("learning") or {}).get("tokenBudget") or {}
        v = tb.get("shadowRecheckTokens")
        if isinstance(v, (int, float)) and v > 0:
            return int(v)
    except Exception:
        pass
    return DEFAULT_RECHECK_TOKEN_CAP


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


# --- enqueue (after each real discovery run) --------------------------------
def build_enqueue_rows(survivor: Dict[str, Any], run_id: Optional[Any],
                       now: Optional[_dt.datetime] = None) -> List[Dict[str, Any]]:
    """The (up to two) shadow rows for one hard-gate survivor — one per checkpoint. Pure, so it's
    unit-testable without Supabase. landed_cost is the ORIGINAL simulated buy-in (frozen here);
    would_have_profited is later judged against THIS cost, never a re-derived one."""
    asin = survivor.get("asin")
    if not asin:
        return []
    now = now or _now()
    price_then = survivor.get("price")
    landed_cost = scoring.assumed_landed_cost(price_then)
    snapshot = db.feature_snapshot(survivor)  # PRE_DECISION_FEATURES only (leakage-safe)
    rows = []
    for day in SHADOW_CHECKPOINTS:
        rows.append({
            "asin": asin,
            "candidate_run_id": run_id,
            "checkpoint_day": day,
            "enqueued_at": now.isoformat(),
            "due_at": (now + _dt.timedelta(days=day)).isoformat(),
            "landed_cost": landed_cost,
            "price_then": price_then,
            "offers_then": survivor.get("offers"),
            "sales_rank_then": survivor.get("sales_rank"),
            "weight_lb": survivor.get("weight_lb"),
            "category": survivor.get("category"),
            "features_snapshot": snapshot,
            "status": "pending",
        })
    return rows


def enqueue_survivors(survivors: List[Dict[str, Any]], run_id: Optional[Any],
                      now: Optional[_dt.datetime] = None) -> int:
    """Enqueue every gate-survivor for day-30/60 shadow rechecks. Returns the number of ASINs
    enqueued (each writes up to 2 checkpoint rows). No-op (returns 0) when Supabase is off or
    migration 009 hasn't landed. Never raises — a shadow-enqueue failure can't break a cycle."""
    if not db.enabled() or not survivors:
        return 0
    all_rows: List[Dict[str, Any]] = []
    asin_count = 0
    for s in survivors:
        rows = build_enqueue_rows(s, run_id, now=now)
        if rows:
            all_rows.extend(rows)
            asin_count += 1
    # ONE bulk POST for the whole run (2 rows/survivor -> 400 sequential round-trips on a
    # 200-survivor night otherwise), and an HONEST count: enqueue_shadow_outcomes returns 0 on
    # failure, so a broken write can never report phantom silver labels (Review 2026-07-05).
    sent = db.enqueue_shadow_outcomes(all_rows)
    if sent == 0 and all_rows:
        log.warning("shadow enqueue wrote 0 of %d rows (is migration 009 applied? Supabase up?) — "
                    "silver labels lost for this run if not retried", len(all_rows))
        return 0
    return asin_count


# --- weekly recheck ---------------------------------------------------------
def compute_label(row: Dict[str, Any], now_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Given a due shadow row and a fresh Keepa snapshot for its ASIN, compute the 'now' fields +
    would_have_profited at the ORIGINAL landed cost. Pure — unit-tested without Keepa/Supabase.

    Cowork leakage/labeling audit fix (2026-07-13, Mehmet-approved), same fix as backtest.py's
    label_at() sibling: `est_profit > 0` alone means merely breaking even counted as "profitable"
    — now mirrors the real buy gate (scoring.oa_hard_reject/score_product_oa): profit >=
    CRITERIA_OA['min_profit_per_unit'] AND roi >= min_roi (the grocery exception applies here
    too). `roi_now` is also now returned."""
    price_now = now_snapshot.get("price")
    landed_cost = row.get("landed_cost")
    net_now = scoring.net_proceeds(price_now, row.get("weight_lb"), category=row.get("category"))
    would = None
    est_profit = None
    roi = None
    if net_now is not None and landed_cost is not None:
        est_profit = round(net_now - landed_cost, 2)
        roi = round(est_profit / landed_cost, 4) if landed_cost > 0 else None
        category = row.get("category")
        is_grocery = (category or "").strip().lower() == "grocery"
        min_roi = config.OA_GROCERY_MIN_ROI if is_grocery else config.CRITERIA_OA["min_roi"]
        min_profit = config.CRITERIA_OA["min_profit_per_unit"]
        would = est_profit >= min_profit and roi is not None and roi >= min_roi
    return {
        "price_now": price_now,
        "offers_now": now_snapshot.get("offers"),
        "sales_rank_now": now_snapshot.get("sales_rank"),
        "est_profit_now": est_profit,
        "roi_now": roi,
        "would_have_profited": would,
        "status": "done" if would is not None else "error",
        "computed_at": _now().isoformat(),
    }


def run_rechecks(api=None, now: Optional[_dt.datetime] = None,
                 token_cap: Optional[int] = None, enrich_fn=None) -> Dict[str, Any]:
    """Weekly job: re-pull due candidates' Keepa stats and write proxy labels. Batches ASINs
    (1 token each) up to the daily token cap. NEVER raises — returns an honest status dict.

    enrich_fn is injectable for tests; defaults to keepa_client.enrich."""
    if not db.enabled():
        return {"status": "disabled", "reason": "Supabase not configured", "checked": 0}
    if not config.have_keepa():
        return {"status": "disabled", "reason": "no KEEPA_KEY (rechecks need a live pull)", "checked": 0}

    now = now or _now()
    cap = token_cap if token_cap is not None else _recheck_token_cap()
    due = db.due_shadow_checkpoints(now_iso=now.isoformat())
    if not due:
        return {"status": "ok", "checked": 0, "labeled": 0, "profitable": 0, "tokens_spent": 0,
                "due": 0}

    # Unique ASINs, capped by the token budget (1 token/ASIN). Rows for a capped-out ASIN stay
    # pending and are retried next week — resumable, never a silent drop (reported below).
    unique_asins: List[str] = []
    for r in due:
        a = r.get("asin")
        if a and a not in unique_asins:
            unique_asins.append(a)
    budgeted = unique_asins[:max(0, cap)]
    deferred = len(unique_asins) - len(budgeted)

    if enrich_fn is None:
        import keepa_client
        enrich_fn = keepa_client.enrich
    api_obj = api
    if api_obj is None:
        try:
            import keepa_client
            api_obj = keepa_client.get_client()
        except Exception as e:
            return {"status": "error", "reason": str(e), "checked": 0}

    fresh: Dict[str, Dict[str, Any]] = {}
    for i in range(0, len(budgeted), _ENRICH_BATCH):
        batch = budgeted[i:i + _ENRICH_BATCH]
        try:
            for prod in (enrich_fn(batch, api=api_obj) or []):
                if isinstance(prod, dict) and prod.get("asin"):
                    fresh[prod["asin"]] = prod
        except Exception as e:
            log.warning("shadow recheck enrich failed (non-fatal): %s", e)

    checked = labeled = profitable = 0
    for r in due:
        asin = r.get("asin")
        if asin not in fresh:
            continue  # deferred (over budget) or Keepa returned nothing — stays pending
        fields = compute_label(r, fresh[asin])
        # roi_now has no shadow_outcomes column (migration 009 predates the 2026-07-13 labeling
        # fix) -- strip it before the PATCH so it can't reject the whole write for an unknown
        # column; compute_label()'s callers/tests still get it in the return value.
        db.complete_shadow_checkpoint(r.get("id"), {k: v for k, v in fields.items() if k != "roi_now"})
        checked += 1
        if fields["would_have_profited"] is not None:
            labeled += 1
            if fields["would_have_profited"]:
                profitable += 1

    return {"status": "ok", "due": len(due), "checked": checked, "labeled": labeled,
            "profitable": profitable, "tokens_spent": len(budgeted), "deferred_asins": deferred,
            "token_cap": cap}
