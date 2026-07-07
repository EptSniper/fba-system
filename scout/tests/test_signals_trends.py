"""
test_signals_trends.py — scout/signals/trends.py (Session 55, free signal-type features).

All pytrends/Supabase calls are mocked/injected — no live network, no real pytrends install
required for these tests to run (a FakeClient stands in; DataFrame conversion is tested against
a REAL small pandas DataFrame, since pandas is already a project dependency via scikit-learn).
"""
import datetime as dt
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from signals import trends  # noqa: E402
import db  # noqa: E402


class DataFrameConversionTest(unittest.TestCase):
    def test_converts_and_drops_partial_week(self):
        import pandas as pd
        idx = pd.to_datetime(["2026-01-05", "2026-01-12", "2026-01-19"])
        df = pd.DataFrame({"Lego": [40, 55, 62], "isPartial": [False, False, True]}, index=idx)
        series = trends._dataframe_to_weekly_series(df, "Lego")
        self.assertEqual(series, [(dt.date(2026, 1, 5), 40.0), (dt.date(2026, 1, 12), 55.0)])


class FakeTrendsClient:
    """A pytrends.TrendReq stand-in: build_payload() may raise N times before succeeding
    (simulating a rate limit), interest_over_time() returns a preset DataFrame."""
    def __init__(self, fail_times=0, df=None, raise_always=False):
        self.fail_times = fail_times
        self.calls = 0
        self.df = df
        self.raise_always = raise_always

    def build_payload(self, kw_list, timeframe=None):
        self.calls += 1
        if self.raise_always or self.calls <= self.fail_times:
            raise RuntimeError("429 rate limited")

    def interest_over_time(self):
        return self.df


def _df(term, dates, values, partial_last=False):
    import pandas as pd
    idx = pd.to_datetime(dates)
    partials = [False] * len(values)
    if partial_last:
        partials[-1] = True
    return pd.DataFrame({term: values, "isPartial": partials}, index=idx)


class FetchWeeklyInterestTest(unittest.TestCase):
    def test_succeeds_on_first_try(self):
        client = FakeTrendsClient(df=_df("Lego", ["2026-01-05"], [40]))
        series = trends.fetch_weekly_interest(client, "Lego", sleep_fn=lambda s: None)
        self.assertEqual(series, [(dt.date(2026, 1, 5), 40.0)])
        self.assertEqual(client.calls, 1)

    def test_retries_with_backoff_then_succeeds(self):
        sleeps = []
        client = FakeTrendsClient(fail_times=2, df=_df("Lego", ["2026-01-05"], [40]))
        series = trends.fetch_weekly_interest(client, "Lego", max_retries=3,
                                              sleep_fn=lambda s: sleeps.append(s))
        self.assertIsNotNone(series)
        self.assertEqual(len(sleeps), 2)  # slept before attempt 2 and attempt 3
        self.assertTrue(all(s >= trends.BASE_BACKOFF_SECONDS for s in sleeps))
        # exponential: second sleep's floor must exceed the first's floor (before jitter)
        self.assertGreater(sleeps[1], trends.BASE_BACKOFF_SECONDS)

    def test_returns_none_after_exhausting_retries(self):
        client = FakeTrendsClient(raise_always=True)
        series = trends.fetch_weekly_interest(client, "Lego", max_retries=3, sleep_fn=lambda s: None)
        self.assertIsNone(series)

    def test_empty_dataframe_returns_empty_list_not_none(self):
        import pandas as pd
        client = FakeTrendsClient(df=pd.DataFrame())
        series = trends.fetch_weekly_interest(client, "Lego", sleep_fn=lambda s: None)
        self.assertEqual(series, [])


class VocabularyTest(unittest.TestCase):
    def test_combines_categories_and_brands(self):
        with mock.patch.object(trends, "sampling_config", return_value={"categories": ["toys", "kitchen"]}), \
             mock.patch.object(db, "recent_brand_vocabulary", return_value=["Lego", "Yeti"]):
            vocab = trends.vocabulary()
        self.assertEqual(vocab, [("category", "toys"), ("category", "kitchen"),
                                ("brand", "Lego"), ("brand", "Yeti")])


