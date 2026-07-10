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
TOKENS_PER_CANDIDATE_ESTIMATE = 4     # sizing only — real spend is always measured after the fact.
                                      # Corrected from 3 to match keepa_client.ENRICH_TOKENS_PER_ASIN's
                                      # 2026-07-07 fix (two live bursts each measured exactly 4/ASIN).
TIER1_RESERVE_FRACTION = 0.25         # Cap tier 1 (shadow rechecks) to this share of the
                                      # ORIGINAL bank (`available`, before anything spends) as
                                      # its OWN per-run ceiling. Review fix (2026-07-08, live
                                      # incident): tier 1 used to be handed the ENTIRE bank as
                                      # its token_cap (collect_hourly.py never bounded it — only
                                      # shadow_outcomes.py's own _recheck_token_cap() default
                                      # existed, and that's only consulted when the CALLER passes
                                      # token_cap=None, which collect_hourly.py never did). Once
                                      # due_shadow_checkpoints()'s own 400-error bug (a separate
                                      # fix, same date) stops silently zeroing tier 1's real work,
                                      # a large one-time backlog of overdue shadow rows (up to 500
                                      # per due_shadow_checkpoints()'s own limit) could otherwise
                                      # drain an entire run's bank on tier 1 alone — exactly the
                                      # "one tier eats everything" failure TIER3_RESERVE_FRACTION
                                      # was built to fix for tier 2. shadow_outcomes.run_rechecks
                                      # is itself resumable (overdue rows simply stay pending), so
                                      # a big backlog drains gradually across many hourly runs
                                      # instead of consuming one run's whole budget.
TIER3_RESERVE_FRACTION = 0.35         # Reserve this share of the ORIGINAL bank (`available`, NOT
                                      # whatever tier 1 leaves behind — review fix 2026-07-08, so
                                      # tier 3's guarantee can't shrink just because tier 1 had a
                                      # big backlog that run) for tier 3 (backtest collection)
                                      # before tier 2 (discovery) spends anything. Review fix
                                      # (2026-07-07, live incident): tier 2 alone was consistently
                                      # spending the ENTIRE bank (Product Finder's Pro-plan
                                      # rejection forces a 10-token/term search fallback, plus the
                                      # enrich guard's old undercounted per-ASIN estimate let it
                                      # overdraw ~14 tokens past the cap every single run) --
                                      # leaving tier 3 with ZERO budget on every burst since the
                                      # hang was fixed, so backtest_rows never grew even once.
                                      # This is a deliberate discovery-vs-training-data tradeoff
                                      # (Mehmet's call, 2026-07-07): tier 2 scans somewhat fewer
                                      # candidates when the bank is full, so tier 3 actually gets
                                      # a chance to grow the corpus that training depends on.

# Review fix (2026-07-06): a defense-in-depth wall-clock budget, independent of the Trends N+1
# fix above. keepa-collect.yml's own job timeout is 10 minutes; a run that's still going at this
# mark skips its remaining tiers so the function returns normally and finish_run() still records
# an honest status, instead of getting force-killed mid-flight with the Supabase `runs` row stuck
# at status='running' forever (exactly what happened to every run since the Keepa bank recovered
# from its overdraw, before the N+1 was found and fixed). Not a substitute for fixing a slow
# path — a safety net in case a different one appears later.
SAFE_DEADLINE_SECONDS = 420  # 7 min, leaving a 3 min buffer before the 10 min job timeout


def _deadline_exceeded(t0: _dt.datetime) -> bool:
    return (_dt.datetime.now(_dt.timezone.utc) - t0).total_seconds() > SAFE_DEADLINE_SECONDS


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


