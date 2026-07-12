"""
test_backtest.py — the backtest engine (DATA_ENGINE_PLAN.md V2).

The LEAKAGE TESTS are the deliverable and lead this file:
  1. a poisoned FUTURE datapoint is invisible to the feature builder (strict < as_of boundary);
  2. an ASIN's windows never straddle a train/validation split (split BY ASIN, not by row);
  3. the simulated features match the LIVE pipeline's features on a fixture (shared contract, no
     parallel reimplementation).
Plus: windowing, the would_have_profited label math, the token-cap budget guard + resume.
"""
import json
import os
import sys
import datetime as dt
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtest as bt  # noqa: E402
import db  # noqa: E402
import deals_firehose  # noqa: E402
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

    # ML leakage audit (2026-07-09, fba-leakage-auditor): test_poisoned_future_point_is_invisible
    # above already proves the WHOLE feature_as_of() pipeline is leakage-safe, but only exercises
    # _window_mean indirectly (avg_price_90/avg_offers_90/etc.) and never exercises
    # _oos_fraction/_rank_drops at all (the constant fixture has no out-of-stock gaps or rank
    # drops for either to compute over). These inject a spike strictly AFTER as_of directly into
    # each function and assert the returned value is byte-identical to the unpoisoned run.

    def test_window_mean_poisoned_future_is_invisible(self):
        series = [(BASE + d, 10.0) for d in range(90)]
        as_of = BASE + 90
        clean = bt._window_mean(series, as_of, 90)
        poisoned = series + [(as_of, 999999.0), (as_of + 5, 888888.0)]
        self.assertEqual(bt._window_mean(poisoned, as_of, 90), clean)
        self.assertEqual(clean, 10.0)

    def test_oos_fraction_poisoned_future_is_invisible(self):
        # Alternating in-stock/out-of-stock (None) before as_of -> a known non-trivial baseline.
        series = [(BASE + d, None if d % 2 == 0 else 10.0) for d in range(90)]
        as_of = BASE + 90
        clean = bt._oos_fraction(series, as_of, 90)
        self.assertGreater(clean, 0.0)
        # Inject future IN-STOCK points -- if they leaked in, they'd DILUTE (lower) the oos
        # fraction, so this specifically catches a future point silently entering the window.
        poisoned = series + [(as_of, 10.0), (as_of + 1, 10.0), (as_of + 2, 10.0)]
        self.assertEqual(bt._oos_fraction(poisoned, as_of, 90), clean)

    def test_rank_drops_poisoned_future_is_invisible(self):
        series = [(BASE + 0, 100.0), (BASE + 5, 50.0), (BASE + 10, 60.0), (BASE + 15, 20.0)]
        as_of = BASE + 20
        clean = bt._rank_drops(series, as_of, 30)
        self.assertEqual(clean, 2)  # 100->50 and 60->20
        poisoned = series + [(as_of, 5.0), (as_of + 1, 1.0), (as_of + 2, 0.5)]
        self.assertEqual(bt._rank_drops(poisoned, as_of, 30), clean)


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