class CollectWeeklyTest(unittest.TestCase):
    def test_one_failing_term_does_not_block_the_rest(self):
        def fake_fetch(client, term, sleep_fn=None, **kw):
            if term == "BadBrand":
                return None
            return [(dt.date(2026, 1, 5), 42.0)]

        with mock.patch.object(trends, "fetch_weekly_interest", side_effect=fake_fetch), \
             mock.patch.object(db, "upsert_trends_series", return_value=1) as mock_upsert:
            result = trends.collect_weekly(
                terms=[("brand", "GoodBrand"), ("brand", "BadBrand")], client=object())
        self.assertEqual(result["fetched"], ["GoodBrand"])
        self.assertEqual(result["failed"], ["BadBrand"])
        self.assertTrue(mock_upsert.called)
        stored_rows = mock_upsert.call_args[0][0]
        self.assertEqual(len(stored_rows), 1)
        self.assertEqual(stored_rows[0]["term"], "GoodBrand")

    def test_disabled_when_client_construction_fails(self):
        with mock.patch.object(trends, "get_client", side_effect=ImportError("no pytrends")):
            result = trends.collect_weekly(terms=[("brand", "X")], client=None)
        self.assertEqual(result["status"], "disabled")


class BackfillTermTest(unittest.TestCase):
    def test_stores_full_series(self):
        series = [(dt.date(2021, 1, 4), 10.0), (dt.date(2021, 1, 11), 12.0)]
        with mock.patch.object(trends, "fetch_weekly_interest", return_value=series), \
             mock.patch.object(db, "upsert_trends_series", return_value=2) as mock_upsert:
            result = trends.backfill_term("Lego", "brand", client=object())
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["weeks"], 2)
        self.assertTrue(mock_upsert.called)

    def test_failed_fetch_reports_status_failed(self):
        with mock.patch.object(trends, "fetch_weekly_interest", return_value=None):
            result = trends.backfill_term("Lego", "brand", client=object())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["rows_stored"], 0)


class TrendsFeaturesLeakageTest(unittest.TestCase):
    """Mirrors test_backtest.py's LeakageBoundaryTest: a poisoned point AT or AFTER as_of must
    never influence the computed features."""

    def test_poisoned_future_point_is_invisible(self):
        clean_series = [(dt.date(2026, 1, 5) + dt.timedelta(weeks=w), 50.0) for w in range(20)]
        as_of = dt.date(2026, 1, 5) + dt.timedelta(weeks=15)
        clean = trends.trends_features("Lego", as_of, series=clean_series)

        poisoned = list(clean_series) + [(as_of, 9999.0), (as_of + dt.timedelta(days=1), 8888.0)]
        after = trends.trends_features("Lego", as_of, series=poisoned)
        self.assertEqual(clean, after)

    def test_at_as_of_exactly_is_excluded(self):
        series = [(dt.date(2026, 1, 5), 10.0), (dt.date(2026, 1, 12), 9999.0)]
        feats = trends.trends_features("Lego", dt.date(2026, 1, 12), series=series)
        # the point AT as_of (Jan 12) must be excluded; only Jan 5 (10.0) is visible
        self.assertEqual(feats["interest_now_vs_90d_avg"], 1.0)  # 10/10

    def test_week_boundary_leakage_mid_week_as_of_excludes_the_still_open_week(self):
        """Review fix (2026-07-06): a Trends weekly point aggregates search interest over the
        WHOLE week [week_start, week_start+6] — not a single day. The bucket for the week
        starting Monday Nov 23, 2026 (a real Black Friday week) aggregates through Nov 29; an
        as_of of Wednesday Nov 25 falls MID-WEEK, so that bucket's own aggregation window still
        extends 4 days PAST as_of even though its week_start (Nov 23) is strictly before as_of.
        The OLD `d < as_of` boundary would have let this still-accumulating, partially-future
        bucket leak straight into the feature; the fix must exclude it entirely."""
        clean_prior_week = dt.date(2026, 11, 16)     # fully closed before as_of — must be visible
        still_open_week = dt.date(2026, 11, 23)       # Black Friday week — must be EXCLUDED
        as_of = dt.date(2026, 11, 25)                 # Wednesday, mid-week of still_open_week

        series = [(clean_prior_week, 20.0), (still_open_week, 999.0)]
        feats = trends.trends_features("Lego", as_of, series=series)

        # If the Black-Friday-week point leaked in, avg90 would blend 20 and 999 and the ratio
        # would land well above 1.0 (and likely trip spike_flag) — it must not.
        self.assertEqual(feats["interest_now_vs_90d_avg"], 1.0)  # 20 / 20, undiluted
        self.assertFalse(feats["spike_flag"])

    def test_week_boundary_leakage_closes_exactly_seven_days_later(self):
        """The boundary is inclusive of a FULLY closed week: a week_start exactly
        WEEK_LENGTH_DAYS before as_of has finished accumulating and must be visible."""
        week_start = dt.date(2026, 11, 23)
        as_of = week_start + dt.timedelta(days=trends.WEEK_LENGTH_DAYS)  # Nov 30 — fully closed
        feats = trends.trends_features("Lego", as_of, series=[(week_start, 42.0)])
        self.assertEqual(feats["interest_now_vs_90d_avg"], 1.0)
        self.assertFalse(feats["stale"])


