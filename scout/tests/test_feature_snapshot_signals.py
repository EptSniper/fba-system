"""
test_feature_snapshot_signals.py — Session 55's free signal-type features wired into
db.PRE_DECISION_FEATURES / db.feature_snapshot(). Confirms the new fields round-trip through the
exact JSON-serialization path a real Supabase JSONB write/read would use (a date object or other
non-JSON-safe value slipping into a snapshot would silently break every future read of that row).
"""
import datetime as dt
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402
from signals import calendar as signals_calendar  # noqa: E402


class NewSignalFieldsPresentTest(unittest.TestCase):
    EXPECTED_NEW_FIELDS = (
        "upc",
        "days_to_prime_day", "weeks_to_q4_arrival_deadline", "days_to_nearest_major_holiday",
        "nearest_major_holiday_name", "is_bts_window", "day_of_week",
        "brand_trend_ratio", "brand_trend_slope", "brand_trend_seasonal_z", "brand_trend_spike",
        "brand_trend_stale",
        "category_trend_ratio", "category_trend_slope", "category_trend_seasonal_z",
        "category_trend_spike", "category_trend_stale",
        "ebay_active_listing_count", "median_active_price_vs_amazon_ratio", "ebay_stale",
    )

    def test_all_new_fields_are_in_pre_decision_features(self):
        missing = [f for f in self.EXPECTED_NEW_FIELDS if f not in db.PRE_DECISION_FEATURES]
        self.assertEqual(missing, [], f"missing from PRE_DECISION_FEATURES: {missing}")

    def test_original_fields_still_present(self):
        """The Session 55 additions must be ADDITIVE — none of the original fields dropped."""
        original = ("asin", "price", "weight_lb", "sales_rank", "est_sales", "offers", "brand",
                   "category", "avg_price_90", "avg_offers_90", "avg_sales_rank_90", "oos_90",
                   "buybox_seller", "amazon_bb_share")
        missing = [f for f in original if f not in db.PRE_DECISION_FEATURES]
        self.assertEqual(missing, [])


class FeatureSnapshotRoundTripTest(unittest.TestCase):
    def _full_product(self) -> dict:
        p = {k: None for k in db.PRE_DECISION_FEATURES}
        p.update({
            "asin": "B0TEST123", "price": 20.0, "weight_lb": 1.2, "sales_rank": 15000,
            "est_sales": 40, "offers": 6, "brand": "Lego", "category": "toys",
            "avg_price_90": 19.5, "avg_offers_90": 5, "avg_sales_rank_90": 14000, "oos_90": 2.0,
            "buybox_seller": "AMAZON", "amazon_bb_share": 0.1,
            "upc": "012345678905",
            "days_to_prime_day": 22, "weeks_to_q4_arrival_deadline": 12.0,
            "days_to_nearest_major_holiday": 5, "nearest_major_holiday_name": "Thanksgiving",
            "is_bts_window": True, "day_of_week": 2,
            "brand_trend_ratio": 1.4, "brand_trend_slope": 0.3, "brand_trend_seasonal_z": 0.8,
            "brand_trend_spike": False, "brand_trend_stale": False,
            "category_trend_ratio": 0.9, "category_trend_slope": -0.1, "category_trend_seasonal_z": -0.2,
            "category_trend_spike": False, "category_trend_stale": True,
            "ebay_active_listing_count": 12, "median_active_price_vs_amazon_ratio": 0.85, "ebay_stale": False,
        })
        return p

    def test_snapshot_carries_every_new_field(self):
        snap = db.feature_snapshot(self._full_product())
        for field in NewSignalFieldsPresentTest.EXPECTED_NEW_FIELDS:
            self.assertIn(field, snap)
        self.assertEqual(snap["nearest_major_holiday_name"], "Thanksgiving")
        self.assertTrue(snap["is_bts_window"])

    def test_snapshot_is_json_round_trip_safe(self):
        """Every value a real Supabase JSONB write would receive must survive json.dumps/loads
        byte-identical — a date/Decimal/other non-primitive here would silently corrupt storage."""
        snap = db.feature_snapshot(self._full_product())
        round_tripped = json.loads(json.dumps(snap))
        self.assertEqual(snap, round_tripped)

    def test_calendar_features_output_is_json_safe(self):
        """calendar_features() returns primitives only — a stray datetime.date would fail
        json.dumps outright, catching the mistake here instead of at a live Supabase write."""
        feats = signals_calendar.calendar_features(dt.date(2026, 6, 1))
        json.dumps(feats)  # raises TypeError if anything non-serializable slipped in

    def test_none_snapshot_still_excludes_post_decision_fields(self):
        """Even with the expanded field list, the leakage allowlist projection must still refuse
        anything not in PRE_DECISION_FEATURES."""
        leaky = dict(self._full_product(), verdict="review", blended_score=95.0)
        snap = db.feature_snapshot(leaky)
        self.assertNotIn("verdict", snap)
        self.assertNotIn("blended_score", snap)


if __name__ == "__main__":
    unittest.main()