class SplitByTimeTest(unittest.TestCase):
    """The promotion-gate time-held-out split (ML de-bias audit, 2026-07-09): split_by_asin is a
    same-time GROUP split (prevents an ASIN's windows straddling train/val) but was never
    time-based — ml-doctrine.md §4 flags this as a tracked gap. split_by_time tests forward
    generalization instead: does the model trained on the past predict the FUTURE."""

    def test_val_is_the_chronologically_latest_slice(self):
        rows = [{"asin": f"A{i}", "simulation_date": f"2026-01-{i+1:02d}", "label": True}
               for i in range(20)]
        train, val = bt.split_by_time(rows, val_fraction=0.3)
        self.assertEqual(len(val), 6)  # round(20*0.3)
        self.assertEqual(len(train), 14)
        # every val date must be later than every train date -- no future-in-train leakage
        self.assertLess(max(r["simulation_date"] for r in train),
                        min(r["simulation_date"] for r in val))

    def test_same_asin_may_straddle_the_split_by_design(self):
        """Unlike split_by_asin, an ASIN's earlier window in train + later window in val is the
        INTENDED forward-prediction scenario here, not leakage."""
        rows = [{"asin": "A1", "simulation_date": "2026-01-01", "label": True},
               {"asin": "A1", "simulation_date": "2026-06-01", "label": True}]
        train, val = bt.split_by_time(rows, val_fraction=0.5)
        self.assertEqual(train[0]["simulation_date"], "2026-01-01")
        self.assertEqual(val[0]["simulation_date"], "2026-06-01")

    def test_deterministic_no_random(self):
        rows = [{"asin": f"A{i}", "simulation_date": f"2026-01-{i+1:02d}", "label": True}
               for i in range(10)]
        train1, val1 = bt.split_by_time(rows)
        train2, val2 = bt.split_by_time(rows)
        self.assertEqual(train1, train2)
        self.assertEqual(val1, val2)

    def test_empty_and_tiny_inputs_degrade_safely(self):
        self.assertEqual(bt.split_by_time([]), ([], []))
        one = [{"asin": "A1", "simulation_date": "2026-01-01", "label": True}]
        train, val = bt.split_by_time(one, val_fraction=0.3)
        self.assertEqual(train, [])
        self.assertEqual(val, one)  # a single row can't be split further -> it's the val side


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

    def test_label_uses_price_in_effect_not_a_far_future_change(self):
        """ML audit fix (2026-07-09): the label used to be the FIRST price change at ANY day
        >= horizon, unbounded — a stable product whose next change lands months later got that
        far-future price attributed to 'day 60'. Keepa series are change-point encoded, so the
        correct day-60 value is the last observation carried forward."""
        as_of = BASE + 120
        # Price 20 until day+59, then NO point at the horizon; next change is +90 at 99.0 —
        # under the old first-change-after logic the label price would be 99.0.
        price = [(BASE + d, 20.0) for d in range(180)] + [(as_of + 90, 99.0)]
        hist = {"price": sorted(price), "offers": [], "sales_rank": [], "amazon": []}
        lbl = bt.label_at(hist, as_of, landed_cost=10.0, weight_lb=1.0, category="toys")
        self.assertEqual(lbl["price_at_horizon"], 20.0)  # the value IN EFFECT at +60, not 99.0
        self.assertFalse(lbl["censored"])

    def test_label_censors_out_of_stock_at_horizon(self):
        """OOS in effect AT the horizon = no sale price to label with — and OOS-at-horizon
        products are disproportionately losers, so borrowing their next in-stock price inflated
        the positive rate. Must censor (would=None), never fabricate."""
        as_of = BASE + 120
        price = ([(BASE + d, 20.0) for d in range(150)]
                + [(as_of + 40, None), (as_of + 80, 35.0)])  # OOS from +40; back in stock +80
        hist = {"price": sorted(price, key=lambda p: p[0]), "offers": [], "sales_rank": [], "amazon": []}
        lbl = bt.label_at(hist, as_of, landed_cost=10.0, weight_lb=1.0, category="toys")
        self.assertIsNone(lbl["would_have_profited"])
        self.assertTrue(lbl["censored"])

    def test_label_censors_when_tracking_stopped_before_horizon(self):
        """Tracking that stops > LABEL_TRACKING_TOLERANCE_DAYS before the horizon (delisted /
        untracked) means the carried-forward value is no longer evidence — censor honestly."""
        as_of = BASE + 120
        # Last point of any kind lands 45 days before the +60 horizon (tolerance is 30).
        price = [(BASE + d, 20.0) for d in range(0, (as_of - BASE) + 15)]
        hist = {"price": price, "offers": [], "sales_rank": [], "amazon": []}
        lbl = bt.label_at(hist, as_of, landed_cost=10.0, weight_lb=1.0, category="toys")
        self.assertTrue(lbl["censored"])
        self.assertIsNone(lbl["would_have_profited"])


    def test_build_rows_tags_backtest_tier(self):
        hist = _constant_history(days=200, price=25.0)
        rows = bt.build_rows_for_asin("B01", hist, {"brand": "Lego", "category": "toys", "weight_lb": 1.0})
        self.assertTrue(rows)
        self.assertTrue(all(r["label_quality"] == "backtest" for r in rows))
        self.assertTrue(all("simulation_date" in r for r in rows))
        self.assertIn("features_snapshot", rows[0])
        self.assertNotIn("verdict", rows[0]["features_snapshot"])  # leakage-safe projection


class SamplerBudgetPreCheckTest(unittest.TestCase):
    """ML audit fix (2026-07-09): both samplers used to check `spent >= budget` AFTER the
    ~10-token spend — a 1-9 token leftover budget still bought one full search term, silently
    eating the history-loop reserve the SAMPLE_TOKEN_RESERVE_FRACTION guarantee exists for."""

    def test_explore_attempts_zero_terms_when_budget_below_term_cost(self):
        calls = []

        def fake_find(api=None, brand_seeds=None, limit=None):
            calls.append(brand_seeds)
            return ["A1"]

        with mock.patch.object(bt, "_fetch_remote_explore_cursor", return_value=0), \
             mock.patch.object(bt, "_upload_remote_explore_cursor", return_value=False):
            out, spent = bt.sample_asins_explore(object(), budget_tokens=3,
                                                categories=["toys", "pet"], find_fn=fake_find)
        self.assertEqual(calls, [])   # a 3-token budget can't afford a 10-token term
        self.assertEqual(spent, 0)
        self.assertEqual(out, [])

    def test_on_policy_attempts_zero_terms_when_budget_below_term_cost(self):
        calls = []

        def fake_find(api=None, brand_seeds=None, limit=None):
            calls.append(brand_seeds)
            return ["A1"]

        with mock.patch("brands.seed_brands", return_value=["Lego", "Yeti"]), \
             mock.patch("discovery_hints.hinted_brand_seeds", return_value=[]):
            out, spent = bt.sample_asins_on_policy(object(), budget_tokens=9, find_fn=fake_find)
        self.assertEqual(calls, [])
        self.assertEqual(spent, 0)

    def test_budget_exactly_one_term_attempts_exactly_one(self):
        calls = []

        def fake_find(api=None, brand_seeds=None, limit=None):
            calls.append(list(brand_seeds))
            return ["A1"]

        with mock.patch.object(bt, "_fetch_remote_explore_cursor", return_value=0), \
             mock.patch.object(bt, "_upload_remote_explore_cursor", return_value=False):
            bt.sample_asins_explore(object(), budget_tokens=10,
                                   categories=["toys", "pet"], find_fn=fake_find)
        self.assertEqual(len(calls), 1)  # affords one 10-token term, not two



