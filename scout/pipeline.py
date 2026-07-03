"""
pipeline.py — orchestrate one scout cycle.

Flow:
    1. init DB
    2. (optional) retrain the model if enough new labels exist
    3. find candidates via Keepa Product Finder
    4. enrich them (price, sales-rank drops, reviews, rating, weight, offers)
    5. score each: transparent rule score + reason, then blend with model proba
    6. upsert every candidate seen
    7. filter to score >= threshold, sort desc, take top N
    8. dedupe against everything already sent to Discord (by ASIN)
    9. post the new picks to Discord
   10. record picks + log a summary

With zero labels and no model, step 5 is purely the rule score — fully functional.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import analyst
import config
import db
import discord_router
import keepa_client
import model as model_mod
import redact
import reflect
import scoring
import spapi
import storage

log = logging.getLogger("scout.pipeline")


def _check_eligibility(scored: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """SP-API "am I allowed?" check for hard-gate survivors (System Blueprint Prompt G3).

    A NO-OP pass-through when SP-API isn't configured (spapi.configured() is False until real
    LWA credentials exist) — every candidate is returned unchanged, with no `eligibility` key,
    which the explain-why layer must read as "not checked", never as "allowed". NOT_ELIGIBLE
    becomes a hard reject (account-gated); APPROVAL_REQUIRED keeps the candidate but tags it.
    Also replaces the estimated FBA fee with SP-API's real getMyFeesEstimate when available,
    recording which source was used (honest data flow) — the rule-based estimate stays as the
    fallback either way, never silently swapped without a record of which one won.
    """
    if not spapi.configured():
        return scored
    for p in scored:
        asin = p.get("asin")
        if not asin:
            continue
        try:
            elig = spapi.get_listings_restrictions(asin)
        except Exception as e:
            log.warning("SP-API restriction check failed for %s: %s", asin, e)
            continue
        p["eligibility"] = elig
        if elig.get("status") == "NOT_ELIGIBLE":
            reasons = "; ".join(elig.get("reasons", [])[:2]) or "not eligible to list"
            p["hard_reject"] = f"account-gated: {reasons}"
        elif elig.get("status") == "APPROVAL_REQUIRED":
            p["needs_ungating"] = True

        price = p.get("price")
        if price:
            try:
                fees = spapi.get_fees_estimate(asin, price)
            except Exception as e:
                fees = {"available": False, "reason": redact.redact(str(e))}
            p["fee_source"] = "spapi" if fees.get("available") else "estimate"
            if fees.get("available") and fees.get("fba_fee") is not None:
                p["spapi_fba_fee"] = fees["fba_fee"]
    return scored


def _run_analyst_pass(scored: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """LLM second-opinion pass over hard-gate survivors (Scout Agent Build Plan Prompt S1).

    A NO-OP pass-through when ANTHROPIC_API_KEY isn't set (analyst.configured() is False) —
    every candidate is returned unchanged, with no `analyst_note` key. The analyst NEVER
    changes score/verdict/gates/hard_reject — it only attaches an advisory note (merged into
    the existing `explanation` dict so it's persisted by log_lead() with zero schema change)
    for human review + `disagrees_with_rules` telemetry. A per-candidate analyst failure is
    caught and recorded as an honest {"status": "error", ...} note — it never drops the
    candidate or crashes the run.
    """
    if not analyst.configured():
        return scored
    for p in scored:
        # Scout Agent Build Plan Prompt S3 — feed the brand's memory note (if any) into the
        # analyst's input; memory_used is recorded so memory_report.py can A/B-measure whether
        # it actually improves disagreement accuracy, rather than assuming it does.
        memory_note = reflect.read_memory_note(p.get("brand"))
        try:
            note = analyst.analyze(p, category=p.get("category"), memory_note=memory_note)
        except Exception as e:  # analyst.analyze() already catches API errors; this is a
            note = {"status": "error", "reason": redact.redact(str(e))}  # last-resort guard
        if isinstance(note, dict):
            note["memory_used"] = bool(memory_note)
        p["analyst_note"] = note
        if isinstance(p.get("explanation"), dict):
            p["explanation"]["analyst_note"] = note
    return scored


def _maybe_post_picks(fresh: List[Dict[str, Any]]) -> Optional[int]:
    """Post fresh picks to Discord's "scout_picks" stream if a webhook resolves — checked via
    discord_router directly (Cowork Session 23's per-channel .env no longer sets the legacy
    config.have_discord()/DISCORD_WEBHOOK_URL, so gating on that would silently skip real
    posts). Returns the posted count, or None if there was nothing to post or no webhook
    configured (still recording picks either way)."""
    if not fresh:
        return None
    if not discord_router._resolve_url("scout_picks"):
        log.warning("No scout_picks webhook (or fallback) configured; skipping post, still "
                   "recording picks.")
        return None
    import discord_notify
    return discord_notify.post_picks(fresh)


def _log_supabase_leads(evaluated: List[Dict[str, Any]],
                        threshold: float,
                        dry_run: bool = False) -> int:
    """Persist every evaluated lead to the optional Supabase business memory (idempotent
    upsert on asin+found_via — see db.py). Also upserts a same-day keepa_snapshots row per
    ASIN, so historical trend detectors (Phase 2) have real daily data to work from.

    High-scoring leads remain ``review`` until a human decides. Hard rejects and
    below-threshold candidates become ``pass`` records, preserving negative examples
    for later calibration and error analysis. Dry runs avoid external writes.
    """
    if dry_run or not db.enabled():
        return 0

    logged = 0
    for product in evaluated:
        hard_reject = product.get("hard_reject")
        score = product.get("blended_score") or 0
        verdict = "pass" if hard_reject or score < threshold else "review"
        reason = product.get("reason") or ""
        if hard_reject:
            reason = f"Hard reject: {hard_reject}. {reason}".strip()
        lead_id = db.log_lead(product, score, verdict, reason,
                              explanation=product.get("explanation"))
        if lead_id is not None:
            logged += 1
        db.upsert_keepa_snapshot(product)
    return logged


def maybe_retrain() -> Dict[str, Any]:
    """Retrain the model from accumulated legacy SQLite labels if there are enough of them.

    DISABLED BY DEFAULT (Code Review 2026-07-02, Finding B4, config.LEGACY_RETRAIN_ENABLED) —
    this is a separate, un-unified path from the leakage-safe Supabase loop
    (labels.py/calibration_report.py). rule_score has also been removed from model.py's
    FEATURES as defense in depth, but the two loops still aren't unified, so this stays off
    until a human opts back in with SCOUT_LEGACY_RETRAIN=1."""
    if not config.LEGACY_RETRAIN_ENABLED:
        return {"trained": False,
                "reason": "legacy retrain disabled by default (Code Review 2026-07-02, Finding "
                         "B4) — set SCOUT_LEGACY_RETRAIN=1 to opt back in"}
    rows = storage.training_rows()
    if len(rows) < config.MIN_LABELS_TO_TRAIN:
        return {"trained": False,
                "reason": f"{len(rows)} labels (< {config.MIN_LABELS_TO_TRAIN}); running on rule score"}
    report = model_mod.train(rows)
    log.info("retrain: %s", report)
    return report


def _evaluate(enriched: List[Dict[str, Any]],
              clf=None) -> List[Dict[str, Any]]:
    """Attach rule score, margin, model proba, blended score, and reason."""
    results = []
    oa = (config.MODE == "OA")
    for p in enriched:
        p = dict(p)
        if oa:
            category = p.get("category")
            profit, roi = scoring.estimate_oa_profit_roi(p.get("price"), p.get("weight_lb"), category=category)
            p["oa_profit"], p["oa_roi"] = profit, roi
            rule_score, _pr, reason = scoring.score_product_oa(p, category=category)
            # Explain-why structure (gates + named adjustments) for Discord/dry-run output AND
            # persisted to the Supabase `leads` row (db.log_lead() sends it as `explanation`).
            # That column only exists once migration 001 is applied; until then, db.py's
            # LEADS_MIGRATION_ONLY_FIELDS handling strips it (and features_snapshot) from the
            # fallback insert so the rest of the row still gets written (Code Review 2026-07-02,
            # Finding B2 — this comment previously described the pre-fix state, where sending
            # unknown columns risked losing the whole write).
            p["explanation"] = scoring.explain_oa(p, category=category)
            # Review-queue ranking (Scout Agent Build Plan sec 3.2) — a SORT key only, computed
            # alongside the score but never fed back into it or into any gate.
            p["triage_score"] = scoring.triage_score(p, category=category)
            margin = scoring.estimate_margin(p.get("price"), p.get("weight_lb"))
        else:
            rule_score, margin, reason = scoring.score_product(p)
        feats = model_mod.features_from(p, rule_score, margin)
        proba = model_mod.predict_proba(feats, model=clf)
        blended = model_mod.blended_score(rule_score, proba)
        p.update({
            "margin_est": margin,
            "rule_score": rule_score,
            "model_proba": proba,
            "blended_score": blended,
            "reason": reason,
            "raw": {k: p.get(k) for k in
                    ("sales_rank", "drops30", "drops90", "brand", "oos_90")},
        })
        p["risks"] = scoring.risk_flags_oa(p) if oa else scoring.risk_flags(p)
        results.append(p)
    return results


def run_once(criteria: Optional[Dict[str, Any]] = None,
             threshold: Optional[float] = None,
             top_n: Optional[int] = None,
             retrain: bool = True,
             post: bool = True,
             dry_run: bool = False) -> Dict[str, Any]:
    """Run a single scout cycle. Returns a summary dict.

    Wrapped in a Supabase `runs` row (System Blueprint Prompt G1) — started at entry, finished
    in a `finally` block so a run that raises is still recorded as "failed" with the exception
    message, never silently lost. No-ops if Supabase/the runs table aren't available.
    """
    criteria = criteria or config.active_criteria()
    threshold = config.SCORE_THRESHOLD if threshold is None else threshold
    top_n = config.TOP_N if top_n is None else top_n

    storage.init_db()
    summary: Dict[str, Any] = {"found": 0, "scored": 0, "above_threshold": 0,
                               "new_picks": 0, "posted": 0, "retrain": None,
                               "supabase_enabled": db.enabled(), "supabase_logged": 0}
    run_id = db.start_run() if not dry_run else None
    # Code Review 2026-07-02, Finding S8: the caller (run_daily.py) used to re-query
    # db.recent_runs(limit=1) to find "the" run id for the digest — racy if a concurrent
    # manual/scheduled run started a different row in the same window. Thread THIS cycle's
    # real run_id through directly instead, on every path (dry-run return, normal return,
    # and — via the exception's own run_id attribute below — the failure path too).
    summary["run_id"] = run_id
    error_summary: Optional[str] = None

    try:
        if retrain:
            summary["retrain"] = maybe_retrain()

        if not config.have_keepa():
            raise RuntimeError("No KEEPA_KEY set. A paid Keepa key is required (see .env).")

        api = keepa_client.get_client()

        # 1) find + 2) enrich
        asins = keepa_client.find_candidates(criteria, api=api)
        summary["found"] = len(asins)
        log.info("Product Finder returned %d ASINs", len(asins))
        enriched = keepa_client.enrich(asins, api=api)
        # Token telemetry (System Blueprint Prompt G1/G2) — a drained key silently looks like
        # "no results" otherwise; surfaced in the summary and the runs row so it's never silent.
        summary["tokens"] = keepa_client.token_telemetry(api)

        # 3) score (load model once)
        clf = model_mod.load_model()
        scored = _evaluate(enriched, clf=clf)
        summary["scored"] = len(scored)

        # 4) persist everything seen
        for p in scored:
            if p.get("asin"):
                storage.upsert_candidate(p)

        # 5) HARD GATE (OA): never post Amazon-Buy-Box / no-price items, regardless of score
        evaluated = scored
        if config.MODE == "OA":
            gated = []
            for p in evaluated:
                reason = scoring.oa_hard_reject(p)
                if reason:
                    p["hard_reject"] = reason
                else:
                    gated.append(p)
            scored = gated
            summary["hard_rejected"] = summary["scored"] - len(scored)

        # 5b) SP-API eligibility check for survivors (System Blueprint Prompt G3) — a no-op
        # today (spapi.configured() is False, no real credentials yet). `evaluated` and `scored`
        # share the same dict objects for survivors, so mutating hard_reject here is visible to
        # both; newly-rejected candidates must still be dropped from `scored` before scoring
        # winners, or SP-API would reject a candidate that then still gets posted as a pick.
        scored = _check_eligibility(scored)
        newly_rejected = [p for p in scored if p.get("hard_reject")]
        if newly_rejected:
            scored = [p for p in scored if not p.get("hard_reject")]
            summary["hard_rejected"] = summary.get("hard_rejected", 0) + len(newly_rejected)

        # 5c) LLM analyst second opinion over hard-gate survivors (Scout Agent Build Plan
        # Prompt S1) — a no-op today (analyst.configured() is False, no ANTHROPIC_API_KEY yet).
        # Never rejects a candidate; only attaches an advisory note + disagreement telemetry.
        scored = _run_analyst_pass(scored)
        summary["analyst_disagreements"] = sum(
            1 for p in scored if (p.get("analyst_note") or {}).get("disagrees_with_rules")
        )

        # Preserve both positive-looking and negative examples in business memory.
        summary["supabase_logged"] = _log_supabase_leads(
            evaluated, threshold=threshold, dry_run=dry_run
        )

        # 6) filter -> sort -> top N. The score THRESHOLD (the pass/fail bar) is unchanged;
        # only the ORDER within the winners changes — by triage_score (Scout Agent Build Plan
        # sec 3.2: expected payback speed at a stressed price) when available, falling back to
        # blended_score for candidates triage_score couldn't rank (missing price/sales data).
        winners = [p for p in scored if (p.get("blended_score") or 0) >= threshold]
        summary["above_threshold"] = len(winners)
        winners.sort(key=lambda x: (x.get("triage_score") if x.get("triage_score") is not None
                                    else x.get("blended_score", 0)), reverse=True)

        # 6) dedupe against prior picks (by ASIN)
        fresh = [p for p in winners if p.get("asin") and not storage.already_picked(p["asin"])]
        fresh = fresh[:top_n]
        summary["new_picks"] = len(fresh)

        if dry_run:
            summary["picks"] = [{"asin": p["asin"], "score": p["blended_score"],
                                 "reason": p["reason"],
                                 "analyst_narrative": (p.get("analyst_note") or {}).get("narrative")}
                                for p in fresh]
            log.info("dry-run: %s", summary)
            return summary

        # 7) post + 8) record
        if post and fresh:
            posted = _maybe_post_picks(fresh)
            if posted is not None:
                summary["posted"] = posted

        for p in fresh:
            storage.record_pick(p["asin"], p.get("blended_score", 0), {
                "title": p.get("title"), "price": p.get("price"),
                "est_sales": p.get("est_sales"), "score": p.get("blended_score"),
                "reason": p.get("reason"),
            })

        log.info("cycle complete: %s", summary)
        return summary
    except Exception as e:
        # Code Review 2026-07-02, Finding B5: a Keepa/SP-API/Best Buy exception can legitimately
        # contain a real API key in its request URL — redact() strips it before this string
        # reaches Supabase's runs.error_summary, the digest, or a system_health Discord post
        # (run_daily.py just reads summary["error"], so redacting once here covers all of them).
        redacted = redact.redact(str(e))
        summary["error"] = redacted
        error_summary = redacted[:500]
        # Code Review Finding S8 — `raise` re-raises the ORIGINAL exception object, so
        # run_daily.py's except handler (which replaces `summary` from scratch) can't see this
        # function's local `summary["run_id"]` any other way; attach it to the exception itself.
        e.run_id = run_id
        raise
    finally:
        # Runs in EVERY case — normal return, dry-run early return, or an exception — so a
        # failed cycle is always recorded, never silently lost. finish_run() itself no-ops if
        # run_id is None (dry runs never start one) or Supabase is unavailable.
        tokens = summary.get("tokens") or {}
        db.finish_run(run_id, "failed" if error_summary else "success",
                     asins_scanned=summary.get("found", 0),
                     candidates_gated=summary.get("hard_rejected", 0),
                     leads_upserted=summary.get("supabase_logged", 0),
                     tokens_consumed=tokens.get("tokens_consumed"),
                     tokens_left_end=tokens.get("tokens_left"),
                     error_summary=error_summary)
