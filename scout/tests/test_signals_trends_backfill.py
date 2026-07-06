"""
test_signals_trends_backfill.py — the one-time 5-year Trends backfill (Session 55).

LEAKAGE TEST is the deliverable here too (same convention as test_backtest.py/test_signals_
trends.py): a poisoned point at/after a row's OWN simulation_date must never influence its
backfilled features. All Supabase/pytrends calls mocked or injected — no live network.
"""
import datetime as dt
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from signals import trends_backfill as tb  # noqa: E402


class BackfillVocabularyTest(unittest.TestCase):
    def test_per_term_isolation_one_failure_does_not_block_others(self):
        def fake_backfill_term(term, term_kind, client=None, sleep_fn=None):
            if term == "BadBrand":
                return {"term": term, "status": "failed", "rows_stored": 0}
            return {"term": term, "status": "ok", "rows_stored": 260}  # ~5yr weekly

        with mock.patch.object(tb.trends, "backfill_term", side_effect=fake_backfill_term):
            result = tb.backfill_vocabulary(
                vocabulary_fn=lambda: [("brand", "GoodBrand"), ("brand", "BadBrand")])
        self.assertEqual(result["terms_backfilled"], 1)
        self.assertEqual(result["terms_failed"], 1)
        self.assertEqual(result["failed_terms"], ["BadBrand"])
        self.assertEqual(result["rows_stored"], 260)


class BackfillRowFeaturesLeakageTest(unittest.TestCase):
    def test_poisoned_future_trend_point_is_invisible(self):
        row = {"asin": "B01", "simulation_date": "2025-06-15",
              "features_snapshot": {"brand": "Lego", "category": "toys", "price": 20.0}}
        as_of = dt.date(2025, 6, 15)
        clean_series = [(as_of - dt.timedelta(weeks=w), 40.0) for w in range(1, 20)]

        clean = tb.backfill_row_features(row, brand_series=clean_series, category_series=[])

        poisoned = clean_series + [(as_of, 9999.0), (as_of + dt.timedelta(days=3), 8888.0)]
        after = tb.backfill_row_features(row, brand_series=poisoned, category_series=[])

        self.assertEqual(clean["features_snapshot"]["brand_trend_ratio"],
                         after["features_snapshot"]["brand_trend_ratio"])

    def test_no_simulation_date_returns_none(self):
        self.assertIsNone(tb.backfill_row_features({"asin": "B02", "features_snapshot": {}}))

    def test_patches_calendar_features_at_simulation_date_not_today(self):
        row = {"asin": "B03", "simulation_date": "2026-06-24",
              "features_snapshot": {"brand": "Lego", "category": "toys"}}
        patched = tb.backfill_row_features(row, brand_series=[], category_series=[])
        # June 24, 2026 IS inside the configured Prime Day window -> days_to_prime_day <= 0
        snap = patched["features_snapshot"]
        self.assertIn("days_to_prime_day", snap)
        self.assertIn("day_of_week", snap)

    def test_original_row_fields_preserved(self):
        row = {"asin": "B04", "simulation_date": "2025-01-01", "would_have_profited": True,
              "est_profit": 12.5, "features_snapshot": {"brand": "Yeti", "category": "kitchen",
                                                        "price": 30.0}}
        patched = tb.backfill_row_features(row, brand_series=[], category_series=[])
        self.assertEqual(patched["would_have_profited"], True)
        self.assertEqual(patched["est_profit"], 12.5)
        self.assertEqual(patched["features_snapshot"]["price"], 30.0)  # untouched original field


class BackfillBacktestRowsTest(unittest.TestCase):
    def test_patches_and_reupserts_all_rows(self):
        rows = [
            {"asin": "B01", "simulation_date": "2025-01-01",
             "features_snapshot": {"brand": "Lego", "category": "toys"}},
            {"asin": "B02", "simulation_date": "2025-02-01",
             "features_snapshot": {"brand": "Lego", "category": "toys"}},
        ]
        with mock.patch.object(tb.db, "trends_series_for", return_value=[]) as mfetch, \
             mock.patch.object(tb.db, "upsert_backtest_rows", return_value=2) as mwrite:
            result = tb.backfill_backtest_rows(rows=rows)
        self.assertEqual(result["rows_read"], 2)
        self.assertEqual(result["rows_patched"], 2)
        self.assertEqual(result["rows_skipped"], 0)
        # both rows share brand "Lego"/category "toys" -> only 2 distinct terms fetched, not 4
        self.assertEqual(mfetch.call_count, 2)
        self.assertTrue(mwrite.called)

    def test_skips_rows_without_simulation_date_honestly(self):
        rows = [{"asin": "B01", "features_snapshot": {}}]
        with mock.patch.object(tb.db, "trends_series_for", return_value=[]), \
             mock.patch.object(tb.db, "upsert_backtest_rows", return_value=0):
            result = tb.backfill_backtest_rows(rows=rows)
        self.assertEqual(result["rows_skipped"], 1)
        self.assertEqual(result["rows_patched"], 0)

    def test_empty_corpus_is_a_clean_noop(self):
        with mock.patch.object(tb.db, "all_backtest_rows_for_backfill", return_value=[]):
            result = tb.backfill_backtest_rows()
        self.assertEqual(result["rows_read"], 0)


if __name__ == "__main__":
    unittest.main()
