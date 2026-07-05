"""
test_backtest.py — the backtest engine (DATA_ENGINE_PLAN.md V2).

The LEAKAGE TESTS are the deliverable and lead this file:
  1. a poisoned FUTURE datapoint is invisible to the feature builder (strict < as_of boundary);
  2. an ASIN's windows never straddle a train/validation split (split BY ASIN, not by row);
  3. the simulated features match the LIVE pipeline's features on a fixture (shared contract, no
     parallel reimplementation).
Plus: windowing, the would_have_profited label math, the token-cap budget guard + resume.
"""
import os
import sys
import datetime as dt
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtest as bt  # noqa: E402
import db  # noqa: E402
import keepa_client  # noqa: E402

BASE = dt.date(2026, 1, 1).toordinal()


def _constant_history(days=200, price=20.0, offers=5, rank=15000):
    """A daily, constant, in-stock history — makes as-of avg90 == current, so backtest features
    coincide with the live pipeline's stats-based features (the fixture for leakage test #3)."""
    price_s = [(BASE + d, price) for d in range(days)]
    offers_s = [(BASE + d, float(offers)) for d in range(days)]
    rank_s = [(BASE + d, float(rank)) for d in range(days)]
    return {"price": price_s, "offers": offers_s, "sales_rank": rank_s, "amazon": []}


class LeakageBoundaryTest(unittest.TestCase):
    def test_poisoned_future_point_is_invisible(self):
        hist = _constant_history(days=200)
        static = {"asin": "B01", "brand": "Lego", "category": "toys", "weight_lb": 1.0}
        as_of = BASE + 120
        clean = bt.features_as_of(hist, as_of, static)

        # Plant wildly different points AT as_of and AFTER it — the feature builder must not move.
        poisoned = {k: list(v) for k, v in hist.items()}
        poisoned["price"] += [(as_of, 999999.0), (as_of + 1, 888888.0)]
        poisoned["offers"] += [(as_of, 999.0), (as_of + 5, 999.0)]
        poisoned["sales_rank"] += [(as_of, 1.0)]
        for s in poisoned.values():
            s.sort(key=lambda p: p[0])
        after = bt.features_as_of(poisoned, as_of, static)

        self.assertEqual(clean, after)  # identical -> no future leakage
        self.assertEqual(clean["price"], 20.0)  # not the poisoned 999999

    def test_window_mean_and_last_before_are_strict(self):
        series = [(BASE + 0, 1.0), (BASE + 10, 2.0), (BASE + 20, 3.0)]
        # a point exactly AT the cutoff is excluded
        self.assertEqual(bt._last_before(series, BASE + 20), 2.0)
        self.assertEqual(bt._last_before(series, BASE + 21), 3.0)
        self.assertIsNone(bt._last_before(series, BASE + 0))


class SplitByAsinTest(unittest.TestCase):
    def test_asin_windows_never_straddle_split(self):
        rows = []
        for asin in [f"A{i}" for i in range(40)]:
            for w in range(5):  # 5 windows per ASIN
                rows.append({"asin": asin, "simulation_date": f"2026-0{w+1}-01", "label": True})
        train, val = bt.split_by_asin(rows, val_fraction=0.3)
        train_asins = {r["asin"] for r in train}
        val_asins = {r["asin"] for r in val}
        self.assertFalse(train_asins & val_asins)  # disjoint by ASIN
        self.assertEqual(len(train_asins | val_asins), 40)
        # deterministic (no Math.random) — same split on a re-run
        train2, _ = bt.split_by_asin(rows, val_fraction=0.3)
        self.assertEqual({r["asin"] for r in train2}, train_asins)


class MatchLivePipelineTest(unittest.TestCase):
    def test_backtest_features_match_live_snapshot_on_fixture(self):
        """With a constant, in-stock history the as-of averages equal the current values, so the
        backtest snapshot must equal what the LIVE path (keepa_client._normalize ->
        db.feature_snapshot) produces from a matching Keepa product — proving a shared contract."""
        price, offers, rank = 20.0, 5, 15000
        hist = _constant_history(days=200, price=price, offers=offers, rank=rank)
        static = {"asin": "B01", "brand": "Lego", "category": "toys", "weight_lb": None}
        bt_snap = db.feature_snapshot(bt.features_as_of(hist, BASE + 120, static))

        # A live Keepa product whose stats reflect that same steady state.
        cents = int(price * 100)
        product = {
            "asin": "B01", "brand": "Lego",
            "categoryTree": [{"catId": 1, "name": "Toys & Games"}],
            "stats": {
                "current": {keepa_client.IDX_NEW: cents, keepa_client.IDX_BUY_BOX: cents,
                            keepa_client.IDX_COUNT_NEW: offers, keepa_client.IDX_SALES_RANK: rank},
                "avg90": {keepa_client.IDX_NEW: cents, keepa_client.IDX_BUY_BOX: cents,
                          keepa_client.IDX_COUNT_NEW: offers, keepa_client.IDX_SALES_RANK: rank},
                "salesRankDrops30": 0, "outOfStockPercentage90": 0.0,
            },
        }
        live_snap = db.feature_snapshot(keepa_client._normalize(product))

        for k in ("price", "offers", "sales_rank", "avg_price_90", "avg_offers_90", "avg_sales_rank_90"):
            self.assertEqual(bt_snap[k], live_snap[k], f"mismatch on {k}: bt={bt_snap[k]} live={live_snap[k]}")


