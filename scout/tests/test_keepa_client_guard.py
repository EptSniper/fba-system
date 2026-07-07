"""
test_keepa_client_guard.py — the hard overdraw guard (Session 55).

LIVE-CONFIRMED BUG: the Keepa balance hit -100 tokens because a batched request was sized off an
estimate without ever checking the actual bank first — Keepa charges the full batch cost upfront
and ALLOWS negative balances (the consequence is ~100 minutes of enforced lockout at the 1
token/min Pro-trickle refill rate). This is the single-choke-point fix: every request-making
function in keepa_client.py routes through _guard_batch() before firing, so no caller can repeat
this by forgetting to check its own budget first.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import keepa_client  # noqa: E402


class FakeApi:
    """A minimal keepa.Keepa stand-in with a controllable, mutable token bank."""
    def __init__(self, tokens_left=60):
        self.tokens_left = tokens_left
        self.tokens_consumed = 0
        self.last_query_asins = None

    def update_status(self):
        pass  # the real client refreshes tokens_left here; this fake's value is set directly

    def query(self, asins, **kwargs):
        self.last_query_asins = list(asins)
        self.tokens_consumed += len(asins)
        return [{"asin": a, "title": f"t{a}", "stats": {}} for a in asins]


class CurrentTokensLeftTest(unittest.TestCase):
    def test_reads_possibly_negative_value(self):
        self.assertEqual(keepa_client.current_tokens_left(FakeApi(tokens_left=-100)), -100)

    def test_unreadable_attribute_returns_none(self):
        self.assertIsNone(keepa_client.current_tokens_left(object()))

    def test_update_status_failure_still_reads_existing_value(self):
        api = FakeApi(tokens_left=15)
        api.update_status = mock.Mock(side_effect=RuntimeError("network hiccup"))
        self.assertEqual(keepa_client.current_tokens_left(api), 15)


class GuardBatchTest(unittest.TestCase):
    def setUp(self):
        keepa_client.reset_guard_telemetry()

    def test_caps_batch_to_affordable_size(self):
        api = FakeApi(tokens_left=20)
        capped, skip = keepa_client._guard_batch(api, 100, 3, "enrich")
        self.assertFalse(skip)
        self.assertEqual(capped, 6)  # 20 // 3 = 6
        self.assertEqual(keepa_client.guard_telemetry()["caps"], 1)

    def test_does_not_cap_when_affordable(self):
        api = FakeApi(tokens_left=60)
        capped, skip = keepa_client._guard_batch(api, 10, 3, "enrich")
        self.assertFalse(skip)
        self.assertEqual(capped, 10)
        self.assertEqual(keepa_client.guard_telemetry()["caps"], 0)

    def test_skips_entirely_when_bank_is_zero(self):
        api = FakeApi(tokens_left=0)
        capped, skip = keepa_client._guard_batch(api, 50, 3, "enrich")
        self.assertTrue(skip)
        self.assertEqual(capped, 0)
        self.assertEqual(keepa_client.guard_telemetry()["skips"], 1)

    def test_skips_entirely_when_bank_is_negative(self):
        """The exact scenario that caused the live -100 debt: a negative bank must refuse
        EVERY further request, not just cap it smaller."""
        api = FakeApi(tokens_left=-100)
        capped, skip = keepa_client._guard_batch(api, 50, 3, "enrich")
        self.assertTrue(skip)
        self.assertEqual(capped, 0)

    def test_unreadable_bank_degrades_to_trusting_caller(self):
        capped, skip = keepa_client._guard_batch(object(), 100, 3, "enrich")
        self.assertFalse(skip)
        self.assertEqual(capped, 100)  # unchanged — can't guard what can't be read

    def test_zero_requested_is_a_noop(self):
        api = FakeApi(tokens_left=20)
        capped, skip = keepa_client._guard_batch(api, 0, 3, "enrich")
        self.assertFalse(skip)
        self.assertEqual(capped, 0)


class EnrichGuardIntegrationTest(unittest.TestCase):
    """The user's own regression spec: mock tokensLeft=20, request 100 ASINs -> the client caps
    to <=20-token-cost worth of ASINs (ENRICH_TOKENS_PER_ASIN=3 -> 6 ASINs)."""

    def setUp(self):
        self._keepa_patch = mock.patch.object(keepa_client, "_KEEPA", True)
        self._keepa_patch.start()
        keepa_client.reset_guard_telemetry()

    def tearDown(self):
        self._keepa_patch.stop()

    def test_enrich_caps_100_asin_request_to_affordable_size(self):
        api = FakeApi(tokens_left=20)
        asins = [f"B{i:09d}" for i in range(100)]
        out = keepa_client.enrich(asins, api=api)
        self.assertEqual(len(api.last_query_asins), 5)  # 20 // 4 (corrected 2026-07-07), never the full 100
        self.assertEqual(len(out), 5)

    def test_enrich_returns_empty_when_bank_empty(self):
        api = FakeApi(tokens_left=0)
        out = keepa_client.enrich([f"B{i}" for i in range(10)], api=api)
        self.assertEqual(out, [])
        self.assertIsNone(api.last_query_asins)  # never even attempted the request

    def test_enrich_returns_empty_when_bank_negative(self):
        """Reproduces the live bug's aftermath: once the bank is negative, EVERY subsequent
        enrich() call must refuse outright until it recovers, never attempt a smaller batch."""
        api = FakeApi(tokens_left=-100)
        out = keepa_client.enrich([f"B{i}" for i in range(10)], api=api)
        self.assertEqual(out, [])
        self.assertIsNone(api.last_query_asins)

    def test_query_history_caps_to_affordable_size(self):
        api = FakeApi(tokens_left=20)
        asins = [f"B{i:09d}" for i in range(100)]
        keepa_client.query_history(asins, api=api)
        self.assertEqual(len(api.last_query_asins), 20)  # 20 // 1 (HISTORY_TOKENS_PER_ASIN)


if __name__ == "__main__":
    unittest.main()
