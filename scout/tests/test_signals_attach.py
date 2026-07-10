"""
test_signals_attach.py — the shared signal-feature producer (fba-feature-engineer, 2026-07-10).

The seam it guards: signals/attach.py used to live only in collect_hourly.py, so the
pipeline.run_once path scored the challenger with 18 of 28 features NaN AND wrote silver shadow
rows missing every signal field (day_of_week included — a per-path label-tier fingerprint).
"""
import datetime as dt
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pipeline  # noqa: E402
from signals import attach  # noqa: E402


class AttachSignalFeaturesTest(unittest.TestCase):
    def test_calendar_features_attach_to_a_bare_product(self):
        # Calendar features are pure date functions — they must attach even with trends/ebay
        # unavailable (both degrade non-fatally inside attach_signal_features).
        out = attach.attach_signal_features([{"asin": "A1", "price": 20.0, "category": "toys"}])
        self.assertIn("day_of_week", out[0])
        self.assertEqual(out[0]["day_of_week"], dt.date.today().weekday())

    def test_pipeline_run_once_attaches_signals_before_scoring(self):
        """The wiring seam: run_once must route enriched candidates through the SHARED producer
        (patched here) before _evaluate — proving the non-hourly path no longer scores with the
        signal fields missing."""
        attached = []

        def fake_attach(products):
            attached.extend(products)
            for p in products:
                p["day_of_week"] = 3
            return products

        with mock.patch.object(pipeline.config, "have_keepa", return_value=True), \
             mock.patch.object(pipeline.keepa_client, "get_client", return_value=object()), \
             mock.patch.object(pipeline, "_discover_candidates",
                               return_value={"asins": ["A1"], "hints_followed": 0,
                                             "hinted": {}, "brand_store": {}}), \
             mock.patch.object(pipeline.keepa_client, "enrich",
                               return_value=[{"asin": "A1", "price": 20.0, "category": "toys"}]), \
             mock.patch.object(pipeline.keepa_client, "token_telemetry", return_value={}), \
             mock.patch.object(pipeline.signals_attach, "attach_signal_features",
                               side_effect=fake_attach) as mattach, \
             mock.patch.object(pipeline.model_mod, "load_model", return_value=None), \
             mock.patch.object(pipeline.train_ranker, "load_challenger", return_value=None), \
             mock.patch.object(pipeline.db, "enabled", return_value=False):
            pipeline.run_once(retrain=False, post=False, dry_run=True)
        mattach.assert_called_once()
        self.assertEqual(attached[0]["asin"], "A1")


if __name__ == "__main__":
    unittest.main()
