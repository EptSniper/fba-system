"""
test_drain_inbox.py — pulling the cloud collector's raw-inbox mailbox into the local Parquet
lake (DATA_ENGINE_PLAN.md hourly-collector era, Session 54).

Covers: checksum verification (a corrupted/truncated download must NOT be ingested or deleted —
left in the bucket for manual review), the disabled/no-Supabase-env honest state, and the happy
path (list -> download -> verify -> ingest -> flush -> delete), all with raw_inbox/datalake
mocked so no real Supabase or disk I/O happens.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import drain_inbox  # noqa: E402
import datalake  # noqa: E402
import raw_inbox  # noqa: E402


class VerifyChecksumTest(unittest.TestCase):
    def test_matching_hash_passes(self):
        payload = '{"asin":"B01"}'
        row = {"payload": payload, "content_hash": datalake.content_hash(payload)}
        self.assertTrue(drain_inbox._verify_checksum(row))

    def test_mismatched_hash_fails(self):
        row = {"payload": '{"asin":"B01"}', "content_hash": "deadbeef"}
        self.assertFalse(drain_inbox._verify_checksum(row))

    def test_missing_fields_fail_closed(self):
        self.assertFalse(drain_inbox._verify_checksum({"payload": "x"}))
        self.assertFalse(drain_inbox._verify_checksum({"content_hash": "x"}))
        self.assertFalse(drain_inbox._verify_checksum({}))


class DrainTest(unittest.TestCase):
    def test_disabled_without_supabase_env(self):
        with mock.patch.object(raw_inbox, "_supa", return_value=""):
            r = drain_inbox.drain()
        self.assertEqual(r["status"], "disabled")

    def test_empty_bucket_is_a_clean_noop(self):
        with mock.patch.object(raw_inbox, "_supa", return_value="https://x.supabase.co"), \
             mock.patch.object(raw_inbox, "_storage_headers", return_value={"apikey": "k"}), \
             mock.patch.object(raw_inbox, "list_objects", return_value=[]):
            r = drain_inbox.drain()
        self.assertEqual(r["listed"], 0)
        self.assertEqual(r["ingested"], 0)

    def test_good_object_is_ingested_flushed_and_deleted(self):
        payload = '{"asin":"B01"}'
        row = {"source": "keepa", "entity_id": "B01", "endpoint": "product",
              "payload": payload, "content_hash": datalake.content_hash(payload),
              "fetched_at": "2026-07-06T00:00:00+00:00"}
        objects = [{"name": "keepa/x.json.zst", "size": 100}]
        with mock.patch.object(raw_inbox, "_supa", return_value="https://x.supabase.co"), \
             mock.patch.object(raw_inbox, "_storage_headers", return_value={"apikey": "k"}), \
             mock.patch.object(raw_inbox, "list_objects", side_effect=[objects, []]), \
             mock.patch.object(raw_inbox, "download", return_value=row), \
             mock.patch.object(raw_inbox, "delete", return_value=1) as mdelete, \
             mock.patch.object(datalake, "ingest_external_row", return_value=True) as mingest, \
             mock.patch.object(datalake, "flush", return_value={}), \
             mock.patch.object(datalake, "digest_line", return_value="lake: +1 rows"):
            r = drain_inbox.drain()
        mingest.assert_called_once_with(row)
        mdelete.assert_called_once_with(["keepa/x.json.zst"])
        self.assertEqual(r["ingested"], 1)
        self.assertEqual(r["deleted"], 1)

    def test_checksum_mismatch_is_not_ingested_and_not_deleted(self):
        """A corrupted/truncated download must be left in the bucket for manual review, never
        silently ingested with bad data, never silently deleted either."""
        bad_row = {"source": "keepa", "entity_id": "B02", "endpoint": "product",
                  "payload": '{"asin":"B02"}', "content_hash": "wronghash",
                  "fetched_at": "2026-07-06T00:00:00+00:00"}
        objects = [{"name": "keepa/bad.json.zst", "size": 50}]
        with mock.patch.object(raw_inbox, "_supa", return_value="https://x.supabase.co"), \
             mock.patch.object(raw_inbox, "_storage_headers", return_value={"apikey": "k"}), \
             mock.patch.object(raw_inbox, "list_objects", side_effect=[objects, objects]), \
             mock.patch.object(raw_inbox, "download", return_value=bad_row), \
             mock.patch.object(raw_inbox, "delete") as mdelete, \
             mock.patch.object(datalake, "ingest_external_row") as mingest, \
             mock.patch.object(datalake, "flush", return_value={}), \
             mock.patch.object(datalake, "digest_line", return_value=""):
            r = drain_inbox.drain()
        mingest.assert_not_called()
        mdelete.assert_not_called()
        self.assertEqual(r["checksum_failed"], 1)
        self.assertEqual(r["ingested"], 0)

    def test_download_failure_is_not_ingested_and_not_deleted(self):
        objects = [{"name": "keepa/missing.json.zst", "size": 10}]
        with mock.patch.object(raw_inbox, "_supa", return_value="https://x.supabase.co"), \
             mock.patch.object(raw_inbox, "_storage_headers", return_value={"apikey": "k"}), \
             mock.patch.object(raw_inbox, "list_objects", side_effect=[objects, objects]), \
             mock.patch.object(raw_inbox, "download", return_value=None), \
             mock.patch.object(raw_inbox, "delete") as mdelete, \
             mock.patch.object(datalake, "ingest_external_row") as mingest, \
             mock.patch.object(datalake, "flush", return_value={}), \
             mock.patch.object(datalake, "digest_line", return_value=""):
            r = drain_inbox.drain()
        mingest.assert_not_called()
        mdelete.assert_not_called()
        self.assertEqual(r["download_failed"], 1)

    def test_bucket_size_warning_at_threshold(self):
        # A large object that fails to download (left undrained) both times list_objects is
        # consulted (before AND after the drain attempt) -> bucket_bytes_after stays at/above
        # the warning threshold.
        big_objects = [{"name": "keepa/huge.json.zst", "size": drain_inbox.WARN_BYTES}]
        with mock.patch.object(raw_inbox, "_supa", return_value="https://x.supabase.co"), \
             mock.patch.object(raw_inbox, "_storage_headers", return_value={"apikey": "k"}), \
             mock.patch.object(raw_inbox, "list_objects", side_effect=[big_objects, big_objects]), \
             mock.patch.object(raw_inbox, "download", return_value=None), \
             mock.patch.object(datalake, "flush", return_value={}), \
             mock.patch.object(datalake, "digest_line", return_value=""):
            r = drain_inbox.drain()
        self.assertIn("bucket_warning", r)


class DigestLineTest(unittest.TestCase):
    def test_disabled_line(self):
        line = drain_inbox.digest_line({"status": "disabled", "reason": "no env"})
        self.assertIn("disabled", line)

    def test_normal_line_mentions_counts(self):
        line = drain_inbox.digest_line({"listed": 5, "ingested": 5, "deleted": 5,
                                       "bucket_bytes_after": 1_000_000})
        self.assertIn("5/5", line)
        self.assertIn("1.0MB", line)

    def test_failures_are_surfaced_in_the_line(self):
        line = drain_inbox.digest_line({"listed": 3, "ingested": 1, "deleted": 1,
                                       "checksum_failed": 1, "download_failed": 1,
                                       "bucket_bytes_after": 0})
        self.assertIn("checksum fail", line)
        self.assertIn("download fail", line)


if __name__ == "__main__":
    unittest.main()
