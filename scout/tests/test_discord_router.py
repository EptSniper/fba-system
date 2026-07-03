"""
Tests for scout/discord_router.py — the multi-channel Discord routing layer (Cowork Session 23
provisioned real channel webhooks into scout/.env).

SAFETY: `requests` is mocked in EVERY test that could reach a real POST — this is not
optional. Real webhook URLs live in scout/.env; a test that forgot to mock the transport would
post a real message to Mehmet's Discord server. Resolution tests also use a temporary, FAKE
entry in STREAMS pointed at a FAKE env var (never a real stream name) so they can never
accidentally resolve to a real configured webhook even if scout/.env has been loaded into
os.environ by an earlier import in the same test process.
"""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord_router  # noqa: E402


def _mock_response(status=204, body=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = body or {}
    r.text = ""
    return r


def _fake_stream(url="https://fake.example.test/webhook"):
    """Context managers for a FAKE stream + env var, never a real STREAMS entry — see module
    docstring. Returns (streams_patch, env_patch)."""
    return (
        patch.object(discord_router, "STREAMS", {"fake_stream": "FAKE_TEST_WEBHOOK_VAR"}),
        patch.dict(os.environ, {"FAKE_TEST_WEBHOOK_VAR": url}, clear=False),
    )


def setup_function(_fn=None):
    discord_router.reset_telemetry()


# ---------------------------------------------------------------------------
# Resolution order: stream's own var -> fallback -> honest skip
# ---------------------------------------------------------------------------

def test_resolve_uses_streams_own_env_var():
    streams_p, env_p = _fake_stream("https://fake.example.test/own")
    with streams_p, env_p:
        assert discord_router._resolve_url("fake_stream") == "https://fake.example.test/own"


def test_resolve_falls_back_when_stream_var_unset():
    with patch.object(discord_router, "STREAMS", {"fake_stream": "FAKE_TEST_WEBHOOK_VAR"}), \
         patch.dict(os.environ, {}, clear=False):
        os.environ.pop("FAKE_TEST_WEBHOOK_VAR", None)
        os.environ["DISCORD_WEBHOOK_FALLBACK"] = "https://fake.example.test/fallback"
        try:
            assert discord_router._resolve_url("fake_stream") == "https://fake.example.test/fallback"
        finally:
            os.environ.pop("DISCORD_WEBHOOK_FALLBACK", None)


def test_resolve_none_when_nothing_configured():
    with patch.object(discord_router, "STREAMS", {"fake_stream": "FAKE_TEST_WEBHOOK_VAR"}), \
         patch.dict(os.environ, {}, clear=False):
        os.environ.pop("FAKE_TEST_WEBHOOK_VAR", None)
        os.environ.pop("DISCORD_WEBHOOK_FALLBACK", None)
        assert discord_router._resolve_url("fake_stream") is None


def test_resolve_unknown_stream_still_checks_fallback():
    with patch.dict(os.environ, {"DISCORD_WEBHOOK_FALLBACK": "https://fake.example.test/fallback"}):
        assert discord_router._resolve_url("not_a_real_stream") == "https://fake.example.test/fallback"


def test_send_skips_honestly_when_nothing_resolves():
    with patch.object(discord_router, "STREAMS", {"fake_stream": "FAKE_TEST_WEBHOOK_VAR"}), \
         patch.dict(os.environ, {}, clear=False), \
         patch.object(discord_router, "requests") as mock_requests:
        os.environ.pop("FAKE_TEST_WEBHOOK_VAR", None)
        os.environ.pop("DISCORD_WEBHOOK_FALLBACK", None)
        result = discord_router.send("fake_stream", "hello")
    assert result is False
    mock_requests.post.assert_not_called()
    assert discord_router.telemetry()["skipped"] == 1


# ---------------------------------------------------------------------------
# send() payload shapes — text / single embed / list of embeds
# ---------------------------------------------------------------------------

def test_send_text_content():
    streams_p, env_p = _fake_stream()
    with streams_p, env_p, patch.object(discord_router, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_response(204)
        ok = discord_router.send("fake_stream", "plain text message")
    assert ok is True
    payload = mock_requests.post.call_args[1]["json"]
    assert payload["content"] == "plain text message"
    assert "embeds" not in payload


def test_send_single_embed():
    streams_p, env_p = _fake_stream()
    with streams_p, env_p, patch.object(discord_router, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_response(204)
        ok = discord_router.send("fake_stream", {"title": "hi"})
    assert ok is True
    payload = mock_requests.post.call_args[1]["json"]
    assert payload["embeds"] == [{"title": "hi"}]


def test_send_empty_list_skips_without_posting():
    streams_p, env_p = _fake_stream()
    with streams_p, env_p, patch.object(discord_router, "requests") as mock_requests:
        ok = discord_router.send("fake_stream", [])
    assert ok is False
    mock_requests.post.assert_not_called()


# ---------------------------------------------------------------------------
# Batching — up to 10 embeds per message, split across multiple messages beyond that
# ---------------------------------------------------------------------------

def test_send_batches_under_the_limit_into_one_message():
    embeds = [{"title": f"e{i}"} for i in range(5)]
    streams_p, env_p = _fake_stream()
    with streams_p, env_p, patch.object(discord_router, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_response(204)
        discord_router.send("fake_stream", embeds)
    assert mock_requests.post.call_count == 1
    assert len(mock_requests.post.call_args[1]["json"]["embeds"]) == 5


def test_send_splits_over_the_limit_into_multiple_messages():
    embeds = [{"title": f"e{i}"} for i in range(23)]  # 10 + 10 + 3
    streams_p, env_p = _fake_stream()
    with streams_p, env_p, patch.object(discord_router, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_response(204)
        discord_router.send("fake_stream", embeds)
    assert mock_requests.post.call_count == 3
    sizes = sorted(len(call.kwargs["json"]["embeds"]) for call in mock_requests.post.call_args_list)
    assert sizes == [3, 10, 10]


# ---------------------------------------------------------------------------
# 429 retry — exactly one retry, honoring Retry-After
# ---------------------------------------------------------------------------

def test_429_then_success_retries_exactly_once():
    streams_p, env_p = _fake_stream()
    with streams_p, env_p, patch.object(discord_router, "requests") as mock_requests, \
         patch.object(discord_router.time, "sleep") as mock_sleep:
        mock_requests.post.side_effect = [_mock_response(429, {"retry_after": 0.01}), _mock_response(204)]
        ok = discord_router.send("fake_stream", "hi")
    assert ok is True
    assert mock_requests.post.call_count == 2
    mock_sleep.assert_called_once()


def test_429_twice_gives_up_after_one_retry():
    streams_p, env_p = _fake_stream()
    with streams_p, env_p, patch.object(discord_router, "requests") as mock_requests, \
         patch.object(discord_router.time, "sleep"):
        mock_requests.post.side_effect = [_mock_response(429, {"retry_after": 0.01}),
                                          _mock_response(429, {"retry_after": 0.01})]
        ok = discord_router.send("fake_stream", "hi")
    assert ok is False
    assert mock_requests.post.call_count == 2  # never a third attempt


def test_other_http_error_does_not_retry():
    streams_p, env_p = _fake_stream()
    with streams_p, env_p, patch.object(discord_router, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_response(500)
        ok = discord_router.send("fake_stream", "hi")
    assert ok is False
    assert mock_requests.post.call_count == 1


def test_network_exception_degrades_honestly():
    streams_p, env_p = _fake_stream()
    with streams_p, env_p, patch.object(discord_router, "requests") as mock_requests:
        mock_requests.post.side_effect = Exception("connection refused")
        ok = discord_router.send("fake_stream", "hi")
    assert ok is False


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

def test_telemetry_counts_sent_and_failed():
    streams_p, env_p = _fake_stream()
    with streams_p, env_p, patch.object(discord_router, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_response(204)
        discord_router.send("fake_stream", "ok one")
        mock_requests.post.return_value = _mock_response(500)
        discord_router.send("fake_stream", "fails")
    t = discord_router.telemetry()
    assert t["sent"] == 1
    assert t["failed"] == 1


def test_reset_telemetry_clears_counts():
    streams_p, env_p = _fake_stream()
    with streams_p, env_p, patch.object(discord_router, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_response(204)
        discord_router.send("fake_stream", "hi")
    discord_router.reset_telemetry()
    assert discord_router.telemetry() == {"sent": 0, "skipped": 0, "failed": 0}


# ---------------------------------------------------------------------------
# send_to_url — the direct-override path (discord_notify.py's legacy webhook_url arg)
# ---------------------------------------------------------------------------

def test_send_to_url_bypasses_stream_resolution():
    with patch.object(discord_router, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_response(204)
        ok = discord_router.send_to_url("https://fake.example.test/direct", {"title": "x"})
    assert ok is True
    assert mock_requests.post.call_args[0][0] == "https://fake.example.test/direct"


# ---------------------------------------------------------------------------
# STREAMS registry sanity — every real channel from Session 23 is registered, incl. stubs
# ---------------------------------------------------------------------------

def test_streams_registry_covers_all_provisioned_channels():
    expected = {"daily_digest", "scout_picks", "retail_deals", "review_queue",
               "brain_proposals", "system_health", "outcomes"}
    assert set(discord_router.STREAMS.keys()) == expected


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in tests:
        try:
            setup_function()
            fn()
            passed += 1
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {fn.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)
