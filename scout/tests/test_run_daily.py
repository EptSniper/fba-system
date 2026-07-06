"""
Tests for System Blueprint Prompt G2: scout/run_daily.py.

Zero live network calls and zero live Keepa/Discord/healthchecks dependency — everything is
mocked. This validates the ORCHESTRATION logic only (digest formatting, heartbeat fail-path,
drift detection); the actual scan itself is scout/pipeline.py's job and is tested separately.

SAFETY: every test that calls run_daily.main() patches `run_daily.discord_router` wholesale
(not just `post_digest`) — real channel webhooks live in scout/.env, and run_daily imports
pipeline -> config -> load_dotenv() at import time, so those real URLs ARE live in this
process. A test that only mocked post_digest but let post_system_health_alerts() run for
real actually posted a live "Scout run failed" message to the real #system-health channel
during this project's own development (caught and fixed here) — patch the whole module
reference, not just the one function you think will be called.
"""
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import run_daily  # noqa: E402


@pytest.fixture(autouse=True)
def _no_live_deals_collection():
    """THIS_WEEK.md Prompt W2 wired scout/deals/collect.py's collect_all() into main() as an
    unconditional (not dry_run) post-run step — a real Slickdeals RSS fetch over the network on
    every test that calls main(dry_run=False), exactly the class of mistake this file's own
    SAFETY note above already documents once for discord_router. autouse so every CURRENT and
    FUTURE test in this file is protected without having to remember to add the patch."""
    with patch.object(run_daily, "deals_collect") as mock_deals:
        mock_deals.collect_all.return_value = {"sources": {}, "total_rows": 0, "upserted": 0}
        yield mock_deals


# ---------------------------------------------------------------------------
# Digest formatting — honest, never fabricated
# ---------------------------------------------------------------------------

def test_digest_zero_candidates_is_honest_not_fake():
    summary = {"found": 12, "scored": 12, "new_picks": 0, "above_threshold": 0, "picks": []}
    digest = run_daily.format_digest(summary, drift_warning=None, run_id=7)
    embed = digest["embeds"][0]
    assert "No candidates cleared the bar" in embed["description"]
    assert "12" in embed["description"]  # scanned/scored counts are real, not omitted
    assert embed["color"] == 0x8B9BB0  # neutral, not the "success" green


def test_digest_lists_real_picks():
    summary = {
        "found": 50, "scored": 50, "new_picks": 2, "above_threshold": 2,
        "picks": [
            {"asin": "B0AAA", "score": 91.5, "reason": "great margin"},
            {"asin": "B0BBB", "score": 85.0, "reason": "solid demand"},
        ],
    }
    digest = run_daily.format_digest(summary, drift_warning=None, run_id=8)
    embed = digest["embeds"][0]
    assert "B0AAA" in embed["description"] and "B0BBB" in embed["description"]
    assert embed["color"] == 0x36D399  # success green


def test_digest_includes_token_telemetry_when_present():
    summary = {"found": 5, "scored": 5, "new_picks": 0, "picks": [], "tokens": {"tokens_left": 340}}
    digest = run_daily.format_digest(summary, drift_warning=None, run_id=None)
    field_names = [f["name"] for f in digest["embeds"][0]["fields"]]
    assert "Keepa tokens left" in field_names


def test_digest_surfaces_drift_warning():
    digest = run_daily.format_digest({"found": 0, "scored": 0}, drift_warning="brains disagree", run_id=1)
    field_names = [f["name"] for f in digest["embeds"][0]["fields"]]
    assert "⚠ Brain drift" in field_names


def test_digest_surfaces_error():
    digest = run_daily.format_digest({"error": "No KEEPA_KEY set"}, drift_warning=None, run_id=1)
    field_names = [f["name"] for f in digest["embeds"][0]["fields"]]
    assert "⚠ Error" in field_names


