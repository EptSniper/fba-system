"""
scout/collect_hourly.py — the hourly burst collector (DATA_ENGINE_PLAN.md hourly-collector era,
Session 54).

Runs in .github/workflows/keepa-collect.yml, hourly at :07. The Keepa Pro trickle refills 1
token/minute and caps its bank at 60 — a PC-only overnight local run only captures roughly half
of that daily generation (the bank overflows while nothing is watching); a burst every hour
instead captures ~100% of it.

NEVER waits for a token refill (no wait=True dripping) — spends ONLY whatever is CURRENTLY
banked, in strict priority order, each tier getting whatever budget the tier above it didn't
spend:

  1. shadow-outcome rechecks due today (shadow_outcomes.run_rechecks) — the time-sensitive tier;
     a due checkpoint gets re-priced the SAME day it matures instead of waiting for the next
     weekly Monday branch.
  2. hint-led candidate scans, through the SAME gates/scoring/lead-upsert path pipeline.run_once()
     uses (deliberately reusing pipeline._evaluate — this project's own established precedent for
     intentionally sharing "private" internals as a single source of truth, e.g. scripts/
     pre-commit.py reusing scout/redact.py's regex objects directly).
  3. backtest ASIN history fetches (backtest.run_backtest) — whatever's left after 1 and 2.

Runtime target < 90s. Every Supabase write goes through the EXISTING idempotent paths (log_lead
upserts on asin+found_via, upsert_keepa_snapshot upserts on asin+day, shadow/backtest rows upsert
on their own natural keys) — an occasional double-fire (two hourly runs overlapping, a retried
run) or a missed hour is harmless by construction, never double-counted.

Cloud-only: raw Keepa responses can't reach the local Parquet lake from a GitHub Actions runner
(no persistent disk between runs) — datalake.py's flush() is redirected to the Supabase Storage
raw-inbox/ bucket when DATALAKE_CLOUD_INBOX=1 (this workflow sets it). scout/drain_inbox.py, run
locally, pulls those objects into the real lake.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
from typing import Any, Dict, List, Optional

import backtest
import config
import datalake
import db
import discovery_hints
import keepa_client
import model as model_mod
import pipeline
import predictions
import redact
import scoring
import shadow_outcomes

log = logging.getLogger("scout.collect_hourly")

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_HINT_SCAN_LIMIT = 60          # candidate-ASIN cap per burst tier 2, independent of token math
TOKENS_PER_CANDIDATE_ESTIMATE = 3     # sizing only — real spend is always measured after the fact


def _observed_tokens_left(api) -> int:
    """The ACTUAL current bank, floored at 0 for THIS function's purpose (deciding whether
    there's anything to spend) — the real, possibly-negative value lives in
    keepa_client.current_tokens_left(), the single source of truth every guarded Keepa call
    also reads from. Delegating here (rather than re-probing separately) avoids two different
    modules disagreeing about what "the bank" currently holds."""
    v = keepa_client.current_tokens_left(api)
    return v if isinstance(v, int) and v > 0 else 0


# --- non-blocking wrappers around keepa_client, for injection into shadow_outcomes/backtest ---
# (both already accept an injectable enrich_fn/find_fn/history_fn for exactly this kind of reuse
# — no need to touch either module; DATA_ENGINE_PLAN.md's "never wait" rule is enforced entirely
# from the caller side via keepa_client's own wait= parameter, added for this purpose.)
def _enrich_no_wait(asins, api=None):
    return keepa_client.enrich(asins, api=api, wait=False)


def _history_no_wait(asins, api=None):
    return keepa_client.query_history(asins, api=api, wait=False)


def _find_no_wait(api=None, brand_seeds=None, limit=None):
    return keepa_client.find_candidates(api=api, brand_seeds=brand_seeds, limit=limit, wait=False)


def _firehose_no_wait(api, pages=None):
    import deals_firehose
    return deals_firehose.harvest(api, pages=pages, wait=False)


def _attach_signal_features(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Session 55 — attach the CURRENT (as-of-today) calendar/Trends/eBay signal features onto
    each already-enriched product dict in place, so they flow into feature_snapshot the same way
    every other pre-decision field does (db.feature_snapshot reads PRE_DECISION_FEATURES off
    whatever keys are present on `p`). Best-effort and per-product isolated — one product's
    signal lookup failing never drops the batch; a per-run cache avoids re-fetching the same
    brand/category Trends series once per product when several share one."""
    today = _dt.date.today()
    try:
        from signals import calendar as signals_calendar
        cal_feats = signals_calendar.calendar_features(today)
    except Exception as e:
        log.warning("calendar_features failed (non-fatal): %s", e)
        cal_feats = {}

    signals_trends = None
    try:
        from signals import trends as signals_trends  # noqa: F401
    except Exception as e:
        log.warning("signals.trends unavailable (non-fatal): %s", e)

    signals_ebay = None
    try:
        from signals import ebay as signals_ebay  # noqa: F401
    except Exception as e:
        log.warning("signals.ebay unavailable (non-fatal): %s", e)

    trend_cache: Dict[str, Dict[str, Any]] = {}

    def _cached_trend(term: str) -> Dict[str, Any]:
        if term not in trend_cache:
            try:
                trend_cache[term] = signals_trends.trends_features(term, today)
            except Exception as e:
                log.warning("trends_features failed for %r (non-fatal): %s", term, e)
                trend_cache[term] = {}
        return trend_cache[term]

    for p in products:
        p.update(cal_feats)
        if signals_trends:
            brand_t = _cached_trend(p["brand"]) if p.get("brand") else {}
            cat_t = _cached_trend(p["category"]) if p.get("category") else {}
            p["brand_trend_ratio"] = brand_t.get("interest_now_vs_90d_avg")
            p["brand_trend_slope"] = brand_t.get("slope_4wk")
            p["brand_trend_seasonal_z"] = brand_t.get("seasonal_z")
            p["brand_trend_spike"] = brand_t.get("spike_flag")
            p["brand_trend_stale"] = brand_t.get("stale", True)
            p["category_trend_ratio"] = cat_t.get("interest_now_vs_90d_avg")
            p["category_trend_slope"] = cat_t.get("slope_4wk")
            p["category_trend_seasonal_z"] = cat_t.get("seasonal_z")
            p["category_trend_spike"] = cat_t.get("spike_flag")
            p["category_trend_stale"] = cat_t.get("stale", True)
        if signals_ebay and signals_ebay.enabled() and p.get("upc"):
            try:
                eb = signals_ebay.ebay_features(p["upc"], p.get("price"))
            except Exception as e:
                log.warning("ebay_features failed for %s (non-fatal): %s", p.get("asin"), e)
                eb = {}
            p["ebay_sold_count_30d"] = eb.get("ebay_sold_count_30d")
            p["median_sold_price_vs_amazon_ratio"] = eb.get("median_sold_price_vs_amazon_ratio")
            p["ebay_stale"] = eb.get("ebay_stale", True)
    return products