class RunBacktestBudgetTest(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("DATALAKE_ENABLED", "DATA_LAKE_DIR")}
        import tempfile
        os.environ["DATALAKE_ENABLED"] = "0"  # don't touch the real lake; state file uses lake_dir
        os.environ["DATA_LAKE_DIR"] = tempfile.mkdtemp(prefix="fba-bt-test-")
        # Review fix (2026-07-07): _load_state()/_save_state() now fall back to a real Supabase
        # Storage read/write when the local state file is empty (the whole point of that fix —
        # GitHub Actions has no persistent disk). Without isolating this too, these tests would
        # silently read REAL cross-run production state (contaminating tokens_spent/
        # asins_processed assertions with leftover live data) and could even write test fixture
        # ASINs to the real bucket. Same isolation principle as the DATA_LAKE_DIR redirect above.
        # Same isolation for the explore rotation cursor (2026-07-09) -- a separate persisted
        # blob (see sample_asins_explore()'s docstring for why it's not folded into state above).
        self._remote_patchers = [
            mock.patch.object(bt, "_fetch_remote_state", return_value={}),
            mock.patch.object(bt, "_upload_remote_state", return_value=False),
            mock.patch.object(bt, "_fetch_remote_explore_cursor", return_value=0),
            mock.patch.object(bt, "_upload_remote_explore_cursor", return_value=False),
            # Keepa throughput plan Action D (2026-07-11): sample_asins_storefront() reads this
            # module's seller pool/cursor via deals_firehose directly (not through `bt`) — same
            # isolation rationale as the cursors above. Empty pool = safe no-op (storefront
            # contributes nothing) unless a specific test overrides it.
            mock.patch.object(deals_firehose, "_fetch_remote_seller_pool", return_value=[]),
            mock.patch.object(deals_firehose, "_fetch_remote_seller_cursor", return_value=0),
            mock.patch.object(deals_firehose, "_upload_remote_seller_cursor", return_value=False),
        ]
        for p in self._remote_patchers:
            p.start()

    def tearDown(self):
        import shutil
        shutil.rmtree(os.environ["DATA_LAKE_DIR"], ignore_errors=True)
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        for p in self._remote_patchers:
            p.stop()

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

    def test_large_persisted_lifetime_spend_does_not_permanently_zero_a_small_cap(self):
        """Review fix (2026-07-08, live incident): before this fix, run_backtest() compared a
        PERSISTED CUMULATIVE spend against THIS RUN's own small token_cap (e.g. 15, the typical
        hourly-burst tier-3 reserve) via a single `spent` variable loaded straight from state.
        That was harmless only because the state file never survived across GitHub Actions runs
        (fixed separately, 2026-07-08) -- once persistence genuinely started working, a lifetime
        total that only grows (e.g. 111, from real prior runs) permanently zeroed
        `max(0, cap - spent)` on every future call, forever, regardless of how small `cap` itself
        was. LIVE-CONFIRMED against a real run: token_cap=15, persisted spent=111 ->
        sample_asins_stratified got budget_tokens=0 -> asins_sampled=0 forever after. This test
        pre-seeds a lifetime spend far exceeding the explicit token_cap and asserts sampling and
        processing still happen — proving the per-run budget check uses only THIS invocation's
        own fresh spend, not the persisted lifetime counter."""
        import json
        state_path = bt._state_path()
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump({"processed_asins": [], "spent_tokens": 500, "rows_written": 0}, f)

        pulled = []

        def fake_find(api=None, brand_seeds=None, limit=None):
            return {"Lego": ["A1", "A2"]}.get((brand_seeds or [None])[0], [])

        def fake_history(asins, api=None):
            pulled.extend(asins)
            return [{"asin": a, "data": None} for a in asins]

        # dealfeed/explore stubbed to (0, 0) so this test isolates the cap-vs-lifetime-spend fix
        # from explore's own budget sizing (not what's under test here). token_cap=25: sampling
        # gets 25 - int(25*0.5) = 13, which affords exactly one 10-token search term under the
        # 2026-07-09 pre-check fix (spent + SEARCH_TOKENS_PER_TERM must FIT the budget BEFORE
        # the call — the old 15-token fixture left sampling only 8, honestly unaffordable now).
        with mock.patch.object(bt.config, "have_keepa", return_value=True), \
             mock.patch.object(bt, "backtest_token_cap", return_value=200), \
             mock.patch.object(bt, "sample_asins_explore", return_value=([], 0)), \
             mock.patch("brands.seed_brands", return_value=["Lego"]), \
             mock.patch("discovery_hints.hinted_brand_seeds", return_value=[]):
            r = bt.run_backtest(api=object(), token_cap=25, find_fn=fake_find,
                               history_fn=fake_history, persist=True)

        self.assertGreater(r["asins_sampled"], 0, "sampling must not be gated by lifetime spend")
        self.assertTrue(pulled, "history-pull loop must still run despite a large lifetime spend")
        # tokens_spent in the returned summary is THIS RUN's spend, not the 500 already persisted.
        self.assertLess(r["tokens_spent"], 500)

    def test_sampling_is_capped_to_leave_room_for_the_history_pull_loop(self):
        """Review fix (2026-07-08, live incident, run 192): sample_asins_stratified() used to get
        the run's ENTIRE token_cap as its ceiling -- dealfeed alone (capped at up to 4 deal pages
        regardless of how big the ceiling is) could spend the whole cap and then some, leaving
        the history-pull loop below with zero headroom. LIVE-CONFIRMED: cap=39, sample_spent=41,
        rows_written=0 despite 599 ASINs sampled -- sampling had eaten the run's entire budget
        before a single ASIN could be converted into a row. Proves sample_asins_stratified is now
        invoked with at most (1 - SAMPLE_TOKEN_RESERVE_FRACTION) of the cap, guaranteeing the rest
        for row-building."""
        captured = {}

        def fake_stratified(api, budget_tokens, target=bt.TARGET_ASINS, find_fn=None,
                            firehose_fn=None, seller_fn=None):
            captured["budget_tokens"] = budget_tokens
            return [], 0, {"dealfeed": 0, "storefront": 0, "explore": 0, "onpolicy": 0}

        with mock.patch.object(bt.config, "have_keepa", return_value=True), \
             mock.patch.object(bt, "sample_asins_stratified", side_effect=fake_stratified):
            bt.run_backtest(api=object(), token_cap=40, persist=False)

        self.assertEqual(captured["budget_tokens"], 40 - int(40 * bt.SAMPLE_TOKEN_RESERVE_FRACTION))
        self.assertLess(captured["budget_tokens"], 40, "sampling must not get the full run cap")