def test_digest_shows_deal_led_discovery_when_hints_followed():
    """TOP100_DEAL_WATCH_PLAN.md T3 — the scout's digest reports when discovery followed fresh
    deal-hint brands. Absent/zero hints_followed -> no such field (self-directed discovery)."""
    with_hints = run_daily.format_digest({"found": 5, "scored": 5, "picks": [], "hints_followed": 3},
                                         drift_warning=None, run_id=1)
    assert any("Deal-led discovery" in f["name"] for f in with_hints["embeds"][0]["fields"])
    without = run_daily.format_digest({"found": 5, "scored": 5, "picks": []}, drift_warning=None, run_id=1)
    assert not any("Deal-led discovery" in f["name"] for f in without["embeds"][0]["fields"])


# ---------------------------------------------------------------------------
# Heartbeat — success vs fail path, honest no-op without a URL
# ---------------------------------------------------------------------------

def test_heartbeat_noop_without_url():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("HEALTHCHECK_URL", None)
        with patch.object(run_daily, "requests") as mock_requests:
            assert run_daily.ping_heartbeat(ok=True) is False
            mock_requests.get.assert_not_called()


def test_heartbeat_success_hits_plain_url():
    with patch.dict(os.environ, {"HEALTHCHECK_URL": "https://hc-ping.com/abc123"}):
        with patch.object(run_daily, "requests") as mock_requests:
            mock_requests.get.return_value = MagicMock()
            run_daily.ping_heartbeat(ok=True)
            called_url = mock_requests.get.call_args[0][0]
            assert called_url == "https://hc-ping.com/abc123"


def test_heartbeat_failure_hits_fail_endpoint():
    with patch.dict(os.environ, {"HEALTHCHECK_URL": "https://hc-ping.com/abc123"}):
        with patch.object(run_daily, "requests") as mock_requests:
            mock_requests.get.return_value = MagicMock()
            run_daily.ping_heartbeat(ok=False)
            called_url = mock_requests.get.call_args[0][0]
            assert called_url == "https://hc-ping.com/abc123/fail"


def test_main_pings_failure_heartbeat_on_exception():
    """The whole point of G2's heartbeat: an exception during the cycle must still ping /fail,
    never silently skip the heartbeat because the cycle blew up. Session 54: scanning moved to
    the hourly cloud collector, so the default (non-dry-run) path no longer calls
    pipeline.run_once() at all — it now only calls db.start_run()/finish_run(). db.start_run()
    is designed to degrade gracefully rather than raise, but this still needs to hold if
    something unexpected in that path ever does raise."""
    with patch.object(run_daily.db, "start_run", side_effect=RuntimeError("Supabase unreachable")), \
            patch.object(run_daily.db, "recent_runs", return_value=[]), \
            patch.object(run_daily.db, "queue_pending_counts", return_value={"leads": 0, "deal_matches": 0}), \
            patch.object(run_daily, "check_brain_drift", return_value=None), \
            patch.object(run_daily.propose_updates, "write_report_with_count", return_value=("", 0)), \
            patch.object(run_daily, "discord_router") as mock_router, \
            patch.object(run_daily, "post_digest") as post_digest, \
            patch.object(run_daily, "ping_heartbeat") as heartbeat:
        result = run_daily.main(dry_run=False)

    assert "error" in result
    heartbeat.assert_called_once_with(False)
    post_digest.assert_called_once()
    # The error DOES generate a system_health alert — assert it went through the router (mocked
    # here), never a raw/unmocked transport.
    mock_router.send.assert_called_once()
    assert mock_router.send.call_args[0][0] == "system_health"


def test_main_pings_success_heartbeat_on_clean_run():
    """Session 54: the default (non-dry-run) path is now housekeeping-only — db.start_run() +
    db.finish_run(status="skipped") replace pipeline.run_once(). queue_pending_counts is pinned
    to zero — this test isolates the heartbeat/digest guarantee, not live Review Queue state."""
    with patch.object(run_daily.db, "start_run", return_value=9), \
            patch.object(run_daily.db, "finish_run"), \
            patch.object(run_daily.db, "recent_runs", return_value=[{"id": 5}]), \
            patch.object(run_daily.db, "queue_pending_counts", return_value={"leads": 0, "deal_matches": 0}), \
            patch.object(run_daily, "check_brain_drift", return_value=None), \
            patch.object(run_daily.propose_updates, "write_report_with_count", return_value=("", 0)), \
            patch.object(run_daily, "discord_router") as mock_router, \
            patch.object(run_daily, "post_digest") as post_digest, \
            patch.object(run_daily, "ping_heartbeat") as heartbeat:
        result = run_daily.main(dry_run=False)

    assert "error" not in result
    heartbeat.assert_called_once_with(True)
    post_digest.assert_called_once()
    mock_router.send.assert_not_called()  # nothing warrants a system_health alert on a clean run


