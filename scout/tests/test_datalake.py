"""
test_datalake.py — the raw data lake (DATA_ENGINE_PLAN.md V0).

Covers the plan's required test surface: round-trip write/read with zstd, dedupe (same payload
twice -> one row + a manifest last_seen bump), partition layout, archive-failure isolation
(a broken writer loses data but NEVER breaks the caller), the OneDrive-path warning, the
enabled/disabled gate, integrity check, and the digest line.

conftest.py disables archiving for the rest of the suite; every test here re-enables it against
its OWN temp lake dir and restores the environment in tearDown, so nothing leaks to the real
C:\\fba-data-lake or to sibling tests.
"""
import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import datalake  # noqa: E402

try:
    import pyarrow.parquet as pq  # noqa: E402
    _HAVE_PYARROW = True
except Exception:
    _HAVE_PYARROW = False


@unittest.skipUnless(_HAVE_PYARROW, "pyarrow not installed — lake archiving no-ops without it")
class DataLakeTest(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("DATALAKE_ENABLED", "DATA_LAKE_DIR",
                                                    "DATALAKE_HTML_CONF_THRESHOLD")}
        self.tmp = tempfile.mkdtemp(prefix="fba-lake-test-")
        os.environ["DATALAKE_ENABLED"] = "1"
        os.environ["DATA_LAKE_DIR"] = self.tmp
        datalake.reset_stats()
        datalake.set_run_context("test-run")

    def tearDown(self):
        datalake.reset_stats()
        shutil.rmtree(self.tmp, ignore_errors=True)
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # --- round-trip ---------------------------------------------------------
    def test_round_trip_write_read_zstd(self):
        self.assertTrue(datalake.archive("keepa", "B01", "product", {"asin": "B01", "price": 999}))
        stats = datalake.flush("test-run")
        self.assertEqual(stats["written"], 1)
        # find the parquet file under keepa/date=.../
        found = []
        for dp, _d, files in os.walk(self.tmp):
            found += [os.path.join(dp, f) for f in files if f.endswith(".parquet")]
        self.assertEqual(len(found), 1)
        table = pq.read_table(found[0])
        self.assertIn("payload", table.column_names)
        self.assertIn("content_hash", table.column_names)
        row = table.to_pylist()[0]
        self.assertEqual(row["source"], "keepa")
        self.assertEqual(row["entity_id"], "B01")
        # the parquet actually used zstd compression
        meta = pq.read_metadata(found[0])
        codecs = {meta.row_group(0).column(i).compression for i in range(meta.num_columns)}
        self.assertIn("ZSTD", codecs)

    # --- dedupe -------------------------------------------------------------
    def test_dedupe_same_payload_once(self):
        payload = {"asin": "B02", "price": 500}
        self.assertTrue(datalake.archive("keepa", "B02", "product", payload))
        self.assertFalse(datalake.archive("keepa", "B02", "product", payload))  # dedupe hit
        stats = datalake.telemetry()
        self.assertEqual(stats["buffered"], 1)
        self.assertEqual(stats["deduped"], 1)
        datalake.flush("test-run")
        # exactly one row on disk despite two archive calls
        rows = 0
        for dp, _d, files in os.walk(self.tmp):
            for f in files:
                if f.endswith(".parquet"):
                    rows += pq.read_metadata(os.path.join(dp, f)).num_rows
        self.assertEqual(rows, 1)

    def test_changed_payload_appends(self):
        self.assertTrue(datalake.archive("keepa", "B03", "product", {"asin": "B03", "price": 100}))
        self.assertTrue(datalake.archive("keepa", "B03", "product", {"asin": "B03", "price": 200}))
        self.assertEqual(datalake.telemetry()["buffered"], 2)

    # --- partition layout ---------------------------------------------------
    def test_partition_layout_hive(self):
        datalake.archive("keepa", "B04", "product", {"x": 1})
        datalake.archive("deals_rss", "http://x", "rss", "<rss/>")
        datalake.flush("test-run")
        # <root>/<source>/date=YYYY-MM-DD/part-*.parquet
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "keepa")))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "deals_rss")))
        keepa_partitions = os.listdir(os.path.join(self.tmp, "keepa"))
        self.assertEqual(len(keepa_partitions), 1)
        self.assertTrue(keepa_partitions[0].startswith("date="))

    def test_one_file_per_source_per_flush(self):
        for i in range(5):
            datalake.archive("keepa", f"B{i}", "product", {"i": i})
        datalake.flush("test-run")
        part_dir = os.path.join(self.tmp, "keepa", os.listdir(os.path.join(self.tmp, "keepa"))[0])
        parquet_files = [f for f in os.listdir(part_dir) if f.endswith(".parquet")]
        self.assertEqual(len(parquet_files), 1)  # 5 rows, ONE file (batch-per-run)

    # --- failure isolation --------------------------------------------------
    def test_archive_never_raises_on_bad_writer(self):
        # A flush whose parquet write raises must be counted, preserve the buffer, and NOT raise.
        datalake.archive("keepa", "B05", "product", {"x": 1})
        import pyarrow as pa
        orig = pq.write_table
        try:
            pq.write_table = lambda *a, **k: (_ for _ in ()).throw(IOError("disk full"))
            stats = datalake.flush("test-run")  # must not raise
        finally:
            pq.write_table = orig
        self.assertGreaterEqual(stats["failures"], 1)
        # buffer preserved for retry -> a real flush now succeeds
        stats2 = datalake.flush("test-run")
        self.assertEqual(stats2["written"], 1)

    def test_archive_bad_payload_is_swallowed(self):
        class Unserializable:
            def __repr__(self):
                raise RuntimeError("boom")
        # _as_text falls back to str() which raises here -> archive() must swallow + count.
        res = datalake.archive("keepa", "B06", "product", Unserializable())
        self.assertFalse(res)

    # --- OneDrive-path warning ---------------------------------------------
    def test_onedrive_path_warned(self):
        proj = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self.assertTrue(datalake._is_inside_onedrive_project(os.path.join(proj, "some-lake")))
        self.assertFalse(datalake._is_inside_onedrive_project(self.tmp))

    # --- enabled/disabled gate ---------------------------------------------
    def test_disabled_is_noop(self):
        os.environ["DATALAKE_ENABLED"] = "0"
        self.assertFalse(datalake.enabled())
        self.assertFalse(datalake.archive("keepa", "B07", "product", {"x": 1}))
        self.assertEqual(datalake.telemetry()["buffered"], 0)

    # --- integrity check ----------------------------------------------------
    def test_integrity_check_ok(self):
        datalake.archive("keepa", "B08", "product", {"x": 1})
        datalake.flush("test-run")
        ic = datalake.integrity_check()
        self.assertEqual(ic["ok"], ic["checked"])
        self.assertGreaterEqual(ic["checked"], 1)
        self.assertEqual(ic["mismatches"], [])
        self.assertEqual(ic["unreadable"], [])

    # --- clearance-HTML confidence gate ------------------------------------
    def test_clearance_html_skipped_when_clean_and_unchanged(self):
        # high confidence + unchanged -> not archived
        self.assertFalse(datalake.archive_clearance_html("http://x", "<html/>",
                                                         extraction_confidence=0.9, changed=False))
        # low confidence -> archived even if unchanged
        self.assertTrue(datalake.archive_clearance_html("http://y", "<html/>",
                                                       extraction_confidence=0.1, changed=False))
        # changed -> archived even at high confidence
        self.assertTrue(datalake.archive_clearance_html("http://z", "<html/>",
                                                       extraction_confidence=0.9, changed=True))

    # --- digest line --------------------------------------------------------
    def test_digest_line_reports_counts(self):
        datalake.archive("keepa", "B09", "product", {"x": 1})
        datalake.archive("keepa", "B09", "product", {"x": 1})  # dedupe
        datalake.flush("test-run")
        line = datalake.digest_line()
        self.assertIn("lake:", line)
        self.assertIn("rows", line)
        self.assertIn("dedupe", line)


if __name__ == "__main__":
    unittest.main()