class PendingBacklogTest(RunBacktestBudgetTest):
    """fba-ml-data-engineer (2026-07-10): the sampled-but-deferred remainder used to be
    DISCARDED every run — ~half of every tier-3 budget re-bought discovery of already-known
    ASINs. It now persists as state["pending"], drains FIRST next run, and sampling is skipped
    entirely while the backlog exceeds what the cap can pull."""

    def _seed_state(self, pending, processed=None):
        import json
        state_path = bt._state_path()
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump({"processed_asins": processed or [], "spent_tokens": 0, "rows_written": 0,
                       "pending": pending}, f)

    def test_pending_backlog_count_is_distinct_and_excludes_processed(self):
        self._seed_state([
            {"asin": "P1", "sample_source": "dealfeed"},
            {"asin": "P1", "sample_source": "dealfeed"},
            {"asin": "P2", "sample_source": "explore"},
            {"asin": "DONE", "sample_source": "onpolicy"},
            {"sample_source": "dealfeed"},
        ], processed=["DONE"])
        self.assertEqual(bt.pending_backlog_count(), 2)

    def test_backlog_skips_sampling_and_drains_first(self):
        pending = [{"asin": f"P{i}", "sample_source": "dealfeed", "category": "pet"}
                  for i in range(50)]  # 50 >> cap(10)//1 affordable pulls
        self._seed_state(pending)
        pulled = []

        def fake_history(asins, api=None):
            pulled.extend(asins)
            return [{"asin": a, "data": None} for a in asins]

        sampler = mock.Mock(side_effect=AssertionError("sampling must be SKIPPED on a full backlog"))
        with mock.patch.object(bt.config, "have_keepa", return_value=True),              mock.patch.object(bt, "sample_asins_stratified", sampler):
            r = bt.run_backtest(api=object(), token_cap=10, history_fn=fake_history, persist=True)
        sampler.assert_not_called()
        self.assertTrue(r["sampling_skipped"])
        self.assertEqual(r["pending_drained"], 50)
        self.assertTrue(pulled)                      # backlog items actually pulled
        self.assertTrue(all(a.startswith("P") for a in pulled))
        self.assertGreater(r["pending_remaining"], 0)  # cap couldn't drain all 50 — rest persists

    def test_low_backlog_still_samples_and_appends(self):
        self._seed_state([{"asin": "P1", "sample_source": "explore", "category": "pet"}])

        def fake_stratified(api, budget_tokens, target=bt.TARGET_ASINS, find_fn=None,
                            firehose_fn=None, seller_fn=None):
            return ([{"asin": "S1", "category": "toys", "sample_source": "dealfeed"}], 5,
                    {"dealfeed": 1, "storefront": 0, "explore": 0, "onpolicy": 0})

        def fake_history(asins, api=None):
            return [{"asin": a, "data": None} for a in asins]

        with mock.patch.object(bt.config, "have_keepa", return_value=True),              mock.patch.object(bt, "sample_asins_stratified", side_effect=fake_stratified):
            r = bt.run_backtest(api=object(), token_cap=200, history_fn=fake_history, persist=True)
        self.assertFalse(r["sampling_skipped"])
        self.assertEqual(r["pending_drained"], 1)
        # both the drained backlog item and the fresh sample were processed
        self.assertEqual(r["pending_remaining"], 0)

    def test_drain_order_interleaves_categories_not_fifo(self):
        # 40 "tools" enqueued first, then 5 "grocery" -- raw FIFO would drain all 40 tools
        # before touching grocery. A budget that can only afford ~10 pulls must still reach
        # grocery immediately instead of exhausting itself on tools alone.
        pending = ([{"asin": f"TOOL{i}", "sample_source": "dealfeed", "category": "tools"}
                   for i in range(40)]
                  + [{"asin": f"GROC{i}", "sample_source": "dealfeed", "category": "grocery"}
                     for i in range(5)])
        self._seed_state(pending)
        pulled = []

        def fake_history(asins, api=None):
            pulled.extend(asins)
            return [{"asin": a, "data": None} for a in asins]

        sampler = mock.Mock(side_effect=AssertionError("sampling must be SKIPPED on a full backlog"))
        with mock.patch.object(bt.config, "have_keepa", return_value=True),              mock.patch.object(bt, "sample_asins_stratified", sampler):
            bt.run_backtest(api=object(), token_cap=10, history_fn=fake_history, persist=True)
        self.assertTrue(any(a.startswith("GROC") for a in pulled),
                        "grocery should be reached well before the 40-item tools cluster drains")

    def test_remainder_persists_with_source_tags(self):
        import json
        self._seed_state([])

        def fake_stratified(api, budget_tokens, target=bt.TARGET_ASINS, find_fn=None,
                            firehose_fn=None, seller_fn=None):
            return ([{"asin": f"S{i}", "category": "pet", "sample_source": "dealfeed"}
                     for i in range(30)], 5, {"dealfeed": 30, "storefront": 0, "explore": 0, "onpolicy": 0})

        def fake_history(asins, api=None):
            return [{"asin": a, "data": None} for a in asins]

        with mock.patch.object(bt.config, "have_keepa", return_value=True),              mock.patch.object(bt, "sample_asins_stratified", side_effect=fake_stratified):
            r = bt.run_backtest(api=object(), token_cap=12, history_fn=fake_history, persist=True)
        self.assertGreater(r["pending_remaining"], 0)
        with open(bt._state_path(), encoding="utf-8") as f:
            saved = json.load(f)
        self.assertTrue(saved["pending"])
        self.assertEqual(saved["pending"][0]["sample_source"], "dealfeed")
        self.assertEqual(saved["pending"][0]["category"], "pet")