def test_main_uses_start_run_id_never_recent_runs_when_available():
    """Session 54: the housekeeping-only default path sets summary["run_id"] DIRECTLY from
    db.start_run()'s return value — recent_runs() must never even be consulted when it's
    available (same guarantee the old pipeline.run_once()-threaded-id test enforced)."""
    with patch.object(run_daily.db, "start_run", return_value=777), \
            patch.object(run_daily.db, "finish_run"), \
            patch.object(run_daily.db, "recent_runs", return_value=[{"id": 999}]) as recent_runs, \
            patch.object(run_daily, "check_brain_drift", return_value=None), \
            patch.object(run_daily.propose_updates, "write_report_with_count", return_value=("", 0)), \
            patch.object(run_daily, "discord_router"), \
            patch.object(run_daily, "post_digest") as post_digest, \
            patch.object(run_daily, "ping_heartbeat"):
        run_daily.main(dry_run=False)

    recent_runs.assert_not_called()  # never even consulted — the id was available directly
    digest = post_digest.call_args[0][0]
    assert "#777" in digest["embeds"][0]["footer"]["text"]


def test_main_falls_back_to_recent_runs_when_start_run_unavailable():
    """If db.start_run() itself returns None (Supabase disabled/unreachable), the digest still
    gets a best-effort id via the pre-existing (racy) recent_runs(limit=1) fallback, rather than
    "unavailable"."""
    with patch.object(run_daily.db, "start_run", return_value=None), \
            patch.object(run_daily.db, "finish_run"), \
            patch.object(run_daily.db, "recent_runs", return_value=[{"id": 42}]) as recent_runs, \
            patch.object(run_daily, "check_brain_drift", return_value=None), \
            patch.object(run_daily.propose_updates, "write_report_with_count", return_value=("", 0)), \
            patch.object(run_daily, "discord_router"), \
            patch.object(run_daily, "post_digest") as post_digest, \
            patch.object(run_daily, "ping_heartbeat"):
        run_daily.main(dry_run=False)

    recent_runs.assert_called_once()
    digest = post_digest.call_args[0][0]
    assert "#42" in digest["embeds"][0]["footer"]["text"]


def test_main_threads_run_id_from_exception_attribute_on_failure():
    """If something in the try block raises with a .run_id attribute attached (the same
    convention pipeline.run_once() uses, Finding S8), the digest still shows the correct run id
    instead of falling back to a potentially-wrong recent_runs(limit=1) query."""
    boom = RuntimeError("Supabase unreachable")
    boom.run_id = 555
    with patch.object(run_daily.db, "start_run", side_effect=boom), \
            patch.object(run_daily.db, "recent_runs") as recent_runs, \
            patch.object(run_daily, "check_brain_drift", return_value=None), \
            patch.object(run_daily.propose_updates, "write_report_with_count", return_value=("", 0)), \
            patch.object(run_daily, "discord_router"), \
            patch.object(run_daily, "post_digest") as post_digest, \
            patch.object(run_daily, "ping_heartbeat"):
        run_daily.main(dry_run=False)

    recent_runs.assert_not_called()
    digest = post_digest.call_args[0][0]
    assert "#555" in digest["embeds"][0]["footer"]["text"]


def test_main_surfaces_proposal_count_in_digest():
    with patch.object(run_daily.pipeline, "run_once", return_value={"found": 3, "scored": 3, "picks": []}), \
            patch.object(run_daily.db, "recent_runs", return_value=[{"id": 5}]), \
            patch.object(run_daily, "check_brain_drift", return_value=None), \
            patch.object(run_daily.propose_updates, "write_report_with_count", return_value=("block text", 3)), \
            patch.object(run_daily, "discord_router"), \
            patch.object(run_daily, "post_digest") as post_digest, \
            patch.object(run_daily, "ping_heartbeat"):
        run_daily.main(dry_run=False)

    digest = post_digest.call_args[0][0]
    proposal_fields = [f for f in digest["embeds"][0]["fields"] if f["name"] == "💡 Brain proposals"]
    assert proposal_fields and "3 new brain" in proposal_fields[0]["value"]