# fba-feature-engineer (2026-07-10): moved to signals/attach.py so pipeline.run_once shares
# the SAME producer (it previously scored with 18/28 features NaN on that path). The local name
# is kept so call sites and tests are unchanged.
from signals.attach import attach_signal_features as _attach_signal_features


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

    # Review fix (2026-07-08, live incident): `limit` used to be sized ONLY off enrich's own
    # per-ASIN cost (TOKENS_PER_CANDIDATE_ESTIMATE), with nothing reserved for find_candidates()'s
    # OWN cost. On this Pro-plan key, Product Finder is REQUEST_REJECTED on every call
    # (keepa_client.py's own confirmed comment), so find_candidates() ALWAYS falls back to a flat
    # SEARCH_TOKENS_PER_TERM(10)/term search (up to 3 terms, 10-30 tokens) BEFORE enrich() ever
    # runs. That real cost was never subtracted before sizing `limit`, so tier 2's TOTAL real
    # spend structurally exceeded its own token_budget every run (live-confirmed: tier2_budget=39
    # but real combined spend=45-46), eating into the tier-3 reserve that budget exists to
    # protect. Reserve the worst-case finder cost up front before sizing enrich's candidate count.
    finder_reserve = min(3, len(hints)) * keepa_client.SEARCH_TOKENS_PER_TERM
    limit = max(1, min(DEFAULT_HINT_SCAN_LIMIT,
                      max(0, token_budget - finder_reserve) // TOKENS_PER_CANDIDATE_ESTIMATE))
    # Force a live refresh (not the passive _tokens_consumed) for the "before" probe too — the
    # search fallback below uses raw requests.get() directly against api.keepa.com, bypassing the
    # keepa.Keepa client object entirely, so it never updates api.tokens_left on its own; only an
    # active update_status() probe (what current_tokens_left(refresh=True) does) sees its spend.
    before = keepa_client.current_tokens_left(api, refresh=True)
    try:
        asins = _find_no_wait(api=api, brand_seeds=hints, limit=limit)
    except Exception as e:
        reason = redact.redact(str(e))
        log.warning("hourly hint-led finder failed (non-fatal): %s", reason)
        after = keepa_client.current_tokens_left(api, refresh=True)
        return {"status": "error", "reason": reason,
                "tokens_spent": keepa_client._delta(before, after) or 0, "candidates": 0,
                "leads_logged": 0, "survivors": 0}
    if not asins:
        after = keepa_client.current_tokens_left(api, refresh=True)
        return {"status": "ok", "reason": "finder returned no candidates",
                "tokens_spent": keepa_client._delta(before, after) or 0, "candidates": 0,
                "leads_logged": 0, "survivors": 0}

    try:
        enriched = _enrich_no_wait(asins, api=api)
    except Exception as e:
        reason = redact.redact(str(e))
        log.warning("hourly hint-led enrich failed (non-fatal): %s", reason)
        after = keepa_client.current_tokens_left(api, refresh=True)
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

    # ML audit fix (2026-07-09, doctrine §5 — BLOCKER): the hourly path (the ONLY production
    # scanning path since run_daily went housekeeping-only) never called _rank_winners, so the
    # trained ranker had no reader here: no shadow ordering was ever computed, and even a human
    # promotion (scoring.rankingChampion=challenger) would have changed nothing observable on
    # this path — the doctrine's dead-artifact cautionary tale reopened one hop downstream.
    # Rank survivors exactly like pipeline.run_once does and record WHICH model ordered the
    # queue this run — "rule" until a human promotes, per the brain key.
    ranking_model = "rule"
    if survivors:
        try:
            survivors, ranking_model = pipeline._rank_winners(survivors)
        except Exception as e:
            log.warning("rank_winners failed (non-fatal, unranked order this run): %s", e)
        try:
            shadow_outcomes.enqueue_survivors(survivors, run_id)
        except Exception as e:
            log.warning("shadow enqueue failed (non-fatal): %s", e)

    after = keepa_client._tokens_consumed(api)
    spent = keepa_client._delta(before, after) or 0
    return {"status": "ok", "candidates": len(asins), "leads_logged": logged,
            "survivors": len(survivors), "tokens_spent": spent,
            "ranking_model": ranking_model}


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

        # Tier 1: shadow-outcome rechecks due today (labels.py's silver tier). Capped to
        # TIER1_RESERVE_FRACTION of the ORIGINAL bank (not handed the whole thing) — see that
        # constant's own comment: due_shadow_checkpoints() used to silently fail on every run (a
        # separate fix, same date), so this cap was never actually exercised in practice; now
        # that tier 1 can do real work again, an uncapped backlog could otherwise reproduce the
        # exact "one tier eats everything" failure tier 2 used to cause.
        tier1_cap = int(available * TIER1_RESERVE_FRACTION)
        shadow_result = shadow_outcomes.run_rechecks(api=api, token_cap=tier1_cap, enrich_fn=_enrich_no_wait)
        summary["shadow"] = shadow_result
        summary["tier1_cap"] = tier1_cap
        budget = max(0, budget - int(shadow_result.get("tokens_spent") or 0))

        # Tier 2: hint-led candidate scan through the normal gates/scoring/lead-upsert path.
        # Capped to leave TIER3_RESERVE_FRACTION of the ORIGINAL bank for tier 3 — see that
        # constant's own comment for why (tier 2 alone was starving tier 3 out completely, and
        # the reserve is computed from `available`, not `budget`, so tier 1's actual spend this
        # run can't shrink tier 3's guarantee).
        tier3_reserve = int(available * TIER3_RESERVE_FRACTION)
        tier2_budget = max(0, budget - tier3_reserve)
        summary["tier3_reserve"] = tier3_reserve
        if _deadline_exceeded(t0):
            scan_result = {"status": "skipped", "reason": "wall-clock safety deadline reached",
                          "tokens_spent": 0}
        else:
            scan_result = hint_led_scan(api, tier2_budget, run_id=run_id)
        summary["scan"] = scan_result
        budget = max(0, budget - int(scan_result.get("tokens_spent") or 0))

        # Tier 3: backtest ASIN history fetches, whatever's left. Session 55: dealfeed/explore
        # (brand-agnostic) sampling now runs INSIDE run_backtest, prioritized ahead of onpolicy —
        # firehose_fn=_firehose_no_wait keeps the "never block on a refill" rule for the new
        # /deal calls too, matching find_fn/history_fn's own no-wait wrappers above.
        if _deadline_exceeded(t0):
            bt_result = {"status": "skipped", "reason": "wall-clock safety deadline reached",
                        "tokens_spent": 0}
        elif budget > 0:
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
        # Migration 013 (2026-07-09): the per-tier token split and the backtest tier's
        # rows/ASINs-sampled counts used to exist ONLY in this run's own printed JSON summary,
        # discarded the moment the GitHub Actions runner tore down — nothing durable recorded
        # which tier got how much of the token budget or how many rows a given run actually
        # wrote, so the control-center's training/collection charts had no history to read.
        # These are the same `summary` fields already computed above; just persisted now.
        bt = summary.get("backtest") or {}
        db.finish_run(
            run_id, "failed" if error_summary else "success",
            asins_scanned=(summary.get("scan") or {}).get("candidates"),
            tokens_consumed=summary.get("tokens_spent_total"),
            tokens_left_end=summary.get("tokens_left_end"),
            error_summary=error_summary,
            tier1_tokens=(summary.get("shadow") or {}).get("tokens_spent"),
            tier2_tokens=(summary.get("scan") or {}).get("tokens_spent"),
            tier3_tokens=bt.get("tokens_spent"),
            backtest_rows_written=bt.get("rows_written"),
            backtest_asins_sampled=bt.get("asins_sampled"),
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