class InterleaveByCategoryTest(unittest.TestCase):
    """Full-crew audit (2026-07-11): draining the pending backlog in raw FIFO order let one
    dealfeed rotation slot's whole category batch (100-250+ ASINs) monopolize every backtest
    run's small per-run pull budget for many consecutive hours — live-confirmed via Supabase
    (4 straight hourly runs 100% 'tools', 07-10 11:00-18:00). _interleave_by_category fixes the
    DRAIN ORDER so a fixed budget spreads across whatever categories are queued immediately."""

    def test_round_robins_across_categories(self):
        pending = ([{"asin": f"T{i}", "category": "tools"} for i in range(5)]
                  + [{"asin": f"G{i}", "category": "grocery"} for i in range(2)])
        out = bt._interleave_by_category(pending)
        cats = [p["category"] for p in out]
        # first two slots must cover BOTH categories, not five "tools" in a row
        self.assertEqual(set(cats[:2]), {"tools", "grocery"})
        self.assertEqual(len(out), len(pending))
        self.assertEqual(sorted(p["asin"] for p in out), sorted(p["asin"] for p in pending))

    def test_preserves_fifo_order_within_a_category(self):
        pending = ([{"asin": f"T{i}", "category": "tools"} for i in range(3)]
                  + [{"asin": f"G{i}", "category": "grocery"} for i in range(3)])
        out = bt._interleave_by_category(pending)
        tools_order = [p["asin"] for p in out if p["category"] == "tools"]
        self.assertEqual(tools_order, ["T0", "T1", "T2"])

    def test_noop_for_single_category_or_empty_backlog(self):
        single = [{"asin": "A", "category": "tools"}, {"asin": "B", "category": "tools"}]
        self.assertEqual(bt._interleave_by_category(single), single)
        self.assertEqual(bt._interleave_by_category([]), [])

    def test_handles_missing_category_as_its_own_bucket(self):
        pending = ([{"asin": "N1"}, {"asin": "N2"}]
                  + [{"asin": "T1", "category": "tools"}])
        out = bt._interleave_by_category(pending)
        self.assertEqual(len(out), 3)
        self.assertEqual({p["asin"] for p in out}, {"N1", "N2", "T1"})


class TrendPrefetchBatchTest(RunBacktestBudgetTest):
    """Review fix (2026-07-06): build_rows_for_asin()'s _fetch_trend_series() call used to have
    no cross-ASIN caching within a run — up to 2 sequential live db.trends_series_for() calls
    PER ASIN. run_backtest()'s batch loop now bulk-prefetches every distinct brand/category term
    ONCE per batch (signals.trends.prefetch_series) regardless of how many ASINs share a term."""

    def test_bulk_prefetches_once_per_batch_not_per_asin(self):
        def fake_find(api=None, brand_seeds=None, limit=None):
            return {"Lego": ["A1", "A2", "A3"]}.get((brand_seeds or [None])[0], [])

        def fake_history(asins, api=None):
            return [{"asin": a, "data": None} for a in asins]

        fake_static = {"A1": {"asin": "A1", "brand": "Lego", "category": "toys", "weight_lb": 1.0},
                      "A2": {"asin": "A2", "brand": "Lego", "category": "toys", "weight_lb": 1.0},
                      "A3": {"asin": "A3", "brand": "Yeti", "category": "kitchen", "weight_lb": 1.0}}

        def fake_parse(product):
            return {}, fake_static[product["asin"]]

        with mock.patch.object(bt.config, "have_keepa", return_value=True), \
             mock.patch.object(bt, "backtest_token_cap", return_value=200), \
             mock.patch.object(bt, "parse_keepa_history", side_effect=fake_parse), \
             mock.patch.object(bt, "sample_asins_explore", return_value=([], 0)), \
             mock.patch("brands.seed_brands", return_value=["Lego"]), \
             mock.patch("discovery_hints.hinted_brand_seeds", return_value=[]), \
             mock.patch("signals.trends.prefetch_series", return_value={}) as mprefetch:
            bt.run_backtest(api=object(), find_fn=fake_find, history_fn=fake_history, persist=False)

        mprefetch.assert_called_once()  # ONE bulk call for the whole batch, not one per ASIN
        (called_terms,), _ = mprefetch.call_args
        self.assertEqual(sorted(called_terms), ["Lego", "Yeti", "kitchen", "toys"])

    def test_prefetch_failure_falls_back_to_per_asin_live_fetch_never_raises(self):
        def fake_find(api=None, brand_seeds=None, limit=None):
            return {"Lego": ["A1"]}.get((brand_seeds or [None])[0], [])

        def fake_history(asins, api=None):
            return [{"asin": a, "data": None} for a in asins]

        def fake_parse(product):
            return {}, {"asin": product["asin"], "brand": "Lego", "category": "toys", "weight_lb": 1.0}

        with mock.patch.object(bt.config, "have_keepa", return_value=True), \
             mock.patch.object(bt, "backtest_token_cap", return_value=200), \
             mock.patch.object(bt, "parse_keepa_history", side_effect=fake_parse), \
             mock.patch("brands.seed_brands", return_value=["Lego"]), \
             mock.patch("discovery_hints.hinted_brand_seeds", return_value=[]), \
             mock.patch("signals.trends.prefetch_series", side_effect=RuntimeError("supabase down")):
            r = bt.run_backtest(api=object(), find_fn=fake_find, history_fn=fake_history, persist=False)
        self.assertEqual(r["status"], "ok")  # degraded gracefully, never propagated the failure


