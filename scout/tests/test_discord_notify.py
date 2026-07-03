"""
Tests for scout/discord_notify.py routing through discord_router.py.

SAFETY: discord_router.requests is mocked in every test — see test_discord_router.py's module
docstring for why this is non-negotiable now that real webhook URLs live in scout/.env.
"""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord_notify  # noqa: E402
import discord_router  # noqa: E402


def _mock_response(status=204):
    r = MagicMock()
    r.status_code = status
    r.text = ""
    return r


def _product(**kw):
    p = {"asin": "B0TEST01", "title": "Demo Product", "blended_score": 82.0, "reason": "good margin"}
    p.update(kw)
    return p


def setup_function(_fn=None):
    discord_router.reset_telemetry()


def test_post_pick_routes_through_scout_picks_stream():
    with patch.object(discord_router, "STREAMS", {"scout_picks": "FAKE_SCOUT_PICKS_VAR"}), \
         patch.dict(os.environ, {"FAKE_SCOUT_PICKS_VAR": "https://fake.example.test/picks"}), \
         patch.object(discord_router, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_response(204)
        ok = discord_notify.post_pick(_product())
    assert ok is True
    payload = mock_requests.post.call_args[1]["json"]
    assert payload["embeds"][0]["title"] == "Demo Product"
    assert "content" in payload  # the Keepa deep-link is preserved


def test_post_pick_explicit_webhook_url_bypasses_router_resolution():
    with patch.object(discord_router, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_response(204)
        ok = discord_notify.post_pick(_product(), webhook_url="https://fake.example.test/direct")
    assert ok is True
    assert mock_requests.post.call_args[0][0] == "https://fake.example.test/direct"


def test_post_pick_honest_skip_when_no_stream_or_fallback_configured():
    with patch.object(discord_router, "STREAMS", {"scout_picks": "FAKE_SCOUT_PICKS_VAR"}), \
         patch.dict(os.environ, {}, clear=False), \
         patch.object(discord_router, "requests") as mock_requests:
        os.environ.pop("FAKE_SCOUT_PICKS_VAR", None)
        os.environ.pop("DISCORD_WEBHOOK_FALLBACK", None)
        ok = discord_notify.post_pick(_product())
    assert ok is False
    mock_requests.post.assert_not_called()


def test_post_picks_empty_list_returns_zero_without_posting():
    with patch.object(discord_router, "requests") as mock_requests:
        assert discord_notify.post_picks([]) == 0
    mock_requests.post.assert_not_called()


def test_post_picks_batches_multiple_products_into_the_router():
    products = [_product(asin=f"B0{i:07d}") for i in range(3)]
    with patch.object(discord_router, "STREAMS", {"scout_picks": "FAKE_SCOUT_PICKS_VAR"}), \
         patch.dict(os.environ, {"FAKE_SCOUT_PICKS_VAR": "https://fake.example.test/picks"}), \
         patch.object(discord_router, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_response(204)
        sent = discord_notify.post_picks(products)
    assert sent == 3
    assert mock_requests.post.call_count == 1  # batched into a single message (<=10 embeds)
    assert len(mock_requests.post.call_args[1]["json"]["embeds"]) == 3


def test_post_picks_returns_zero_on_router_failure():
    products = [_product()]
    with patch.object(discord_router, "STREAMS", {"scout_picks": "FAKE_SCOUT_PICKS_VAR"}), \
         patch.dict(os.environ, {"FAKE_SCOUT_PICKS_VAR": "https://fake.example.test/picks"}), \
         patch.object(discord_router, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_response(500)
        sent = discord_notify.post_picks(products)
    assert sent == 0


def test_post_picks_explicit_webhook_url_uses_legacy_per_pick_path():
    # post_picks' legacy path builds its OWN requests.Session() (discord_notify.requests, not
    # discord_router.requests) — both must be mocked, or session=<real Session> would bypass
    # discord_router's mocked transport and attempt a real connection (caught via a real
    # NameResolutionError against the fake domain during development of this test).
    products = [_product(asin="B0A"), _product(asin="B0B")]
    mock_session = MagicMock()
    mock_session.post.return_value = _mock_response(204)
    with patch.object(discord_notify.requests, "Session", return_value=mock_session), \
         patch.object(discord_router, "requests") as mock_router_requests, \
         patch.object(discord_notify.time, "sleep"):
        mock_router_requests.post.return_value = _mock_response(204)  # belt-and-suspenders
        sent = discord_notify.post_picks(products, webhook_url="https://fake.example.test/direct")
    assert sent == 2
    assert mock_session.post.call_count == 2  # one message per pick, legacy behavior preserved
    mock_router_requests.post.assert_not_called()


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
