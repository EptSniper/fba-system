"""
pipeline.py — pre-launch discovery orchestration.

Flow (the paper's recommended initial production pipeline):
    ingest (Keepa) -> features -> HARD GATES (compliance/margin/crowding) ->
    rule score + calibrated classifier P(success) -> blended score ->
    quantile regressor (expected units) -> ranker order ->
    uncertainty routing (ambiguous -> human queue, not auto-alert) ->
    dedupe by ASIN -> alert top-N to Discord -> persist picks + weak labels.

With no champion model it runs on the transparent rule score alone. Gates always
win over the model. Ambiguous candidates are routed to review, never auto-sourced.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import config
import database as db
import features as feat
import gates
import labels
import models
import registry
import scoring

log = logging.getLogger("scout_pro.pipeline")


def _alertable(proba: Optional[float], blended: float) -> bool:
    if proba is not None:
        return proba >= config.ALERT_PROBABILITY and proba > config.UNCERTAINTY_HIGH
    return blended >= 70.0  # rule-only fallback


def _uncertain(proba: Optional[float]) -> bool:
    return proba is not None and config.UNCERTAINTY_LOW <= proba <= config.UNCERTAINTY_HIGH


def run_discovery(criteria: Optional[Dict[str, Any]] = None,
                  snapshots: Optional[List[Dict[str, Any]]] = None,
                  post: bool = True, dry_run: bool = False) -> Dict[str, Any]:
    criteria = criteria or config.CRITERIA
    db.init_db()
    summary: Dict[str, Any] = {"ingested": 0, "gated_out": 0, "scored": 0,
                               "routed_to_review": 0, "new_alerts": 0, "posted": 0}

    # 1) ingest (or accept injected snapshots for testing/backfill replay)
    if snapshots is None:
        if not config.have_keepa():
            raise RuntimeError("No KEEPA_KEY set. A paid Keepa key is required to ingest.")
        import ingest_keepa
        snapshots = ingest_keepa.ingest(criteria)
    summary["ingested"] = len(snapshots)
    if not snapshots:
        return summary
    snap_by_asin = {s["asin"]: s for s in snapshots if s.get("asin")}

    # 2) features
    feature_rows = feat.build_features(list(snap_by_asin.keys()))
    summary["scored"] = len(feature_rows)

    # 3) weak proxy labels (discovery training signal)
    labels.write_weak_labels(feature_rows, snap_by_asin)

    # 4) champion model + auxiliary models
    clf, clf_rec = registry.get_champion("classifier")
    ranker, _ = registry.get_champion("ranker")
    reg_units, _ = registry.get_champion("regressor_units")
    model_version = (clf_rec or {}).get("version", "rule-only") if clf_rec else "rule-only"

    candidates: List[Dict[str, Any]] = []
    for f in feature_rows:
        asin = f["asin"]
        snap = snap_by_asin.get(asin, {})

        passed, reasons = gates.hard_gates(f, snap)
        if not passed:
            summary["gated_out"] += 1
            continue

        rscore, reason = scoring.rule_score(f)
        proba_list = models.predict_proba(clf, [f]) if clf is not None else None
        proba = proba_list[0] if proba_list else None
        blended = models.blended_score(rscore, proba)
        units_list = models.predict_regressor(reg_units, [f]) if reg_units is not None else None
        rank_list = models.predict_rank_scores(ranker, [f]) if ranker is not None else None

        candidates.append({
            "asin": asin,
            "title": snap.get("title"),
            "price": f.get("price"),
            "est_sales": f.get("est_sales"),
            "review_count": f.get("review_count"),
            "rating": f.get("rating"),
            "offer_count": f.get("offer_count"),
            "margin_est": f.get("margin_est"),
            "rule_score": rscore,
            "proba": proba,
            "blended_score": blended,
            "expected_units": units_list[0] if units_list else None,
            "rank_score": rank_list[0] if rank_list else (proba if proba is not None else blended / 100.0),
            "reason": reason,
            "compliance_status": "clear",
            "model_version": f"champion {model_version}" if proba is not None else "rule-only",
        })

    # 5) uncertainty routing: ambiguous -> human queue (not auto-alerted)
    actionable = []
    for c in candidates:
        if _uncertain(c["proba"]):
            db.enqueue_review(c["asin"], c["proba"], c["blended_score"],
                              f"ambiguous P={c['proba']:.2f}; {c['reason']}")
            summary["routed_to_review"] += 1
        elif _alertable(c["proba"], c["blended_score"]):
            actionable.append(c)

    # 6) rank -> dedupe -> top N
    actionable.sort(key=lambda x: x["rank_score"], reverse=True)
    fresh = [c for c in actionable if not db.already_picked(c["asin"])][:config.TOP_N]
    summary["new_alerts"] = len(fresh)

    if dry_run:
        summary["alerts"] = [{"asin": c["asin"], "blended": c["blended_score"],
                              "proba": c["proba"], "reason": c["reason"]} for c in fresh]
        return summary

    # 7) alert + persist
    if post and fresh:
        if config.have_discord():
            import discord_notify
            summary["posted"] = discord_notify.post_picks(fresh)
        else:
            log.warning("No DISCORD_WEBHOOK_URL; recording picks without posting.")
    for c in fresh:
        db.record_pick(c["asin"], c["blended_score"], c["proba"], {
            "title": c["title"], "price": c["price"], "est_sales": c["est_sales"],
            "score": c["blended_score"], "proba": c["proba"], "reason": c["reason"],
        })
    log.info("discovery complete: %s", summary)
    return summary