class HistoryLoopBatchSizingTest(RunBacktestBudgetTest):
    """Session 55 review fix: _ENRICH_BATCH (100) is a request-size CEILING, not a promise that
    100 tokens are banked. The Keepa Pro plan's bank caps at 60, so the OLD `if spent +
    _ENRICH_BATCH > cap: break` check made the hourly cloud collector's tier-3 backtest defer
    its ENTIRE todo list on the very first loop iteration of every run (spent=0, cap<=60,
    0+100>60 always true) and never pull a single history batch. The fix sizes each batch to
    what's actually affordable (live bank AND remaining cap), so a low-token run still gets rows."""

    class _FakeApi:
        def __init__(self, tokens_left):
            self.tokens_left = tokens_left
            self.tokens_consumed_total = 0

        def update_status(self):
            pass

    def test_small_cap_still_pulls_a_partial_history_batch(self):
        pulled_batches = []

        def fake_history(asins, api=None):
            pulled_batches.append(list(asins))
            api.tokens_left -= len(asins)  # simulate the real 1-token/ASIN spend
            api.tokens_consumed_total += len(asins)
            return [{"asin": a, "data": None} for a in asins]

        preset_sample = [{"asin": f"A{i:03d}", "category": None, "sample_source": "onpolicy"}
                        for i in range(30)]

        with mock.patch.object(bt.config, "have_keepa", return_value=True), \
             mock.patch.object(bt, "sample_asins_stratified",
                               return_value=(preset_sample, 0, {"onpolicy": 30})):
            r = bt.run_backtest(api=self._FakeApi(tokens_left=40), token_cap=40,
                               history_fn=fake_history, persist=False)

        self.assertTrue(pulled_batches, "history_fn was never called — everything deferred, "
                                       "reproducing the exact bug this test guards against")
        self.assertLessEqual(len(pulled_batches[0]), 40)  # sized to the bank, not a fixed 100
        self.assertEqual(r["deferred_asins"], 0)
        self.assertEqual(r["asins_processed"], 30)

    def test_zero_bank_defers_without_crashing(self):
        preset_sample = [{"asin": "A001", "category": None, "sample_source": "onpolicy"}]
        with mock.patch.object(bt.config, "have_keepa", return_value=True), \
             mock.patch.object(bt, "sample_asins_stratified",
                               return_value=(preset_sample, 0, {"onpolicy": 1})):
            r = bt.run_backtest(api=self._FakeApi(tokens_left=0), token_cap=40,
                               history_fn=lambda asins, api=None: [], persist=False)
        self.assertEqual(r["deferred_asins"], 1)
        self.assertEqual(r["asins_processed"], 0)

    def test_spend_reflects_measured_delta_not_phantom_full_batch(self):
        """The old code charged spent += len(batch) even when the guard inside history_fn
        truncated or skipped the request — phantom spend that inflated the persisted state and
        starved future runs. The new accounting must reflect ACTUAL measured token movement."""
        def fake_history_truncates(asins, api=None):
            # simulates keepa_client's own internal guard silently returning fewer products
            # than requested, while genuinely spending only for what it returned
            actually_processed = asins[:2]
            api.tokens_left -= len(actually_processed)
            api.tokens_consumed_total += len(actually_processed)
            return [{"asin": a, "data": None} for a in actually_processed]

        preset_sample = [{"asin": f"A{i:03d}", "category": None, "sample_source": "onpolicy"}
                        for i in range(10)]
        with mock.patch.object(bt.config, "have_keepa", return_value=True), \
             mock.patch.object(bt, "sample_asins_stratified",
                               return_value=(preset_sample, 0, {"onpolicy": 10})):
            r = bt.run_backtest(api=self._FakeApi(tokens_left=10), token_cap=10000,
                               history_fn=fake_history_truncates, persist=False)
        # only 2 tokens were ever actually spent (measured via the tokens_left delta), never the
        # full 10-ASIN batch size the old `spent += len(batch)` would have charged
        self.assertEqual(r["tokens_spent"], 2)


