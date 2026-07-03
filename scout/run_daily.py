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
    python run_daily.py             # real run — needs KEEPA_KEY (see .env)
    python run_daily.py --dry-run   # no external writes/posts; prints the summary

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

import db
import discord_router
import memory_report
import ops_report
import pipeline
import propose_updates
import redact
import reflect
import search_log

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

log = logging.getLogger("scout.run_daily")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_BRAIN = os.path.join(HERE, "..", "learning-hub", "data", "ai-brain.json")
BUNDLED_BRAIN = os.path.join(HERE, "..", "control-center", "hub-data", "ai-brain.json")

# Below this many Keepa tokens left, post a dedicated system_health warning (a drained key
# silently looks like "no results" otherwise — System Blueprint Prompt G2's own concern,
# now routed to its own channel instead of only a digest field).
LOW_TOKEN_WARNING_THRESHOLD = int(os.getenv("LOW_TOKEN_WARNING_THRESHOLD", "1000"))


def check_brain_drift() -> Optional[str]:
    """Warn if the bundled control-center snapshot has drifted from the live brain — this exact
    kind of drift has bitten the project before (see AI_COLLABORATION_JOURNAL.md's known-drift
    history). Returns a warning string, or None if they match or either file is simply absent."""
    try:
        with open(LOCAL_BRAIN, encoding="utf-8") as f:
            local = f.read()
        with open(BUNDLED_BRAIN, encoding="utf-8") as f:
            bundled = f.read()
    except FileNotFoundError:
        return None
    if local != bundled:
        return ("hub-data/ai-brain.json has drifted from learning-hub/data/ai-brain.json — "
               "re-sync before the deployed dashboard trusts stale thresholds.")
    return None


def format_digest(summary: Dict[str, Any], drift_warning: Optional[str],
                  run_id: Optional[Any], proposals_pending: int = 0,
                  searches_due: int = 0, cross_channel_line: Optional[str] = None) -> Dict[str, Any]:
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
    if cross_channel_line:
        # The digest stays the one place that proves the WHOLE run happened, even though
        # picks/proposals/alerts now also post to their own channels.
        embed["fields"].append({"name": "🔀 This cycle", "value": cross_channel_line, "inline": False})
    return {"username": "FBA Scout — Daily Digest", "embeds": [embed]}


def cross_channel_summary_line(summary: Dict[str, Any], proposals_pending: int,
                               system_health_alerts: int) -> Optional[str]:
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
    return ", ".join(parts) if parts else None


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


def main(dry_run: bool = False) -> Dict[str, Any]:
    drift_warning = check_brain_drift()
    if drift_warning:
        log.warning(drift_warning)

    summary: Dict[str, Any] = {}
    ok = False
    try:
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
            line = cross_channel_summary_line(summary, proposals_pending, health_alert_count)
            post_digest(format_digest(summary, drift_warning, run_id, proposals_pending,
                                      searches_due, line))
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
    parser.add_argument("--dry-run", action="store_true", help="no external writes/posts")
    args = parser.parse_args()
    result = main(dry_run=args.dry_run)
    print(json.dumps({k: v for k, v in result.items() if k != "picks"}, indent=2, default=str))
    sys.exit(1 if result.get("error") else 0)
