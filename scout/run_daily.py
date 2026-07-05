"""
run_daily.py — the single daily entry point (System Blueprint Prompt G2).

Orchestrates: brain-drift check -> pipeline.run_once() (which already does drip-scan discovery,
hard gates, enrichment, scoring with explain-why, and idempotent Supabase upserts, plus its own
`runs`-row wrapping from G1) -> ONE batched Discord digest embed to the "daily_digest" stream
(distinct from discord_notify.post_picks(), which posts to "scout_picks" — the digest is a
single summary message, respecting webhook rate limits) -> finally ping HEALTHCHECK_URL
(healthchecks.io, free) on success or its /fail endpoint on failure, so a machine that never
woke up is still detected (a webhook alone can't report a process that's asleep).

Multi-channel Discord routing (Cowork Session 23's 7 provisioned webhooks) goes through
discord_router.py: this file posts the digest ("daily_digest") and system-health alerts
("system_health" — run failures, brain drift, low Keepa tokens); pipeline.py posts picks
("scout_picks") via discord_notify.py; propose_updates.py posts a short notice
("brain_proposals"); scout/deals/collect.py posts source stats ("retail_deals"). The digest
keeps a one-line cross-channel summary so it remains the single place that proves the whole
run happened.

Usage:
    python run_daily.py               # real run — needs KEEPA_KEY (see .env)
    python run_daily.py --dry-run     # no external writes/posts; prints the summary
    python run_daily.py --dry-run-live  # THIS_WEEK.md Prompt W2 — Keepa discovery honestly
                                         # skipped (no key yet), everything else runs for real
                                         # (deals collection, a real runs row, digest, heartbeat)

Schedule it: see the "Scheduling" section in scout/README.md for the Windows Task Scheduler
command (with "run when missed" enabled) and the equivalent cron line for a future small VPS.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

try:
    # Code Review 2026-07-02, Finding B1: load .env HERE, before any submodule import, so
    # nothing in this file (or a module it imports first, like db.py) can silently read an
    # empty environment depending on import order. db.py now self-loads too (belt and
    # suspenders) — this is the entry point's own defense-in-depth copy.
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # pragma: no cover - dotenv simply not installed
    pass

import datalake
import db
import discord_router
import harvest
import memory_report
import ops_report
import pipeline
import propose_updates
import redact
import reflect
import search_log
from deals import collect as deals_collect

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

log = logging.getLogger("scout.run_daily")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_BRAIN = os.path.join(HERE, "..", "learning-hub", "data", "ai-brain.json")
BUNDLED_BRAIN = os.path.join(HERE, "..", "control-center", "hub-data", "ai-brain.json")

# Every OTHER hub-data file mirrored into control-center/hub-data/ for Vercel (which has no
# sibling learning-hub/ folder — see control-center/lib/data.ts's live() fallback). ai-brain.json
# itself is checked separately via LOCAL_BRAIN/BUNDLED_BRAIN above so existing callers/tests that
# patch those two specific names keep working unchanged. Code Review 2026-07-02, Finding S13:
# the drift check originally covered ONLY ai-brain.json — a stale leads/picks/finances/deals/
# knowledge-index/rag-manifest snapshot on Vercel is just as real a "deployed site shows old
# data" problem (lower-stakes than stale SCORING thresholds, but still worth a heads-up).
_HUB_DATA_DIR = os.path.join(HERE, "..", "learning-hub", "data")
_HUB_ROOT_DIR = os.path.join(HERE, "..", "learning-hub")
_BUNDLED_DIR = os.path.join(HERE, "..", "control-center", "hub-data")
_RAG_SOURCES_DIR = os.path.join(HERE, "..", "knowledge-rag", "sources")

OTHER_MIRRORED_HUB_DATA_FILES = [
    (os.path.join(_HUB_DATA_DIR, "finances.json"), os.path.join(_BUNDLED_DIR, "finances.json")),
    (os.path.join(_HUB_DATA_DIR, "inventory.json"), os.path.join(_BUNDLED_DIR, "inventory.json")),
    (os.path.join(_HUB_DATA_DIR, "leads.json"), os.path.join(_BUNDLED_DIR, "leads.json")),
    (os.path.join(_HUB_DATA_DIR, "picks.json"), os.path.join(_BUNDLED_DIR, "picks.json")),
    (os.path.join(_HUB_DATA_DIR, "deals.json"), os.path.join(_BUNDLED_DIR, "deals.json")),
    (os.path.join(_HUB_ROOT_DIR, "knowledge-index.json"), os.path.join(_BUNDLED_DIR, "knowledge-index.json")),
    # rag-manifest.json's LIVE source lives in a different sibling tree entirely (knowledge-rag/,
    # not learning-hub/) and under a different filename (manifest.json) — see getRagManifest().
    (os.path.join(_RAG_SOURCES_DIR, "manifest.json"), os.path.join(_BUNDLED_DIR, "rag-manifest.json")),
]

# Below this many Keepa tokens left, post a dedicated system_health warning (a drained key
# silently looks like "no results" otherwise — System Blueprint Prompt G2's own concern,
# now routed to its own channel instead of only a digest field).
LOW_TOKEN_WARNING_THRESHOLD = int(os.getenv("LOW_TOKEN_WARNING_THRESHOLD", "1000"))


def _hub_data_files_differ(live_path: str, bundled_path: str) -> bool:
    """True only if BOTH files exist and their contents differ. Missing files degrade to False
    (nothing to compare) rather than a drift finding — matches the original single-file
    behavior."""
    try:
        with open(live_path, encoding="utf-8") as f:
            live = f.read()
        with open(bundled_path, encoding="utf-8") as f:
            bundled = f.read()
    except FileNotFoundError:
        return False
    return live != bundled


def check_brain_drift() -> Optional[str]:
    """Warn if ANY bundled control-center/hub-data snapshot has drifted from its live source —
    this exact kind of drift has bitten the project before (see AI_COLLABORATION_JOURNAL.md's
    known-drift history). Originally checked only ai-brain.json; Code Review 2026-07-02, Finding
    S13 extended it to every mirrored hub-data file (finances/inventory/leads/picks/deals/
    knowledge-index/rag-manifest), since a stale one of those is just as real a "deployed site
    shows old data" problem. Returns a combined warning naming every drifted file, or None if
    everything matches (or every pair is simply absent)."""
    drifted = []
    if _hub_data_files_differ(LOCAL_BRAIN, BUNDLED_BRAIN):
        drifted.append(os.path.basename(BUNDLED_BRAIN))
    for live_path, bundled_path in OTHER_MIRRORED_HUB_DATA_FILES:
        if _hub_data_files_differ(live_path, bundled_path):
            drifted.append(os.path.basename(bundled_path))
    if not drifted:
        return None
    if drifted == ["ai-brain.json"]:
        # Keep the original single-file wording verbatim — anything that string-matched this
        # exact message (Discord history, prior journal entries) keeps working.
        return ("hub-data/ai-brain.json has drifted from learning-hub/data/ai-brain.json — "
               "re-sync before the deployed dashboard trusts stale thresholds.")
    return (f"{len(drifted)} bundled control-center/hub-data file(s) have drifted from their "
           f"live source: {', '.join(drifted)} — re-sync before the deployed dashboard trusts "
           f"stale data.")


def format_digest(summary: Dict[str, Any], drift_warning: Optional[str],
                  run_id: Optional[Any], proposals_pending: int = 0,
                  searches_due: int = 0, cross_channel_line: Optional[str] = None,
                  queue_pending: int = 0, deals_summary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """One batched Discord embed for the whole cycle. Honest when there are zero candidates —
    says so plainly, never fabricates picks to look active."""
    picks = summary.get("picks") or []
    found = summary.get("found", 0)
    scored = summary.get("scored", 0)
    fields = [
        {"name": "Scanned", "value": str(found), "inline": True},
        {"name": "Scored", "value": str(scored), "inline": True},
        {"name": "New picks", "value": str(summary.get("new_picks", 0)), "inline": True},
    ]
    tokens = summary.get("tokens") or {}
    if tokens.get("tokens_left") is not None:
        fields.append({"name": "Keepa tokens left", "value": str(tokens["tokens_left"]), "inline": True})
    analyst_disagreements = summary.get("analyst_disagreements")
    if analyst_disagreements:
        # Scout Agent Build Plan Prompt S1 — proves the analyst pass isn't decorative: if it
        # never disagrees, the prompt needs tuning; when it does, this is where you'd notice.
        fields.append({"name": "🧠 Analyst disagreed", "value": f"{analyst_disagreements} of "
                       f"{summary.get('scored', 0)} candidates", "inline": True})
    hints_followed = summary.get("hints_followed")
    if hints_followed:
        # TOP100_DEAL_WATCH_PLAN.md T3 — discovery pointed at the nightly deal watch's hinted
        # brands FIRST. A count only; zero fresh hints just means self-directed discovery.
        fields.append({"name": "🧭 Deal-led discovery", "value": f"followed {hints_followed} "
                       f"fresh deal-hint brand(s) before the normal rotation", "inline": True})

    if picks:
        lines = []
        for p in picks[:5]:
            line = f"• `{p.get('asin','?')}` {p.get('score','?')}/100 — {(p.get('reason') or '')[:120]}"
            if p.get("analyst_narrative"):
                line += f"\n  🧠 {p['analyst_narrative'][:150]}"
            lines.append(line)
        description = "\n".join(lines)
    elif summary.get("above_threshold"):
        description = f"{summary['above_threshold']} candidate(s) cleared the score bar (already picked before)."
    elif summary.get("dry_run_live"):
        # THIS_WEEK.md Prompt W2 — an honest SKIP, not "the scout looked and found nothing."
        # Distinguishing these matters: "0 scanned" alone reads like a quiet Keepa result, not
        # "discovery didn't run yet" — a real difference an operator shouldn't have to guess at.
        description = ("Keepa discovery skipped honestly — no KEEPA_KEY configured yet "
                       "(dry-run-live mode). Deals collection, runs telemetry, and this digest "
                       "still ran for real.")
    else:
        description = f"No candidates cleared the bar this run ({found} scanned, {scored} scored)."

    embed = {
        "title": "Scout daily digest",
        "description": description,
        "color": 0x36D399 if picks else 0x8B9BB0,
        "fields": fields,
        "footer": {"text": f"run #{run_id}" if run_id else "run id unavailable"},
    }
    if drift_warning:
        embed["fields"].append({"name": "⚠ Brain drift", "value": drift_warning, "inline": False})
    if summary.get("error"):
        embed["fields"].append({"name": "⚠ Error", "value": str(summary["error"])[:500], "inline": False})
    if proposals_pending > 0:
        # System Blueprint Prompt G5 — proposals only ever surface a count here; applying one
        # is always a separate, human-initiated step (see learning-hub/tracking/brain-proposals.md).
        embed["fields"].append({"name": "💡 Brain proposals", "value": f"{proposals_pending} new brain "
                               f"proposals pending — see brain-proposals.md", "inline": False})
    if searches_due > 0:
        # Scout Agent Build Plan sec 3.3 — the brand-growth loop; a count only, execution stays
        # Keepa-gated and manual.
        embed["fields"].append({"name": "🔎 Brand searches due", "value": f"{searches_due} saved "
                               f"brand search(es) due for re-run", "inline": False})
    if queue_pending > 0:
        # CC1 — the control-center's Review Queue (/queue). A count + link only; the actual
        # approve/reject/watch decision always happens in the UI, never here.
        embed["fields"].append({"name": "🗂️ Review Queue", "value": f"{queue_pending} item(s) "
                               f"waiting on a human decision — open the control-center's "
                               f"Review Queue (/queue)", "inline": False})
    if deals_summary and deals_summary.get("total_rows"):
        # Deal Finder Build Plan D1/D3 (THIS_WEEK.md Prompt W2) — collection is live and
        # key-free (Slickdeals RSS); the matcher (D2) that would turn a deal into a scored
        # pick isn't built yet, so say so plainly rather than implying more than exists.
        per_source = ", ".join(f"{name}: {n}" for name, n in deals_summary.get("sources", {}).items())
        embed["fields"].append({"name": "🛒 Retail deals", "value": f"{deals_summary['total_rows']} "
                               f"deal(s) collected ({per_source}) — matching not yet built",
                               "inline": False})
    if cross_channel_line:
        # The digest stays the one place that proves the WHOLE run happened, even though
        # picks/proposals/alerts now also post to their own channels.
        embed["fields"].append({"name": "🔀 This cycle", "value": cross_channel_line, "inline": False})
    lake_digest = summary.get("lake_digest")
    if lake_digest:
        # V0 data lake (DATA_ENGINE_PLAN.md) — one honest line: rows/bytes archived this run,
        # running total on disk, dedupe rate. Absent when archiving is disabled.
        embed["fields"].append({"name": "🗄️ Data lake", "value": lake_digest, "inline": False})
    return {"username": "FBA Scout — Daily Digest", "embeds": [embed]}


def cross_channel_summary_line(summary: Dict[str, Any], proposals_pending: int,
                               system_health_alerts: int, queue_notified: int = 0) -> Optional[str]:
    """A one-line "picks → #scout-picks (3), proposals → #brain-proposals (2)" summary of what
    else posted THIS cycle, so the digest remains the single place that proves the whole run
    happened even though those items now go to their own channels. None if nothing else fired."""
    parts = []
    posted = summary.get("posted", 0)
    if posted:
        parts.append(f"picks → #scout-picks ({posted})")
    if proposals_pending:
        parts.append(f"proposals → #brain-proposals ({proposals_pending})")
    if system_health_alerts:
        parts.append(f"alerts → #system-health ({system_health_alerts})")
    if queue_notified:
        parts.append(f"queue → #review-queue ({queue_notified})")
    return ", ".join(parts) if parts else None


def notify_review_queue(counts: Optional[Dict[str, int]]) -> int:
    """Posts a short heads-up to the "review_queue" stream when the queue is non-empty (CC1) —
    this is the first real caller of that stream (provisioned 2026-07-02, stubbed ever since —
    see scout/discord_router.py's STREAMS registry comment). Returns the total pending count
    posted (0 if the queue is empty, counts are unavailable, or the send failed) — feeds the
    digest's cross-channel line, same convention as post_system_health_alerts()."""
    if not counts:
        return 0
    total = counts.get("leads", 0) + counts.get("deal_matches", 0)
    if total <= 0:
        return 0
    embed = {
        "title": "🗂️ Review Queue has items waiting",
        "description": f"{counts.get('leads', 0)} scout lead(s) + {counts.get('deal_matches', 0)} "
                      f"deal match(es) need a human decision. Open the control-center's Review "
                      f"Queue (/queue) to approve, reject, or watch — each action requires a reason code.",
        "color": 0xF5B14C,
    }
    ok = discord_router.send("review_queue", [embed])
    return total if ok else 0


def system_health_alerts(summary: Dict[str, Any], drift_warning: Optional[str]) -> List[Dict[str, Any]]:
    """Short embeds for conditions that deserve their OWN system_health notification — a run
    failure, brain drift, or a low Keepa token balance — separate from the daily digest so an
    on-call glance doesn't require reading the whole thing. Returns [] when nothing warrants one."""
    alerts = []
    if summary.get("error"):
        alerts.append({"title": "⚠ Scout run failed", "description": str(summary["error"])[:500],
                       "color": 0xE24C4C})
    if drift_warning:
        alerts.append({"title": "⚠ Brain drift detected", "description": drift_warning,
                       "color": 0xF5B14C})
    tokens_left = (summary.get("tokens") or {}).get("tokens_left")
    if isinstance(tokens_left, (int, float)) and tokens_left < LOW_TOKEN_WARNING_THRESHOLD:
        alerts.append({"title": "⚠ Low Keepa tokens", "color": 0xF5B14C,
                       "description": f"{tokens_left} tokens left "
                                      f"(warning threshold {LOW_TOKEN_WARNING_THRESHOLD})"})
    # V0 weekly integrity check (Mondays) — a checksum mismatch or unreadable Parquet in the
    # data lake means archived training data is corrupting; that deserves its own alert, not a
    # buried log line. Absent on non-Monday runs (integrity_check isn't run then).
    integ = summary.get("lake_integrity") or {}
    if integ.get("mismatches") or integ.get("unreadable"):
        alerts.append({"title": "⚠ Data lake integrity", "color": 0xE24C4C,
                       "description": (f"{len(integ.get('mismatches', []))} checksum mismatch(es), "
                                       f"{len(integ.get('unreadable', []))} unreadable file(s) — "
                                       f"the raw training lake may be corrupting.")})
    return alerts


def post_system_health_alerts(summary: Dict[str, Any], drift_warning: Optional[str]) -> int:
    """Posts system_health_alerts()'s embeds (if any) to the "system_health" stream. Returns
    how many were posted (0 if none, or if the send failed) — feeds the digest's cross-channel
    line. Never raises — callers (main()'s finally block) already isolate this, but a bug here
    must not even be capable of crashing the router call itself."""
    alerts = system_health_alerts(summary, drift_warning)
    if not alerts:
        return 0
    ok = discord_router.send("system_health", alerts)
    return len(alerts) if ok else 0


def post_digest(payload: Dict[str, Any]) -> bool:
    """Exactly ONE Discord message per cycle to the "daily_digest" stream — respects webhook
    rate limits by construction (never loops per-candidate). Honest no-op if no webhook/
    fallback is configured (discord_router.send() logs and returns False)."""
    embeds = payload.get("embeds") or []
    return discord_router.send("daily_digest", embeds, username=payload.get("username", "FBA Scout"))


def ping_heartbeat(ok: bool) -> bool:
    """Dead-man's switch (healthchecks.io, free) — a webhook alone can't report a machine that
    never woke up; this closes that gap. Honest no-op if HEALTHCHECK_URL isn't set (it's an
    explicit opt-in step in the System Blueprint roadmap, not assumed to exist)."""
    url = os.getenv("HEALTHCHECK_URL")
    if not url or not requests:
        return False
    target = url if ok else url.rstrip("/") + "/fail"
    try:
        requests.get(target, timeout=10)
        return True
    except Exception as e:
        log.warning("heartbeat ping failed (%s): %s", target, e)
        return False


def main(dry_run: bool = False, dry_run_live: bool = False) -> Dict[str, Any]:
    drift_warning = check_brain_drift()
    if drift_warning:
        log.warning(drift_warning)

    if not dry_run:
        # Pull the latest cloud-trained ranker (train-ranker.yml uploads to Supabase storage
        # models/ranker/current/) so the local pipeline has the current champion CANDIDATE on
        # disk at cycle start. SHADOW-ONLY: nothing consumes it in scoring until Mehmet promotes
        # via the brain key scoring.rankingChampion. Best-effort — a storage hiccup never blocks
        # the cycle. Lazy import keeps run_daily's import chain sklearn-free.
        try:
            import train_ranker
            fetched = train_ranker.fetch_current_model()
            if fetched:
                log.info("ranker: fetched current cloud model -> %s", fetched)
        except Exception as e:
            log.warning("ranker fetch failed (non-fatal): %s", e)

    summary: Dict[str, Any] = {}
    ok = False
    try:
        if dry_run_live:
            # THIS_WEEK.md Prompt W2 — "dress rehearsal": run everything that CAN run without a
            # Keepa key for REAL (deals collection, runs telemetry, digest, heartbeat — all
            # gated on `not dry_run` below, which dry_run_live never sets True), while honestly
            # SKIPPING the Keepa-dependent discovery step instead of letting it raise. A real
            # runs row is still written (status="skipped", not "failed" — nothing broke; this
            # was never expected to run yet) so Runs Health shows today's cycle happened.
            run_id = db.start_run()
            db.finish_run(run_id, status="skipped",
                          error_summary="Keepa discovery skipped honestly (dry-run-live mode, "
                                        "no KEEPA_KEY configured yet) - not a failure.")
            summary = {"found": 0, "scored": 0, "new_picks": 0, "posted": 0,
                      "run_id": run_id, "dry_run_live": True}
            ok = True
        else:
            summary = pipeline.run_once(dry_run=dry_run, post=not dry_run)
            ok = "error" not in summary
    except Exception as e:
        # Code Review 2026-07-02, Finding B5: pipeline.run_once() already redacts its OWN
        # summary["error"]/error_summary before re-raising, but `raise` re-raises the ORIGINAL
        # exception object — str(e) here is unredacted again, so this needs its own pass too
        # before it flows into the digest / system_health Discord post.
        summary = {"error": redact.redact(str(e)), "run_id": getattr(e, "run_id", None)}
        ok = False
    finally:
        # Code Review 2026-07-02, Finding S8: prefer the run_id pipeline.run_once() threaded
        # through summary["run_id"] (or the exception's .run_id attribute on failure) — it's
        # THIS cycle's actual id. Only fall back to re-querying recent_runs(limit=1) if that's
        # somehow missing (e.g. an older pipeline build); that fallback is racy against a
        # concurrent manual/scheduled run and is a last resort, not the normal path.
        run_id = summary.get("run_id")
        if run_id is None:
            recent = db.recent_runs(limit=1)
            run_id = recent[0].get("id") if recent else None

        deals_summary = None
        if not dry_run:
            # Deal Finder Build Plan D1/D3 (THIS_WEEK.md Prompt W2) — Slickdeals RSS needs no
            # key, so this can go live now; Best Buy stays key-gated with its own honest skip
            # (deals/sources/bestbuy.py). Same non-fatal isolation as every other optional step.
            try:
                deals_summary = deals_collect.collect_all()
            except Exception as e:
                log.warning("deals collection failed (non-fatal): %s", e)

        proposals_pending = 0
        searches_due = 0
        if not dry_run:
            # System Blueprint Prompt G5 — proposals only, never applied automatically. Wrapped
            # so a bug here can NEVER prevent the digest/heartbeat from firing for this cycle.
            # One call computes the proposals ONCE (avoids re-running the knowledge-driven
            # subprocess check twice for the report text vs the digest count).
            try:
                _block, proposals_pending = propose_updates.write_report_with_count()
            except Exception as e:
                log.warning("propose_updates failed (non-fatal): %s", e)
            # Scout Agent Build Plan sec 3.3 — a count only; never runs a search itself.
            try:
                searches_due = len(search_log.due_searches())
            except Exception as e:
                log.warning("search_log.due_searches failed (non-fatal): %s", e)
            # Scout Agent Build Plan sec 3.7 / Prompt S3 — weekly (Mondays), same non-fatal
            # isolation as propose_updates: a bug here must never block the digest/heartbeat.
            if _dt.datetime.now(_dt.timezone.utc).weekday() == 0:
                try:
                    ops_report.write_report()
                except Exception as e:
                    log.warning("ops_report failed (non-fatal): %s", e)
                try:
                    reflect.run_weekly()
                except Exception as e:
                    log.warning("reflect.run_weekly failed (non-fatal): %s", e)
                try:
                    memory_report.write_report()
                except Exception as e:
                    log.warning("memory_report failed (non-fatal): %s", e)
                # V1 shadow-outcome tracker — weekly re-pull of due day-30/60 candidates (1-token
                # calls, capped by learning.tokenBudget.shadowRecheckTokens). Honest no-op without
                # Keepa/Supabase. Same non-fatal isolation as every other weekly step.
                try:
                    import shadow_outcomes
                    summary["shadow_rechecks"] = shadow_outcomes.run_rechecks()
                except Exception as e:
                    log.warning("shadow recheck failed (non-fatal): %s", e)

        if not dry_run and datalake.enabled():
            # V0 data lake: deals collection (above) archived raw RSS/API bodies to the buffer
            # AFTER pipeline.run_once() already flushed its own (Keepa) portion — and in
            # dry-run-live mode run_once never ran at all — so flush here to persist them, then
            # publish the whole-cycle digest line. Mondays also run a read-back integrity check
            # (checksum-verify a sample of each partition). All non-fatal: a lake hiccup counts
            # in datalake.telemetry()['failures'] and never blocks the digest/heartbeat.
            try:
                datalake.set_run_context(run_id)
                datalake.flush(run_id)
                summary["lake_digest"] = datalake.digest_line()
                if _dt.datetime.now(_dt.timezone.utc).weekday() == 0:
                    ic = datalake.integrity_check()
                    summary["lake_integrity"] = ic
                    if ic.get("mismatches") or ic.get("unreadable"):
                        log.warning("lake integrity issues: %s", redact.redact(str(ic)))
            except Exception as e:
                log.warning("data lake flush/integrity failed (non-fatal): %s", e)

        if not dry_run:
            # V0 idle-token harvester — runs LAST, after the daily pipeline. DISABLED on the Pro
            # trickle (run_harvest() returns status="disabled" with a blocked-on-upgrade reason,
            # logged honestly, not silently absent). When enabled (post API-tier upgrade) it banks
            # the idle-token surplus as raw training data and its lake_digest supersedes the line.
            try:
                hres = harvest.run_harvest()
                summary["harvest"] = hres
                if hres.get("status") == "disabled":
                    log.info("idle-token harvester: %s", hres.get("reason"))
                elif hres.get("lake_digest"):
                    summary["lake_digest"] = hres["lake_digest"]
            except Exception as e:
                log.warning("idle-token harvest failed (non-fatal): %s", e)

        health_alert_count = 0
        if not dry_run:
            # Discord multi-channel routing (Cowork Session 23) — a run failure / brain drift /
            # low-token warning gets its own system_health notification, separate from the
            # digest, so an on-call glance doesn't require reading the whole thing. Wrapped like
            # every other optional step: must never block the digest/heartbeat.
            try:
                health_alert_count = post_system_health_alerts(summary, drift_warning)
            except Exception as e:
                log.warning("system_health alert post failed (non-fatal): %s", e)

        if not dry_run:
            # CC1 — the control-center's Review Queue. Same non-fatal isolation as every other
            # optional post-run step: must never block the digest/heartbeat.
            queue_pending_total = 0
            queue_notified = 0
            try:
                queue_counts = db.queue_pending_counts()
                queue_pending_total = sum((queue_counts or {}).values())
                queue_notified = notify_review_queue(queue_counts)
            except Exception as e:
                log.warning("review queue notify failed (non-fatal): %s", e)

            line = cross_channel_summary_line(summary, proposals_pending, health_alert_count, queue_notified)
            post_digest(format_digest(summary, drift_warning, run_id, proposals_pending,
                                      searches_due, line, queue_pending_total, deals_summary))
        # Code Review 2026-07-02, Finding S1 — REVISED from the earlier "heartbeat still fires
        # on a dry run, proving the machine is alive" design: a dry run pinging success can
        # mask the more dangerous failure mode, a scheduled task that's silently running
        # --dry-run instead of the real cycle (e.g. a botched deploy) — the heartbeat would
        # report healthy forever while NO real scan/post/lead-capture ever happens. Dry runs
        # now skip the heartbeat entirely; only a real cycle proves the schedule is alive.
        if not dry_run:
            ping_heartbeat(ok)

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the daily scout cycle end to end.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="no external writes/posts")
    mode.add_argument("--dry-run-live", action="store_true",
                      help="THIS_WEEK.md Prompt W2 - honestly skip Keepa discovery (no key "
                           "needed yet), but run everything else for real: deals collection, "
                           "a real runs row, proposals/searches-due/weekly-ops checks, the "
                           "digest, and the heartbeat. For running the daily cycle before "
                           "KEEPA_KEY exists.")
    args = parser.parse_args()
    result = main(dry_run=args.dry_run, dry_run_live=args.dry_run_live)
    print(json.dumps({k: v for k, v in result.items() if k != "picks"}, indent=2, default=str))
    sys.exit(1 if result.get("error") else 0)