class RemoteStateFallbackTest(unittest.TestCase):
    """Review fix (2026-07-07, live incident): _state_path() is a LOCAL file — on GitHub Actions
    (no persistent disk between runs) it never survived, so every hourly burst silently started
    from empty state, re-sampled fresh dealfeed candidates every single time, and never actually
    progressed toward the resumable corpus (298 ASINs sampled, 0 processed, observed live).
    _load_state()/_save_state() now fall back to a Supabase-Storage-backed copy — these tests
    exercise that fallback directly (not via the full run_backtest() cycle above, which always
    mocks the remote functions out for isolation)."""

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("DATALAKE_ENABLED", "DATA_LAKE_DIR")}
        import tempfile
        os.environ["DATALAKE_ENABLED"] = "0"
        os.environ["DATA_LAKE_DIR"] = tempfile.mkdtemp(prefix="fba-bt-remote-test-")

    def tearDown(self):
        import shutil
        shutil.rmtree(os.environ["DATA_LAKE_DIR"], ignore_errors=True)
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_empty_local_file_falls_back_to_remote_state(self):
        remote = {"processed_asins": ["B0REMOTE"], "spent_tokens": 42, "rows_written": 7}
        with mock.patch.object(bt, "_fetch_remote_state", return_value=remote) as mfetch:
            st = bt._load_state()
        mfetch.assert_called_once()
        self.assertEqual(st, remote)

    def test_nonempty_local_file_is_preferred_over_remote(self):
        local = {"processed_asins": ["B0LOCAL"], "spent_tokens": 1, "rows_written": 0}
        with open(bt._state_path(), "w", encoding="utf-8") as f:
            json.dump(local, f)
        with mock.patch.object(bt, "_fetch_remote_state",
                              side_effect=AssertionError("should not be called")):
            st = bt._load_state()
        self.assertEqual(st, local)

    def test_save_state_writes_locally_and_uploads_remotely(self):
        st = {"processed_asins": ["B0NEW"], "spent_tokens": 3, "rows_written": 1}
        with mock.patch.object(bt, "_upload_remote_state") as mupload:
            bt._save_state(st)
        mupload.assert_called_once_with(st)
        with open(bt._state_path(), encoding="utf-8") as f:
            self.assertEqual(json.load(f), st)

    def test_remote_fetch_failure_degrades_to_empty_not_a_crash(self):
        with mock.patch("requests.get", side_effect=ConnectionError("network down")), \
             mock.patch.dict(os.environ, {"SUPABASE_URL": "https://example.test",
                                          "SUPABASE_SERVICE_KEY": "fake"}):
            st = bt._fetch_remote_state()
        self.assertEqual(st, {})

    def test_strict_remote_fetch_failure_marks_backlog_preflight_unknown(self):
        with mock.patch("requests.get", side_effect=ConnectionError("network down")), \
             mock.patch.dict(os.environ, {"SUPABASE_URL": "https://example.test",
                                          "SUPABASE_SERVICE_KEY": "fake"}):
            with self.assertRaisesRegex(RuntimeError, "remote state unavailable"):
                bt._fetch_remote_state(strict=True)

    def test_remote_upload_failure_is_non_fatal(self):
        with mock.patch("requests.post", side_effect=ConnectionError("network down")), \
             mock.patch.dict(os.environ, {"SUPABASE_URL": "https://example.test",
                                          "SUPABASE_SERVICE_KEY": "fake"}):
            ok = bt._upload_remote_state({"processed_asins": []})
        self.assertFalse(ok)


class SampleAsinsExploreRotationTest(RunBacktestBudgetTest):
    """Review fix (2026-07-09, live incident): sample_asins_explore()'s category loop used to
    always start at cats[0] -- under this function's typically small share of the sampling
    budget (dealfeed takes its cut first), only the first 1-2 configured categories ever got a
    real attempt, run after run. Live-confirmed: 100% of 200 dealfeed-sourced backtest_rows
    collected were tagged "toys" (a related but separate rotation bug in deals_firehose.py), and
    the wider corpus is 82.5% toys / top-5 brands 37% -- this function's own un-rotated loop was
    a second contributor. A persisted cursor (own Supabase Storage path) now rotates the start
    position across calls."""

    def test_rotation_starts_from_the_persisted_cursor_not_always_index_zero(self):
        def fake_find(api=None, brand_seeds=None, limit=None):
            return {"kitchen": ["B_KITCHEN"]}.get((brand_seeds or [None])[0], [])

        with mock.patch.object(bt, "_fetch_remote_explore_cursor", return_value=1):
            out, spent = bt.sample_asins_explore(
                object(), budget_tokens=10, categories=["toys", "kitchen", "pet"], find_fn=fake_find)
        # cursor=1 -> rotation starts at "kitchen"; budget only affords one category (flat 10/ea)
        self.assertEqual([d["category"] for d in out], ["kitchen"])
        self.assertEqual(spent, 10)

    def test_cursor_advances_past_categories_actually_attempted(self):
        def fake_find(api=None, brand_seeds=None, limit=None):
            return []

        with mock.patch.object(bt, "_fetch_remote_explore_cursor", return_value=0), \
             mock.patch.object(bt, "_upload_remote_explore_cursor") as mupload:
            bt.sample_asins_explore(
                object(), budget_tokens=20, categories=["toys", "kitchen", "pet"], find_fn=fake_find)
        # cursor(0) + 2 categories attempted (20 budget / 10 each) -> next run starts at "pet"
        mupload.assert_called_once_with(2)

    def test_cursor_wraps_around_the_end_of_the_category_list(self):
        def fake_find(api=None, brand_seeds=None, limit=None):
            return []

        with mock.patch.object(bt, "_fetch_remote_explore_cursor", return_value=2), \
             mock.patch.object(bt, "_upload_remote_explore_cursor") as mupload:
            bt.sample_asins_explore(
                object(), budget_tokens=20, categories=["toys", "kitchen", "pet"], find_fn=fake_find)
        # cursor=2 ("pet") + 2 attempted wraps past the end of a 3-item list -> back to index 1
        mupload.assert_called_once_with(1)


