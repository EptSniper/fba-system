"""
test_raw_inbox.py — the cloud-side raw-response mailbox (DATA_ENGINE_PLAN.md hourly-collector
era, Session 54).

Covers: the enabled() flag, upload_buffered's zstd+JSON round-trip and honest failure counting
when Supabase env is absent, list_objects' folder/file distinction and pagination, and
download/delete error handling. All network calls mocked — no real Supabase traffic.
"""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import raw_inbox  # noqa: E402


class EnabledFlagTest(unittest.TestCase):
    def test_default_off(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATALAKE_CLOUD_INBOX", None)
            self.assertFalse(raw_inbox.enabled())

    def test_on_when_set(self):
        with mock.patch.dict(os.environ, {"DATALAKE_CLOUD_INBOX": "1"}):
            self.assertTrue(raw_inbox.enabled())

    def test_off_for_falsy_strings(self):
        for v in ("0", "false", "False", ""):
            with mock.patch.dict(os.environ, {"DATALAKE_CLOUD_INBOX": v}):
                self.assertFalse(raw_inbox.enabled())


class UploadBufferedTest(unittest.TestCase):
    def test_no_supabase_env_counts_all_as_failures(self):
        """Never silently lose rows: without Supabase env, every buffered row is counted as a
        failure (not just skipped quietly)."""
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SUPABASE_URL", None)
            os.environ.pop("SUPABASE_SERVICE_KEY", None)
            stats = raw_inbox.upload_buffered({"keepa": [{"content_hash": "a", "fetched_at": "t"}]})
        self.assertEqual(stats["failures"], 1)
        self.assertEqual(stats["uploaded"], 0)

    def test_uploads_each_row_as_compressed_blob(self):
        row = {"source": "keepa", "entity_id": "B01", "endpoint": "product",
              "fetched_at": "2026-07-06T00:00:00+00:00", "content_hash": "abc123def456",
              "tokens_consumed": 1, "payload": "{\"asin\":\"B01\"}", "pipeline_context": "{}"}
        posted = []

        def fake_post(url, headers=None, json=None, data=None, timeout=None):
            posted.append({"url": url, "data": data})
            resp = mock.Mock()
            resp.status_code = 200
            resp.raise_for_status = lambda: None
            resp.text = ""
            return resp

        with mock.patch.dict(os.environ, {"SUPABASE_URL": "https://x.supabase.co",
                                          "SUPABASE_SERVICE_KEY": "k"}), \
             mock.patch("requests.post", side_effect=fake_post):
            stats = raw_inbox.upload_buffered({"keepa": [row]})
        self.assertEqual(stats["uploaded"], 1)
        self.assertEqual(stats["failures"], 0)
        # one call to create the bucket, one to upload the object
        self.assertEqual(len(posted), 2)
        upload_call = posted[-1]
        self.assertIn("keepa/", upload_call["url"])
        # the uploaded blob decompresses back to the exact original row
        import zstandard
        decompressed = zstandard.ZstdDecompressor().decompress(upload_call["data"])
        self.assertEqual(json.loads(decompressed), row)


class ListObjectsTest(unittest.TestCase):
    def test_distinguishes_folders_from_files_and_paginates(self):
        calls = {"n": 0}

        def fake_post(url, headers=None, json=None, timeout=None):
            calls["n"] += 1
            resp = mock.Mock()
            resp.raise_for_status = lambda: None
            if json.get("prefix") == "":
                resp.json = lambda: [{"name": "keepa", "id": None}]
            elif json.get("offset", 0) == 0:
                resp.json = lambda: [{"name": f"f{i}.json.zst", "id": f"id{i}",
                                     "metadata": {"size": 10}} for i in range(raw_inbox._LIST_PAGE)]
            else:
                resp.json = lambda: [{"name": "last.json.zst", "id": "idlast", "metadata": {"size": 5}}]
            return resp

        with mock.patch.dict(os.environ, {"SUPABASE_URL": "https://x.supabase.co",
                                          "SUPABASE_SERVICE_KEY": "k"}), \
             mock.patch("requests.post", side_effect=fake_post):
            objs = raw_inbox.list_objects(limit=5000)
        self.assertEqual(len(objs), raw_inbox._LIST_PAGE + 1)
        self.assertTrue(all(o["name"].startswith("keepa/") for o in objs))
        self.assertEqual(sum(o["size"] for o in objs), raw_inbox._LIST_PAGE * 10 + 5)

    def test_no_supabase_env_returns_empty(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SUPABASE_URL", None)
            os.environ.pop("SUPABASE_SERVICE_KEY", None)
            self.assertEqual(raw_inbox.list_objects(), [])


class DownloadDeleteTest(unittest.TestCase):
    def test_download_round_trips_a_row(self):
        row = {"source": "keepa", "content_hash": "abc"}
        import zstandard
        blob = zstandard.ZstdCompressor().compress(json.dumps(row).encode())

        def fake_get(url, headers=None, timeout=None):
            resp = mock.Mock()
            resp.raise_for_status = lambda: None
            resp.content = blob
            return resp

        with mock.patch.dict(os.environ, {"SUPABASE_URL": "https://x.supabase.co",
                                          "SUPABASE_SERVICE_KEY": "k"}), \
             mock.patch("requests.get", side_effect=fake_get):
            out = raw_inbox.download("keepa/x.json.zst")
        self.assertEqual(out, row)

    def test_download_failure_returns_none_not_raise(self):
        with mock.patch.dict(os.environ, {"SUPABASE_URL": "https://x.supabase.co",
                                          "SUPABASE_SERVICE_KEY": "k"}), \
             mock.patch("requests.get", side_effect=RuntimeError("network down")):
            self.assertIsNone(raw_inbox.download("keepa/x.json.zst"))

    def test_delete_empty_list_is_noop(self):
        self.assertEqual(raw_inbox.delete([]), 0)

    def test_delete_failure_returns_zero_not_raise(self):
        with mock.patch.dict(os.environ, {"SUPABASE_URL": "https://x.supabase.co",
                                          "SUPABASE_SERVICE_KEY": "k"}), \
             mock.patch("requests.delete", side_effect=RuntimeError("network down")):
            self.assertEqual(raw_inbox.delete(["a"]), 0)


if __name__ == "__main__":
    unittest.main()
