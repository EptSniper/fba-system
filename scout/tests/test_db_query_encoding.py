"""
test_db_query_encoding.py — regression tests for the timestamp-encoding bug (2026-07-08, live
incident): db.py interpolated a tz-aware ISO timestamp (e.g. "...+00:00") into a Supabase REST
query string WITHOUT percent-encoding it. PostgREST's query-string parser decodes an unescaped
'+' as a space (the historic application/x-www-form-urlencoded convention), corrupting the UTC
offset so Postgres rejected the whole filter with a 400 ("invalid input syntax for type
timestamp with time zone") -- LIVE-REPRODUCED against the real production Supabase project
during this session's audit. due_shadow_checkpoints() hit this on EVERY hourly burst, silently
zeroing out tier 1 (shadow rechecks) the whole time. get_cached_restriction() has the identical
shape on a different table (spapi_restrictions_cache).
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402


class _FakeResponse:
    def __init__(self, json_data):
        self._json = json_data

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


class TimestampQueryEncodingTest(unittest.TestCase):
    def setUp(self):
        self._enabled_patch = mock.patch.object(db, "enabled", return_value=True)
        self._enabled_patch.start()

    def tearDown(self):
        self._enabled_patch.stop()

    def test_due_shadow_checkpoints_percent_encodes_the_plus_sign(self):
        now_iso = "2026-07-08T03:16:25.295868+00:00"
        captured = {}

        def fake_get(url, **kwargs):
            captured["url"] = url
            return _FakeResponse([])

        with mock.patch.object(db.requests, "get", side_effect=fake_get):
            db.due_shadow_checkpoints(now_iso=now_iso)

        # The raw '+' must NEVER appear un-encoded in the query string -- that's exactly the byte
        # PostgREST's parser silently turns into a space, corrupting the timestamptz literal.
        self.assertNotIn("lte.2026-07-08T03:16:25.295868+00:00", captured["url"])
        self.assertIn("lte.2026-07-08T03%3A16%3A25.295868%2B00%3A00", captured["url"])

    def test_get_cached_restriction_percent_encodes_the_plus_sign(self):
        captured = {}

        def fake_get(url, **kwargs):
            captured["url"] = url
            return _FakeResponse([])

        with mock.patch.object(db.requests, "get", side_effect=fake_get):
            db.get_cached_restriction("B0TESTASIN")

        self.assertNotIn("+00:00&select", captured["url"])
        self.assertIn("%2B00%3A00", captured["url"])

    def test_due_shadow_checkpoints_still_returns_rows_on_success(self):
        """Sanity check the fix doesn't break the happy path — the whole point of the query."""
        fake_rows = [{"asin": "B0X", "status": "pending"}]
        with mock.patch.object(db.requests, "get", return_value=_FakeResponse(fake_rows)):
            result = db.due_shadow_checkpoints(now_iso="2026-07-08T00:00:00+00:00")
        self.assertEqual(result, fake_rows)


if __name__ == "__main__":
    unittest.main()