class TrendsFeaturesMathTest(unittest.TestCase):
    def test_no_data_returns_stale_none(self):
        feats = trends.trends_features("Lego", dt.date(2026, 6, 1), series=[])
        self.assertTrue(feats["stale"])
        self.assertIsNone(feats["interest_now_vs_90d_avg"])

    def test_stale_flag_when_last_point_too_old(self):
        series = [(dt.date(2026, 1, 1), 50.0)]
        feats = trends.trends_features("Lego", dt.date(2026, 6, 1), series=series)
        self.assertTrue(feats["stale"])
        self.assertIsNotNone(feats["interest_now_vs_90d_avg"])  # still returns last-known value

    def test_not_stale_when_recent(self):
        as_of = dt.date(2026, 6, 10)
        # week_start 12 days back -> its bucket closed 5 days ago (12 - WEEK_LENGTH_DAYS) —
        # fully closed under the leakage-safe boundary AND within STALE_AFTER_DAYS (14).
        series = [(as_of - dt.timedelta(days=12), 50.0)]
        feats = trends.trends_features("Lego", as_of, series=series)
        self.assertFalse(feats["stale"])

    def test_spike_flag_true_above_2x_90d_avg(self):
        base = dt.date(2026, 1, 5)
        series = [(base + dt.timedelta(weeks=w), 20.0) for w in range(12)]
        series.append((base + dt.timedelta(weeks=12), 50.0))  # a spike week
        as_of = base + dt.timedelta(weeks=13)
        feats = trends.trends_features("Lego", as_of, series=series)
        self.assertTrue(feats["spike_flag"])
        self.assertGreater(feats["interest_now_vs_90d_avg"], 2.0)

    def test_slope_4wk_reflects_upward_trend(self):
        base = dt.date(2026, 1, 5)
        series = [(base + dt.timedelta(weeks=w), 10.0 * (w + 1)) for w in range(4)]
        as_of = base + dt.timedelta(weeks=4)
        feats = trends.trends_features("Lego", as_of, series=series)
        self.assertEqual(feats["slope_4wk"], 10.0)

    def test_seasonal_z_uses_same_iso_week_prior_years(self):
        # 3 years of the SAME week number, with year 3 (the most recent, "latest") a clear outlier
        series = [
            (dt.date(2023, 6, 15), 20.0),  # iso week ~24
            (dt.date(2024, 6, 13), 22.0),  # same iso week, next year
            (dt.date(2025, 6, 12), 90.0),  # same iso week, this is the "latest" point
        ]
        as_of = dt.date(2025, 6, 19)
        feats = trends.trends_features("Lego", as_of, series=series)
        self.assertIsNotNone(feats["seasonal_z"])
        self.assertGreater(feats["seasonal_z"], 0)  # 90 is well above the ~21 historical mean


class MainEntryPointTest(unittest.TestCase):
    """Review fix (2026-07-06): collect_weekly() had NO scheduled caller anywhere in the
    codebase — .github/workflows/trends-collect.yml now invokes this weekly via
    `python3 -m signals.trends`."""

    def test_main_calls_collect_weekly_and_exits_zero(self):
        with mock.patch.object(trends, "collect_weekly",
                               return_value={"status": "ok", "fetched": ["Lego"], "failed": [],
                                            "rows_stored": 5}) as mock_collect:
            rc = trends.main()
        mock_collect.assert_called_once()
        self.assertEqual(rc, 0)

    def test_main_exits_zero_even_when_disabled(self):
        """'disabled' (pytrends/env unavailable) is an honest no-op, not a CI failure — same
        convention as collect_hourly.main()'s 'no KEEPA_KEY' case."""
        with mock.patch.object(trends, "collect_weekly",
                               return_value={"status": "disabled", "reason": "no pytrends"}):
            rc = trends.main()
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