def test_main_proposal_failure_never_blocks_digest_or_heartbeat():
    """A bug in propose_updates must never prevent the digest/heartbeat from firing."""
    with patch.object(run_daily.pipeline, "run_once", return_value={"found": 0, "scored": 0, "picks": []}), \
            patch.object(run_daily.db, "recent_runs", return_value=[]), \
            patch.object(run_daily, "check_brain_drift", return_value=None), \
            patch.object(run_daily.propose_updates, "write_report_with_count", side_effect=RuntimeError("boom")), \
            patch.object(run_daily, "discord_router"), \
            patch.object(run_daily, "post_digest") as post_digest, \
            patch.object(run_daily, "ping_heartbeat") as heartbeat:
        run_daily.main(dry_run=False)

    post_digest.assert_called_once()
    heartbeat.assert_called_once_with(True)


def test_main_dry_run_never_posts_digest_or_pings_heartbeat():
    """Code Review 2026-07-02, Finding S1 — REVISED from an earlier design where a dry run
    still pinged the success heartbeat ("proves the machine is alive"): that let a scheduled
    task silently running --dry-run instead of the real cycle report healthy forever while no
    real work ever happened. Dry runs must post NOTHING externally, full stop."""
    with patch.object(run_daily.pipeline, "run_once", return_value={"found": 0, "scored": 0, "picks": []}), \
            patch.object(run_daily.db, "recent_runs", return_value=[]), \
            patch.object(run_daily, "check_brain_drift", return_value=None), \
            patch.object(run_daily, "discord_router") as mock_router, \
            patch.object(run_daily, "post_digest") as post_digest, \
            patch.object(run_daily, "ping_heartbeat") as heartbeat:
        run_daily.main(dry_run=True)

    post_digest.assert_not_called()
    mock_router.send.assert_not_called()  # dry runs must post NOTHING externally
    heartbeat.assert_not_called()


# ---------------------------------------------------------------------------
# Deals collection wiring + --dry-run-live mode (THIS_WEEK.md Prompt W2)
# ---------------------------------------------------------------------------

def test_main_calls_deals_collection_on_a_real_run(_no_live_deals_collection):
    """Deal Finder Build Plan D3 — collect_all() needs no key (Slickdeals RSS is free), so it
    should run on every real (not dry_run) cycle, independent of whether Keepa succeeds."""
    with patch.object(run_daily.pipeline, "run_once", return_value={"found": 0, "scored": 0, "picks": []}), \
            patch.object(run_daily.db, "recent_runs", return_value=[]), \
            patch.object(run_daily, "check_brain_drift", return_value=None), \
            patch.object(run_daily.propose_updates, "write_report_with_count", return_value=("", 0)), \
            patch.object(run_daily, "discord_router"), \
            patch.object(run_daily, "post_digest"), \
            patch.object(run_daily, "ping_heartbeat"):
        run_daily.main(dry_run=False)

    _no_live_deals_collection.collect_all.assert_called_once()


def test_main_dry_run_never_calls_deals_collection(_no_live_deals_collection):
    """A true --dry-run must post/write NOTHING externally, including deals collection (which
    both upserts to Supabase AND posts a Discord notification — collect_all's own dry_run param
    isn't even reachable here since main() shouldn't call it at all in this mode)."""
    with patch.object(run_daily.pipeline, "run_once", return_value={"found": 0, "scored": 0, "picks": []}), \
            patch.object(run_daily.db, "recent_runs", return_value=[]), \
            patch.object(run_daily, "check_brain_drift", return_value=None), \
            patch.object(run_daily, "discord_router"), \
            patch.object(run_daily, "post_digest"), \
            patch.object(run_daily, "ping_heartbeat"):
        run_daily.main(dry_run=True)

    _no_live_deals_collection.collect_all.assert_not_called()