class SampleAsinsStorefrontTest(unittest.TestCase):
    """Keepa throughput plan Action D (2026-07-11): a full 3P storefront's ASIN list (hundreds
    of ASINs) for ~SELLER_QUERY_TOKENS_ESTIMATE tokens via keepa_client.seller_asins, rotating
    through deals_firehose's opportunistically-grown seller pool via a persisted cursor — same
    pattern as sample_asins_explore's category rotation."""

    def test_empty_pool_is_a_safe_noop(self):
        with mock.patch.object(deals_firehose, "_fetch_remote_seller_pool", return_value=[]):
            out, spent = bt.sample_asins_storefront(object(), budget_tokens=100)
        self.assertEqual((out, spent), ([], 0))

    def test_rotation_starts_from_the_persisted_cursor_not_always_index_zero(self):
        def fake_seller(seller_id, api=None):
            return {"S2": ["B_S2"]}.get(seller_id, [])

        with mock.patch.object(deals_firehose, "_fetch_remote_seller_pool",
                               return_value=["S1", "S2", "S3"]), \
             mock.patch.object(deals_firehose, "_fetch_remote_seller_cursor", return_value=1), \
             mock.patch.object(deals_firehose, "_upload_remote_seller_cursor"):
            out, spent = bt.sample_asins_storefront(object(), budget_tokens=10, seller_fn=fake_seller)
        # cursor=1 -> rotation starts at "S2"; budget only affords one seller query (10 tokens)
        self.assertEqual([d["asin"] for d in out], ["B_S2"])
        self.assertIsNone(out[0]["category"])
        self.assertEqual(spent, 10)

    def test_cursor_advances_past_sellers_actually_attempted_and_wraps(self):
        def fake_seller(seller_id, api=None):
            return []

        with mock.patch.object(deals_firehose, "_fetch_remote_seller_pool",
                               return_value=["S1", "S2", "S3"]), \
             mock.patch.object(deals_firehose, "_fetch_remote_seller_cursor", return_value=2), \
             mock.patch.object(deals_firehose, "_upload_remote_seller_cursor") as mupload:
            bt.sample_asins_storefront(object(), budget_tokens=20, seller_fn=fake_seller)
        # cursor=2 ("S3") + 2 sellers attempted (20 budget / 10 each) wraps past the 3-item list
        mupload.assert_called_once_with(1)

    def test_budget_precheck_stops_before_overspending(self):
        calls = []

        def fake_seller(seller_id, api=None):
            calls.append(seller_id)
            return []

        with mock.patch.object(deals_firehose, "_fetch_remote_seller_pool",
                               return_value=["S1", "S2", "S3"]), \
             mock.patch.object(deals_firehose, "_fetch_remote_seller_cursor", return_value=0), \
             mock.patch.object(deals_firehose, "_upload_remote_seller_cursor"):
            out, spent = bt.sample_asins_storefront(object(), budget_tokens=15, seller_fn=fake_seller)
        # 15 tokens affords exactly one 10-token query, not two
        self.assertEqual(calls, ["S1"])
        self.assertEqual(spent, 10)

    def test_seller_fn_failure_is_non_fatal(self):
        def fake_seller(seller_id, api=None):
            raise RuntimeError("boom")

        with mock.patch.object(deals_firehose, "_fetch_remote_seller_pool", return_value=["S1"]), \
             mock.patch.object(deals_firehose, "_fetch_remote_seller_cursor", return_value=0), \
             mock.patch.object(deals_firehose, "_upload_remote_seller_cursor"):
            out, spent = bt.sample_asins_storefront(object(), budget_tokens=100, seller_fn=fake_seller)
        self.assertEqual(out, [])

    def test_dedupes_asins_across_sellers(self):
        def fake_seller(seller_id, api=None):
            return {"S1": ["B1", "B2"], "S2": ["B2", "B3"]}.get(seller_id, [])

        with mock.patch.object(deals_firehose, "_fetch_remote_seller_pool",
                               return_value=["S1", "S2"]), \
             mock.patch.object(deals_firehose, "_fetch_remote_seller_cursor", return_value=0), \
             mock.patch.object(deals_firehose, "_upload_remote_seller_cursor"):
            out, spent = bt.sample_asins_storefront(object(), budget_tokens=20, seller_fn=fake_seller)
        self.assertEqual(sorted(d["asin"] for d in out), ["B1", "B2", "B3"])


class StratifiedSamplingIncludesStorefrontTest(RunBacktestBudgetTest):
    """sample_asins_stratified()'s waterfall order: dealfeed -> storefront -> explore ->
    onpolicy. Storefront sits between dealfeed and explore per the Keepa throughput plan
    (Action D) — the cheapest new breadth lever once dealfeed's day-to-day overlap grows."""

    def test_storefront_asins_are_tagged_and_counted(self):
        def fake_firehose(api, pages=None):
            return {"asins": [], "tokens_spent": 0}

        def fake_seller(seller_id, api=None):
            return ["B_STORE"]

        with mock.patch.object(deals_firehose, "_fetch_remote_seller_pool", return_value=["S1"]), \
             mock.patch.object(deals_firehose, "_fetch_remote_seller_cursor", return_value=0), \
             mock.patch.object(deals_firehose, "_upload_remote_seller_cursor"), \
             mock.patch.object(bt, "sample_asins_explore", return_value=([], 0)), \
             mock.patch.object(bt, "sample_asins_on_policy", return_value=([], 0)):
            out, spent, counts = bt.sample_asins_stratified(
                object(), budget_tokens=100, firehose_fn=fake_firehose, seller_fn=fake_seller)
        self.assertEqual([d["asin"] for d in out], ["B_STORE"])
        self.assertEqual(out[0]["sample_source"], "storefront")
        self.assertEqual(counts["storefront"], 1)


if __name__ == "__main__":
    unittest.main()
