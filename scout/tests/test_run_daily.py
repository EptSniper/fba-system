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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import run_daily  # noqa: E402


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
    never silently skip the heartbeat because the cycle blew up."""
    with patch.object(run_daily.pipeline, "run_once", side_effect=RuntimeError("No KEEPA_KEY set")), \
            patch.object(run_daily.db, "recent_runs", return_value=[]), \
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
    with patch.object(run_daily.pipeline, "run_once", return_value={"found": 3, "scored": 3, "picks": []}), \
            patch.object(run_daily.db, "recent_runs", return_value=[{"id": 5}]), \
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


def test_main_prefers_threaded_run_id_over_recent_runs_query():
    """Code Review 2026-07-02, Finding S8: pipeline.run_once() threads THIS cycle's real
    run_id through summary["run_id"] — the digest must use that, never the racy
    recent_runs(limit=1) fallback, when it's available."""
    with patch.object(run_daily.pipeline, "run_once",
                      return_value={"found": 1, "scored": 1, "picks": [], "run_id": 777}), \
            patch.object(run_daily.db, "recent_runs", return_value=[{"id": 999}]) as recent_runs, \
            patch.object(run_daily, "check_brain_drift", return_value=None), \
            patch.object(run_daily.propose_updates, "write_report_with_count", return_value=("", 0)), \
            patch.object(run_daily, "discord_router"), \
            patch.object(run_daily, "post_digest") as post_digest, \
            patch.object(run_daily, "ping_heartbeat"):
        run_daily.main(dry_run=False)

    recent_runs.assert_not_called()  # never even consulted — the threaded id was available
    digest = post_digest.call_args[0][0]
    assert "#777" in digest["embeds"][0]["footer"]["text"]


def test_main_falls_back_to_recent_runs_when_run_id_not_threaded():
    """Backward compatibility: an older pipeline build that doesn't set summary["run_id"]
    still gets a best-effort id via the pre-existing (racy) fallback, rather than "unavailable"."""
    with patch.object(run_daily.pipeline, "run_once", return_value={"found": 1, "scored": 1, "picks": []}), \
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
    """pipeline.run_once() attaches .run_id to the exception it raises (Finding S8) so the
    failed cycle's digest still shows the correct run id instead of falling back to a
    potentially-wrong recent_runs(limit=1) query."""
    boom = RuntimeError("No KEEPA_KEY set")
    boom.run_id = 555
    with patch.object(run_daily.pipeline, "run_once", side_effect=boom), \
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
        with patch.object(run_daily, "LOCAL_BRAIN", local_path), \
                patch.object(run_daily, "BUNDLED_BRAIN", bundled_path):
            warning = run_daily.check_brain_drift()
        assert warning is not None and "drift" in warning.lower()
    finally:
        os.unlink(local_path)
        os.unlink(bundled_path)


def test_brain_drift_silent_when_identical():
    content = '{"a": 1}'
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f1:
        f1.write(content)
        local_path = f1.name
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f2:
        f2.write(content)
        bundled_path = f2.name
    try:
        with patch.object(run_daily, "LOCAL_BRAIN", local_path), \
                patch.object(run_daily, "BUNDLED_BRAIN", bundled_path):
            assert run_daily.check_brain_drift() is None
    finally:
        os.unlink(local_path)
        os.unlink(bundled_path)


def test_brain_drift_silent_when_files_missing():
    with patch.object(run_daily, "LOCAL_BRAIN", "/nonexistent/path.json"), \
            patch.object(run_daily, "BUNDLED_BRAIN", "/also/nonexistent.json"):
        assert run_daily.check_brain_drift() is None


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