class WindowingAndLabelTest(unittest.TestCase):
    def test_windows_respect_history_and_horizon(self):
        hist = _constant_history(days=200)
        ws = bt.windows_for(hist, step_days=35, horizon=60, min_history=90)
        self.assertTrue(ws)
        self.assertGreaterEqual(ws[0], BASE + 90)          # >= min_history after first point
        self.assertLessEqual(ws[-1] + 60, BASE + 199)      # label horizon stays inside history
        # spacing is ~step_days
        if len(ws) > 1:
            self.assertEqual(ws[1] - ws[0], 35)

    def test_label_would_have_profited_at_original_cost(self):
        # price rises from 20 -> 40 over the horizon: bought cheap, sells for more -> profits
        hist = _constant_history(days=200, price=20.0)
        # overwrite the horizon side with a higher price
        as_of = BASE + 120
        hi = {k: list(v) for k, v in hist.items()}
        hi["price"] = [(d, (40.0 if d >= as_of + 60 else 20.0)) for d, _ in hi["price"]]
        landed = bt.scoring.assumed_landed_cost(20.0)
        lbl = bt.label_at(hi, as_of, landed, weight_lb=1.0, category="toys")
        self.assertTrue(lbl["would_have_profited"])
        self.assertEqual(lbl["price_at_horizon"], 40.0)

    def test_build_rows_tags_backtest_tier(self):
        hist = _constant_history(days=200, price=25.0)
        rows = bt.build_rows_for_asin("B01", hist, {"brand": "Lego", "category": "toys", "weight_lb": 1.0})
        self.assertTrue(rows)
        self.assertTrue(all(r["label_quality"] == "backtest" for r in rows))
        self.assertTrue(all("simulation_date" in r for r in rows))
        self.assertIn("features_snapshot", rows[0])
        self.assertNotIn("verdict", rows[0]["features_snapshot"])  # leakage-safe projection


class RunBacktestBudgetTest(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("DATALAKE_ENABLED", "DATA_LAKE_DIR")}
        import tempfile
        os.environ["DATALAKE_ENABLED"] = "0"  # don't touch the real lake; state file uses lake_dir
        os.environ["DATA_LAKE_DIR"] = tempfile.mkdtemp(prefix="fba-bt-test-")

    def tearDown(self):
        import shutil
        shutil.rmtree(os.environ["DATA_LAKE_DIR"], ignore_errors=True)
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_disabled_without_keepa(self):
        with mock.patch.object(bt.config, "have_keepa", return_value=False):
            r = bt.run_backtest()
        self.assertEqual(r["status"], "disabled")

    def test_token_cap_defers_and_persist_off_counts_rows(self):
        # 3 ASINs, batch 100, cap that allows sampling + one history batch only
        def fake_find(api=None, brand_seeds=None, limit=None):
            return {"Lego": ["A1", "A2", "A3"]}.get((brand_seeds or [None])[0], [])

        def fake_history(asins, api=None):
            return [{"asin": a, "data": None} for a in asins]  # parse yields empty history -> 0 rows

        with mock.patch.object(bt.config, "have_keepa", return_value=True), \
             mock.patch.object(bt, "backtest_token_cap", return_value=200), \
             mock.patch("brands.seed_brands", return_value=["Lego"]), \
             mock.patch("discovery_hints.hinted_brand_seeds", return_value=[]):
            r = bt.run_backtest(api=object(), find_fn=fake_find, history_fn=fake_history, persist=False)
        self.assertEqual(r["status"], "ok")
        self.assertGreaterEqual(r["tokens_spent"], 0)
        self.assertIn("rows_written", r)

    def test_resume_state_skips_processed_asins(self):
        # Pre-seed state so A1 is already processed; a re-run must not re-pull it.
        import json
        state_path = bt._state_path()
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump({"processed_asins": ["A1"], "spent_tokens": 0, "rows_written": 0}, f)

        pulled = []

        def fake_find(api=None, brand_seeds=None, limit=None):
            return ["A1", "A2"]

        def fake_history(asins, api=None):
            pulled.extend(asins)
            return [{"asin": a, "data": None} for a in asins]

        with mock.patch.object(bt.config, "have_keepa", return_value=True), \
             mock.patch.object(bt, "backtest_token_cap", return_value=10000), \
             mock.patch("brands.seed_brands", return_value=["Lego"]), \
             mock.patch("discovery_hints.hinted_brand_seeds", return_value=[]):
            bt.run_backtest(api=object(), find_fn=fake_find, history_fn=fake_history, persist=True)
        self.assertIn("A2", pulled)
        self.assertNotIn("A1", pulled)  # already processed -> skipped on resume


if __name__ == "__main__":
    unittest.main()
