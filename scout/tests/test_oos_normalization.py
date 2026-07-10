"""
test_oos_normalization.py — regression tests for the live shadow-scoring TypeError
(fba-ml-debugger, 2026-07-10, live-instrumented then locally reproduced).

Keepa's stats.outOfStockPercentage90 is a PER-PRICE-TYPE ARRAY (like current/avg90), but
_normalize passed it through raw for the field's whole life. Every rule-side consumer
isinstance-guards (so the oos>30 red flag silently NEVER fired on live products), and the one
unguarded consumer — challenger shadow scoring via vectorize_one — crashed with
"float() argument must be a string or a real number, not 'list'" on EVERY live candidate the
moment shadow loading was ungated, silently degrading every shadow score to None.
"""
import os
import sys
import math
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import keepa_client as kc  # noqa: E402
import db  # noqa: E402
import train_ranker as tr  # noqa: E402


class OosPctTest(unittest.TestCase):
    def test_array_extracts_new_price_type(self):
        # [AMAZON, NEW, USED, SALES_RANK] — NEW (idx 1) is the analog of backtest's
        # price-series availability fraction, keeping train/serve semantics aligned.
        self.assertEqual(kc._oos_pct([10, 25, -1, 0]), 25.0)

    def test_array_falls_back_to_amazon_when_new_missing(self):
        self.assertEqual(kc._oos_pct([10, -1]), 10.0)

    def test_keepa_minus_one_sentinel_is_none_not_zero(self):
        self.assertIsNone(kc._oos_pct([-1, -1]))  # missing != 0 (doctrine §4)
        self.assertIsNone(kc._oos_pct(-1))

    def test_scalar_passthrough_and_absent(self):
        self.assertEqual(kc._oos_pct(37), 37.0)  # already-correct form unchanged
        self.assertIsNone(kc._oos_pct(None))

    def test_normalize_produces_scalar_oos(self):
        raw = {"asin": "B0TEST", "title": "T", "brand": "X",
               "stats": {"current": [1999, 2099, -1, 5000],
                         "outOfStockPercentage90": [10, 25, -1, 0]},
               "categoryTree": [{"name": "Toys & Games", "catId": 165793011}]}
        self.assertEqual(kc._normalize(raw)["oos_90"], 25.0)


class VectorizeToleranceTest(unittest.TestCase):
    def test_list_valued_feature_degrades_to_nan_not_crash(self):
        feats = {"price": 20.0, "oos_90": [10, 25, -1, 0]}  # the exact live shape, pre-fix
        vec = tr.vectorize_one(feats)
        idx = tr.NUMERIC_FEATURES.index("oos_90")
        self.assertTrue(math.isnan(vec[idx]))  # one bad field costs one feature, not the vector
        self.assertEqual(vec[tr.NUMERIC_FEATURES.index("price")], 20.0)

    def test_bool_still_vectorizes_as_binary(self):
        feats = {"is_bts_window": True, "brand_trend_stale": False}
        vec = tr.vectorize_one(feats)
        self.assertEqual(vec[tr.NUMERIC_FEATURES.index("is_bts_window")], 1.0)
        self.assertEqual(vec[tr.NUMERIC_FEATURES.index("brand_trend_stale")], 0.0)

    def test_challenger_score_end_to_end_with_raw_shaped_product(self):
        """The full live path that failed: raw product -> _normalize -> feature_snapshot ->
        challenger_score must return a float, not degrade to None."""
        class _FakeModel:
            def predict_proba(self, X):
                import numpy as np
                self.seen = X
                return np.array([[0.2, 0.8]])  # real LGBMClassifier returns an ndarray

        raw = {"asin": "B0TEST", "title": "T", "brand": "X",
               "stats": {"current": [1999, 2099, -1, 5000],
                         "outOfStockPercentage90": [10, 25, -1, 0]},
               "categoryTree": [{"name": "Toys & Games", "catId": 165793011}]}
        feats = db.feature_snapshot(kc._normalize(raw))
        champion = {"model": _FakeModel(), "scaler": None, "features": list(tr.NUMERIC_FEATURES)}
        self.assertEqual(tr.challenger_score(champion, feats), 0.8)


if __name__ == "__main__":
    unittest.main()