def test_dry_run_live_skips_keepa_pipeline_honestly(_no_live_deals_collection):
    """The core of --dry-run-live: pipeline.run_once() (which raises without a KEEPA_KEY) must
    never even be CALLED — this is an intentional skip, not an attempted-and-caught failure."""
    with patch.object(run_daily.pipeline, "run_once") as mock_run_once, \
            patch.object(run_daily.db, "start_run", return_value=42) as mock_start, \
            patch.object(run_daily.db, "finish_run") as mock_finish, \
            patch.object(run_daily, "check_brain_drift", return_value=None), \
            patch.object(run_daily.propose_updates, "write_report_with_count", return_value=("", 0)), \
            patch.object(run_daily, "discord_router"), \
            patch.object(run_daily, "post_digest"), \
            patch.object(run_daily, "ping_heartbeat") as heartbeat:
        result = run_daily.main(dry_run=False, dry_run_live=True)

    mock_run_once.assert_not_called()
    mock_start.assert_called_once()
    # Status is "skipped", never "failed" — nothing broke, this was never expected to run yet.
    mock_finish.assert_called_once()
    assert mock_finish.call_args.kwargs["status"] == "skipped"
    assert result["run_id"] == 42
    assert result["dry_run_live"] is True
    assert result["found"] == 0 and result["scored"] == 0
    assert "error" not in result
    heartbeat.assert_called_once_with(True)  # a legitimate, successful (reduced-scope) cycle


def test_dry_run_live_still_runs_deals_collection_and_digest(_no_live_deals_collection):
    """--dry-run-live is "live except Keepa" — deals collection, the digest, and everything
    else gated on `not dry_run` must still run for real (dry_run_live never sets dry_run=True)."""
    with patch.object(run_daily.db, "start_run", return_value=1), \
            patch.object(run_daily.db, "finish_run"), \
            patch.object(run_daily, "check_brain_drift", return_value=None), \
            patch.object(run_daily.propose_updates, "write_report_with_count", return_value=("", 0)), \
            patch.object(run_daily, "discord_router"), \
            patch.object(run_daily, "post_digest") as post_digest, \
            patch.object(run_daily, "ping_heartbeat"):
        run_daily.main(dry_run=False, dry_run_live=True)

    _no_live_deals_collection.collect_all.assert_called_once()
    post_digest.assert_called_once()