def hint_led_scan(api, token_budget: int, run_id: Optional[Any] = None) -> Dict[str, Any]:
    """Tier 2: a lightweight hint-led discovery pass through the SAME gates/scoring/lead-upsert
    path pipeline.run_once() uses. Skips the SP-API eligibility and LLM analyst passes (both
    no-ops today with no configured keys, and kept out regardless to stay well under the <90s
    runtime budget) — this is a fast slice of the pipeline, not a full cycle. Returns an honest
    status dict; NEVER raises."""
    if token_budget <= 0:
        return {"status": "skipped", "reason": "no budget remaining", "tokens_spent": 0,
                "candidates": 0, "leads_logged": 0, "survivors": 0}
    try:
        hints = discovery_hints.hinted_brand_seeds()
    except Exception as e:
        log.warning("hinted_brand_seeds failed (non-fatal): %s", e)
        hints = []
    if not hints:
        return {"status": "ok", "reason": "no fresh deal hints", "tokens_spent": 0,
                "candidates": 0, "leads_logged": 0, "survivors": 0}

    limit = max(1, min(DEFAULT_HINT_SCAN_LIMIT, token_budget // TOKENS_PER_CANDIDATE_ESTIMATE))
    before = keepa_client._tokens_consumed(api)
    try:
        asins = _find_no_wait(api=api, brand_seeds=hints, limit=limit)
    except Exception as e:
        reason = redact.redact(str(e))
        log.warning("hourly hint-led finder failed (non-fatal): %s", reason)
        return {"status": "error", "reason": reason, "tokens_spent": 0, "candidates": 0,
                "leads_logged": 0, "survivors": 0}
    if not asins:
        after = keepa_client._tokens_consumed(api)
        return {"status": "ok", "reason": "finder returned no candidates",
                "tokens_spent": keepa_client._delta(before, after) or 0, "candidates": 0,
                "leads_logged": 0, "survivors": 0}

    try:
        enriched = _enrich_no_wait(asins, api=api)
    except Exception as e:
        reason = redact.redact(str(e))
        log.warning("hourly hint-led enrich failed (non-fatal): %s", reason)
        after = keepa_client._tokens_consumed(api)
        return {"status": "error", "reason": reason,
                "tokens_spent": keepa_client._delta(before, after) or 0,
                "candidates": len(asins), "leads_logged": 0, "survivors": 0}

    try:
        enriched = _attach_signal_features(enriched)
    except Exception as e:
        log.warning("attach_signal_features failed (non-fatal, continuing without them): %s", e)

    clf = model_mod.load_model()
    # Intentional reuse of pipeline's own scoring internals — see module docstring. Keeps the
    # hourly burst's gates/scoring IDENTICAL to the nightly path; never a parallel reimplementation.
    scored = pipeline._evaluate(enriched, clf=clf)

    logged = 0
    survivors: List[Dict[str, Any]] = []
    for p in scored:
        if not p.get("asin"):
            continue
        hard_reject = scoring.oa_hard_reject(p) if config.MODE == "OA" else None
        if hard_reject:
            p["hard_reject"] = hard_reject
        score = p.get("blended_score") or 0
        verdict = "pass" if hard_reject else "review"
        reason = f"Hard reject: {hard_reject}. {p.get('reason') or ''}".strip() if hard_reject else (p.get("reason") or "")
        try:
            lead_id = db.log_lead(p, score, verdict, reason, found_via="hourly-collect",
                                  explanation=p.get("explanation"))
        except Exception as e:
            log.warning("log_lead failed for %s (non-fatal): %s", p.get("asin"), e)
            lead_id = None
        if lead_id is not None:
            logged += 1
        try:
            db.upsert_keepa_snapshot(p)
        except Exception as e:
            log.warning("upsert_keepa_snapshot failed for %s (non-fatal): %s", p.get("asin"), e)
        try:
            predictions.record_predictions_for(p.get("asin"), lead_id, p, p.get("explanation") or {})
        except Exception as e:
            log.warning("record_predictions_for failed for %s (non-fatal): %s", p.get("asin"), e)
        if not hard_reject:
            survivors.append(p)

    if survivors:
        try:
            shadow_outcomes.enqueue_survivors(survivors, run_id)
        except Exception as e:
            log.warning("shadow enqueue failed (non-fatal): %s", e)

    after = keepa_client._tokens_consumed(api)
    spent = keepa_client._delta(before, after) or 0
    return {"status": "ok", "candidates": len(asins), "leads_logged": logged,
            "survivors": len(survivors), "tokens_spent": spent}


def run_hourly_collect(api=None) -> Dict[str, Any]:
    """The whole burst, in strict priority order, spending only what's currently banked. NEVER
    raises — every tier is independently guarded; a failure in one tier still lets later tiers
    run with whatever budget remains."""
    if not config.have_keepa():
        return {"status": "disabled", "reason": "no KEEPA_KEY"}
    try:
        api = api or keepa_client.get_client()
    except Exception as e:
        return {"status": "error", "reason": redact.redact(str(e))}

    run_id = db.start_run(host="github-actions-hourly")
    datalake.set_run_context(run_id)
    datalake.reset_stats()
    t0 = _dt.datetime.now(_dt.timezone.utc)
    summary: Dict[str, Any] = {"run_id": run_id}
    error_summary: Optional[str] = None
    try:
        # A fresh client reports tokens_left as None until its first request — probe with the
        # cheapest possible call (seller lookup with a throwaway id would still cost tokens; the
        # keepa lib actually populates tokens_left on CONNECT for most versions, but read
        # defensively either way and treat "still unknown" as "nothing banked" rather than guess).
        available = _observed_tokens_left(api)
        summary["tokens_available"] = available
        if available <= 0:
            summary["status"] = "ok"
            summary["reason"] = "no tokens currently banked"
            return summary

        budget = available

        # Tier 1: shadow-outcome rechecks due today (labels.py's silver tier).
        shadow_result = shadow_outcomes.run_rechecks(api=api, token_cap=budget, enrich_fn=_enrich_no_wait)
        summary["shadow"] = shadow_result
        budget = max(0, budget - int(shadow_result.get("tokens_spent") or 0))

        # Tier 2: hint-led candidate scan through the normal gates/scoring/lead-upsert path.
        scan_result = hint_led_scan(api, budget, run_id=run_id)
        summary["scan"] = scan_result
        budget = max(0, budget - int(scan_result.get("tokens_spent") or 0))

        # Tier 3: backtest ASIN history fetches, whatever's left. Session 55: dealfeed/explore
        # (brand-agnostic) sampling now runs INSIDE run_backtest, prioritized ahead of onpolicy —
        # firehose_fn=_firehose_no_wait keeps the "never block on a refill" rule for the new
        # /deal calls too, matching find_fn/history_fn's own no-wait wrappers above.
        if budget > 0:
            bt_result = backtest.run_backtest(api=api, token_cap=budget,
                                              find_fn=_find_no_wait, history_fn=_history_no_wait,
                                              firehose_fn=_firehose_no_wait)
        else:
            bt_result = {"status": "skipped", "reason": "no budget remaining", "tokens_spent": 0}
        summary["backtest"] = bt_result

        summary["status"] = "ok"
        summary["tokens_spent_total"] = (
            int(shadow_result.get("tokens_spent") or 0)
            + int(scan_result.get("tokens_spent") or 0)
            + int(bt_result.get("tokens_spent") or 0)
        )
        return summary
    except Exception as e:
        error_summary = redact.redact(str(e))
        summary["status"] = "error"
        summary["error"] = error_summary
        return summary
    finally:
        datalake.flush(run_id)
        summary["lake_digest"] = datalake.digest_line()
        elapsed = (_dt.datetime.now(_dt.timezone.utc) - t0).total_seconds()
        summary["elapsed_seconds"] = round(elapsed, 1)
        # Session 55: the real balance AT THE END of this run (may be negative — Keepa allows
        # overdraw) + how many times the overdraw guard had to intervene this run, both for the
        # daily digest's honest "N runs skipped due to negative Keepa balance" line.
        summary["tokens_left_end"] = keepa_client.current_tokens_left(api, refresh=True)
        summary["guard"] = keepa_client.guard_telemetry()
        db.finish_run(
            run_id, "failed" if error_summary else "success",
            asins_scanned=(summary.get("scan") or {}).get("candidates"),
            tokens_consumed=summary.get("tokens_spent_total"),
            tokens_left_end=summary.get("tokens_left_end"),
            error_summary=error_summary,
        )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(HERE, ".env"))
    except Exception:
        pass
    result = run_hourly_collect()
    print(json.dumps(result, indent=2, default=str))
    return 1 if result.get("status") == "error" else 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
