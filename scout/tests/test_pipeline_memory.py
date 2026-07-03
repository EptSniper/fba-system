"""Tests for the optional Supabase business-memory handoff."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pipeline


def _candidate(**overrides):
    row = {
        "asin": "B000TEST01",
        "title": "Test product",
        "blended_score": 82,
        "reason": "Strong demand and margin",
    }
    row.update(overrides)
    return row


def test_supabase_memory_logs_review_and_negative_examples():
    rows = []

    def capture(product, score, verdict, reason, found_via="scout", explanation=None):
        rows.append((product["asin"], score, verdict, reason, explanation))
        return len(rows)

    candidates = [
        _candidate(),
        _candidate(asin="B000TEST02", blended_score=42, reason="Weak margin"),
        _candidate(asin="B000TEST03", hard_reject="Amazon owns the Buy Box"),
    ]
    with patch.object(pipeline.db, "enabled", return_value=True), \
            patch.object(pipeline.db, "log_lead", side_effect=capture), \
            patch.object(pipeline.db, "upsert_keepa_snapshot") as snap:
        assert pipeline._log_supabase_leads(candidates, threshold=70) == 3

    assert [row[2] for row in rows] == ["review", "pass", "pass"]
    assert rows[2][3].startswith("Hard reject: Amazon owns the Buy Box.")
    # Every evaluated candidate (not just posted picks) gets a same-day Keepa snapshot too.
    assert snap.call_count == 3


def test_supabase_memory_skips_external_writes_during_dry_run():
    with patch.object(pipeline.db, "enabled", return_value=True), \
            patch.object(pipeline.db, "log_lead") as log_lead, \
            patch.object(pipeline.db, "upsert_keepa_snapshot") as snap:
        assert pipeline._log_supabase_leads(
            [_candidate()], threshold=70, dry_run=True
        ) == 0
        log_lead.assert_not_called()
        snap.assert_not_called()


# ---------------------------------------------------------------------------
# _maybe_post_picks — must check discord_router directly, NOT the legacy
# config.have_discord()/DISCORD_WEBHOOK_URL (which the new per-channel .env doesn't set —
# gating on it would silently skip real posts; caught and fixed during this session).
# ---------------------------------------------------------------------------

def test_maybe_post_picks_none_when_nothing_fresh():
    assert pipeline._maybe_post_picks([]) is None


def test_maybe_post_picks_skips_honestly_without_a_webhook():
    with patch.object(pipeline.discord_router, "_resolve_url", return_value=None):
        assert pipeline._maybe_post_picks([_candidate()]) is None


def test_maybe_post_picks_posts_when_scout_picks_webhook_resolves():
    with patch.object(pipeline.discord_router, "_resolve_url", return_value="https://fake.example.test/picks"):
        import discord_notify
        with patch.object(discord_notify, "post_picks", return_value=1) as mock_post:
            result = pipeline._maybe_post_picks([_candidate()])
    assert result == 1
    mock_post.assert_called_once()


def test_maybe_post_picks_never_gated_by_legacy_have_discord():
    """The regression this test locks in: config.have_discord() reflects the OLD single
    DISCORD_WEBHOOK_URL var, which the new per-channel .env doesn't set — it must have NO
    bearing on whether picks get posted."""
    with patch.object(pipeline.config, "have_discord", return_value=False), \
            patch.object(pipeline.discord_router, "_resolve_url", return_value="https://fake.example.test/picks"):
        import discord_notify
        with patch.object(discord_notify, "post_picks", return_value=1) as mock_post:
            result = pipeline._maybe_post_picks([_candidate()])
    assert result == 1
    mock_post.assert_called_once()


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