def test_dry_run_and_dry_run_live_are_mutually_exclusive_at_the_cli():
    """argparse should refuse both flags together rather than silently picking one."""
    import argparse
    import subprocess
    import sys as _sys
    result = subprocess.run(
        [_sys.executable, "run_daily.py", "--dry-run", "--dry-run-live"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "not allowed with argument" in result.stderr


# ---------------------------------------------------------------------------
# format_digest — deals summary + dry-run-live honesty (THIS_WEEK.md Prompt W2)
# ---------------------------------------------------------------------------

def test_digest_deals_summary_field_shows_per_source_counts():
    summary = {"found": 0, "scored": 0, "new_picks": 0, "picks": []}
    deals_summary = {"sources": {"slickdeals": 8, "bestbuy": 0}, "total_rows": 8, "upserted": 8}
    digest = run_daily.format_digest(summary, drift_warning=None, run_id=1, deals_summary=deals_summary)
    field = next(f for f in digest["embeds"][0]["fields"] if f["name"] == "🛒 Retail deals")
    assert "8 deal(s) collected" in field["value"]
    assert "slickdeals: 8" in field["value"]
    assert "matching not yet built" in field["value"]  # never implies more than exists


def test_digest_omits_deals_field_when_nothing_collected():
    """No-op when total_rows is 0/absent — never post a pointless empty field."""
    summary = {"found": 0, "scored": 0, "new_picks": 0, "picks": []}
    digest = run_daily.format_digest(summary, drift_warning=None, run_id=1,
                                     deals_summary={"sources": {}, "total_rows": 0, "upserted": 0})
    field_names = [f["name"] for f in digest["embeds"][0]["fields"]]
    assert "🛒 Retail deals" not in field_names


def test_digest_dry_run_live_description_is_honest_not_a_quiet_zero():
    """A dry-run-live cycle's "0 scanned, 0 scored" must NOT read like a normal quiet Keepa
    result — it's an intentional skip, and the description says so explicitly."""
    summary = {"found": 0, "scored": 0, "new_picks": 0, "picks": [], "dry_run_live": True}
    digest = run_daily.format_digest(summary, drift_warning=None, run_id=1)
    description = digest["embeds"][0]["description"]
    assert "skipped" in description.lower()
    assert "KEEPA_KEY" in description


# ---------------------------------------------------------------------------
# Brain-drift detection
# ---------------------------------------------------------------------------

def test_brain_drift_detects_a_real_difference():
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f1:
        f1.write('{"a": 1}')
        local_path = f1.name
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f2:
        f2.write('{"a": 2}')
        bundled_path = f2.name
    try:
        # Only patch the ai-brain.json pair — the other 7 mirrored pairs (Finding S13) are left
        # pointing at the real repo files, which is fine here since we only assert "some drift
        # was found", not the exact count/message.
        with patch.object(run_daily, "LOCAL_BRAIN", local_path), \
                patch.object(run_daily, "BUNDLED_BRAIN", bundled_path):
            warning = run_daily.check_brain_drift()
        assert warning is not None and "drift" in warning.lower()
    finally:
        os.unlink(local_path)
        os.unlink(bundled_path)


def _matched_temp_pair(content='{"a": 1}'):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f1:
        f1.write(content)
        live_path = f1.name
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f2:
        f2.write(content)
        bundled_path = f2.name
    return live_path, bundled_path


def test_brain_drift_silent_when_identical():
    # Patches ALL 8 mirrored pairs (Finding S13) to guaranteed-identical temp files — this must
    # be deterministic regardless of whether the real repo's other hub-data files happen to be
    # in sync at test time, not incidentally dependent on real-repo state.
    pairs = [_matched_temp_pair() for _ in range(8)]
    paths = [p for pair in pairs for p in pair]
    try:
        with patch.object(run_daily, "LOCAL_BRAIN", pairs[0][0]), \
                patch.object(run_daily, "BUNDLED_BRAIN", pairs[0][1]), \
                patch.object(run_daily, "OTHER_MIRRORED_HUB_DATA_FILES", pairs[1:]):
            assert run_daily.check_brain_drift() is None
    finally:
        for p in paths:
            os.unlink(p)


def test_brain_drift_silent_when_files_missing():
    with patch.object(run_daily, "LOCAL_BRAIN", "/nonexistent/path.json"), \
            patch.object(run_daily, "BUNDLED_BRAIN", "/also/nonexistent.json"), \
            patch.object(run_daily, "OTHER_MIRRORED_HUB_DATA_FILES",
                        [("/nonexistent/a.json", "/nonexistent/b.json")]):
        assert run_daily.check_brain_drift() is None


def test_brain_drift_reports_every_drifted_file_by_name():
    """Finding S13: a SECOND drifted file (not just ai-brain.json) must be named in the
    warning, not silently swallowed."""
    brain_pair = _matched_temp_pair('{"a": 1}')
    leads_live, leads_bundled = _matched_temp_pair('{"leads": 1}')
    try:
        with open(leads_bundled, "w", encoding="utf-8") as f:
            f.write('{"leads": 2}')  # force this ONE pair to actually differ
        with patch.object(run_daily, "LOCAL_BRAIN", brain_pair[0]), \
                patch.object(run_daily, "BUNDLED_BRAIN", brain_pair[1]), \
                patch.object(run_daily, "OTHER_MIRRORED_HUB_DATA_FILES", [(leads_live, leads_bundled)]):
            warning = run_daily.check_brain_drift()
        assert warning is not None
        assert os.path.basename(leads_bundled) in warning
    finally:
        for p in (*brain_pair, leads_live, leads_bundled):
            os.unlink(p)


# ---------------------------------------------------------------------------
# Multi-channel Discord routing (Cowork Session 23): post_digest -> "daily_digest",
# system_health alerts, and the cross-channel summary line.
# ---------------------------------------------------------------------------

def test_post_digest_routes_through_daily_digest_stream():
    with patch.object(run_daily, "discord_router") as mock_router:
        mock_router.send.return_value = True
        payload = {"username": "FBA Scout — Daily Digest", "embeds": [{"title": "x"}]}
        ok = run_daily.post_digest(payload)
    assert ok is True
    mock_router.send.assert_called_once_with("daily_digest", [{"title": "x"}], username="FBA Scout — Daily Digest")


def test_system_health_alerts_empty_on_clean_summary():
    assert run_daily.system_health_alerts({"found": 3, "scored": 3}, drift_warning=None) == []


def test_system_health_alerts_includes_error():
    alerts = run_daily.system_health_alerts({"error": "No KEEPA_KEY set"}, drift_warning=None)
    assert any("failed" in a["title"].lower() for a in alerts)


def test_system_health_alerts_includes_drift():
    alerts = run_daily.system_health_alerts({}, drift_warning="brains disagree")
    assert any("drift" in a["title"].lower() for a in alerts)


def test_system_health_alerts_includes_low_tokens():
    summary = {"tokens": {"tokens_left": 50}}
    alerts = run_daily.system_health_alerts(summary, drift_warning=None)
    assert any("token" in a["title"].lower() for a in alerts)


def test_system_health_alerts_silent_on_healthy_token_balance():
    summary = {"tokens": {"tokens_left": 50000}}
    assert run_daily.system_health_alerts(summary, drift_warning=None) == []


def test_post_system_health_alerts_sends_when_alerts_exist():
    with patch.object(run_daily, "discord_router") as mock_router:
        mock_router.send.return_value = True
        count = run_daily.post_system_health_alerts({"error": "boom"}, drift_warning=None)
    assert count == 1
    assert mock_router.send.call_args[0][0] == "system_health"


def test_post_system_health_alerts_noop_when_nothing_to_report():
    with patch.object(run_daily, "discord_router") as mock_router:
        count = run_daily.post_system_health_alerts({"found": 1}, drift_warning=None)
    assert count == 0
    mock_router.send.assert_not_called()


def test_post_system_health_alerts_zero_on_send_failure():
    with patch.object(run_daily, "discord_router") as mock_router:
        mock_router.send.return_value = False
        count = run_daily.post_system_health_alerts({"error": "boom"}, drift_warning=None)
    assert count == 0


def test_cross_channel_summary_line_lists_active_channels():
    line = run_daily.cross_channel_summary_line(
        {"posted": 3}, proposals_pending=2, system_health_alerts=1)
    assert "picks → #scout-picks (3)" in line
    assert "proposals → #brain-proposals (2)" in line
    assert "alerts → #system-health (1)" in line


def test_cross_channel_summary_line_none_when_nothing_happened():
    assert run_daily.cross_channel_summary_line({}, proposals_pending=0, system_health_alerts=0) is None


def test_format_digest_includes_cross_channel_field_when_given():
    digest = run_daily.format_digest({"found": 0, "scored": 0}, drift_warning=None, run_id=1,
                                     cross_channel_line="picks → #scout-picks (3)")
    field_names = [f["name"] for f in digest["embeds"][0]["fields"]]
    assert "🔀 This cycle" in field_names


# ---------------------------------------------------------------------------
# hourly_collection_summary + the negative-balance digest line (Session 55)
# ---------------------------------------------------------------------------

def test_hourly_collection_summary_none_when_no_runs_today():
    with patch.object(run_daily.db, "hourly_runs_today", return_value=[]):
        assert run_daily.hourly_collection_summary() is None


def test_hourly_collection_summary_aggregates_totals():
    runs = [
        {"tokens_consumed": 10, "asins_scanned": 3, "tokens_left_end": 5},
        {"tokens_consumed": 7, "asins_scanned": 2, "tokens_left_end": -20},
    ]
    with patch.object(run_daily.db, "hourly_runs_today", return_value=runs), \
         patch.object(run_daily.db, "count_backtest_rows", return_value=228):
        summary = run_daily.hourly_collection_summary()
    assert summary["runs_fired"] == 2
    assert summary["tokens_spent"] == 17
    assert summary["asins_scanned"] == 5
    assert summary["backtest_rows"] == 228
    assert summary["negative_balance_skips"] == 1  # only the -20 run


def test_hourly_collection_summary_counts_zero_negative_skips_honestly():
    runs = [{"tokens_consumed": 10, "asins_scanned": 3, "tokens_left_end": 40}]
    with patch.object(run_daily.db, "hourly_runs_today", return_value=runs), \
         patch.object(run_daily.db, "count_backtest_rows", return_value=0):
        summary = run_daily.hourly_collection_summary()
    assert summary["negative_balance_skips"] == 0


def test_format_digest_shows_negative_balance_warning():
    """The overdraw guard's own honest signal must surface in the digest, not stay buried in a
    log line only Claude Code ever reads."""
    digest = run_daily.format_digest(
        {"found": 0, "scored": 0, "hourly_collection": {
            "runs_fired": 4, "tokens_spent": 0, "asins_scanned": 0, "backtest_rows": 228,
            "negative_balance_skips": 4}},
        drift_warning=None, run_id=1)
    fields = {f["name"]: f["value"] for f in digest["embeds"][0]["fields"]}
    assert "⏱️ Hourly collector (today)" in fields
    assert "empty/negative" in fields["⏱️ Hourly collector (today)"]


def test_format_digest_omits_negative_balance_warning_when_zero():
    digest = run_daily.format_digest(
        {"found": 0, "scored": 0, "hourly_collection": {
            "runs_fired": 4, "tokens_spent": 40, "asins_scanned": 10, "backtest_rows": 228,
            "negative_balance_skips": 0}},
        drift_warning=None, run_id=1)
    fields = {f["name"]: f["value"] for f in digest["embeds"][0]["fields"]}
    assert "empty/negative" not in fields["⏱️ Hourly collector (today)"]


# ---------------------------------------------------------------------------
# Sampling composition (Session 55 — the brand-agnostic sampling overhaul's digest line)
# ---------------------------------------------------------------------------

def test_sampling_composition_summary_none_when_unavailable():
    with patch.object(run_daily.db, "backtest_rows_by_source", return_value={}):
        assert run_daily.sampling_composition_summary() is None


def test_sampling_composition_summary_returns_counts():
    counts = {"dealfeed": 40, "explore": 35, "onpolicy": 25}
    with patch.object(run_daily.db, "backtest_rows_by_source", return_value=counts):
        assert run_daily.sampling_composition_summary() == counts


def test_format_sampling_composition_line_percentages():
    line = run_daily.format_sampling_composition_line({"dealfeed": 40, "explore": 35, "onpolicy": 25})
    assert line.startswith("100 collected:")
    assert "40% dealfeed" in line
    assert "35% explore" in line
    assert "25% onpolicy" in line


def test_format_sampling_composition_line_omits_zero_sources():
    line = run_daily.format_sampling_composition_line({"dealfeed": 10, "explore": 0, "onpolicy": 0})
    assert "explore" not in line
    assert "onpolicy" not in line
    assert "100% dealfeed" in line


def test_format_sampling_composition_line_honest_when_empty():
    assert run_daily.format_sampling_composition_line({}) == "0 backtest rows collected yet"


def test_format_digest_includes_sampling_composition_field():
    digest = run_daily.format_digest(
        {"found": 0, "scored": 0, "sampling_composition": {"dealfeed": 5, "explore": 3, "onpolicy": 2}},
        drift_warning=None, run_id=1)
    fields = {f["name"]: f["value"] for f in digest["embeds"][0]["fields"]}
    assert "🎯 Sampling composition (corpus total)" in fields
    assert "50% dealfeed" in fields["🎯 Sampling composition (corpus total)"]


def test_format_digest_omits_sampling_field_when_absent():
    digest = run_daily.format_digest({"found": 0, "scored": 0}, drift_warning=None, run_id=1)
    fields = {f["name"]: f["value"] for f in digest["embeds"][0]["fields"]}
    assert "🎯 Sampling composition (corpus total)" not in fields


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in tests:
        try:
            fn()
            passed += 1
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {fn.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)
