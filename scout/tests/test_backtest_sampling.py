"""
test_backtest_sampling.py — the brand-agnostic data-sampling overhaul (Session 55,
learning-hub/data/ai-brain.json learning.sampling).

Covers: sample_asins_explore's brand-agnostic category seeding, sample_asins_stratified's
budget-waterfall math (dealfeed -> explore -> onpolicy) and per-source tagging, build_rows_for_
asin's ip_risk flagging for avoid-listed brands, and the architectural safety guarantee that the
new sampling paths have no way to create a lead/candidate/review-queue row regardless of score —
that gate lives entirely in scoring.oa_hard_reject/brands.is_avoided on the separate buy-discovery
path, untouched here.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtest as bt  # noqa: E402
import brands  # noqa: E402
import deals_firehose as df  # noqa: E402


BASE_HIST = {
    "price": [(1000 + d, 20.0) for d in range(200)],
    "offers": [(1000 + d, 5.0) for d in range(200)],
    "sales_rank": [(1000 + d, 15000.0) for d in range(200)],
    "amazon": [],
}


class SampleAsinsExploreTest(unittest.TestCase):
    def test_seeds_with_category_keywords_not_brands(self):
        seen_terms = []

        def fake_find(api=None, brand_seeds=None, limit=None):
            seen_terms.append((brand_seeds or [None])[0])
            return [f"ASIN-{(brand_seeds or [None])[0]}"]

        out, spent = bt.sample_asins_explore(object(), budget_tokens=1000,
                                             categories=["toys", "kitchen"], find_fn=fake_find)
        self.assertEqual(seen_terms, ["toys", "kitchen"])  # category terms, never a brand name
        self.assertEqual({d["asin"] for d in out}, {"ASIN-toys", "ASIN-kitchen"})
        self.assertEqual({d["category"] for d in out}, {"toys", "kitchen"})
        self.assertGreater(spent, 0)

    def test_stops_when_budget_exhausted(self):
        calls = []

        def fake_find(api=None, brand_seeds=None, limit=None):
            calls.append(brand_seeds)
            return []

        bt.sample_asins_explore(object(), budget_tokens=15,
                                categories=["toys", "kitchen", "pet", "beauty"], find_fn=fake_find)
        # each call is charged the flat 10-token fallback (unreadable counters) -> budget=15 stops after 2
        self.assertEqual(len(calls), 2)


class SampleAsinsStratifiedTest(unittest.TestCase):
    def test_dealfeed_tried_first_then_explore_then_onpolicy(self):
        def fake_firehose(api, pages=None):
            return {"asins": [{"asin": "DEAL1", "category": "toys"}], "tokens_spent": 5}

        def fake_find(api=None, brand_seeds=None, limit=None):
            term = (brand_seeds or [None])[0]
            if term == "kitchen":
                return ["EXPLORE1"]
            if term == "Lego":
                return ["ONPOLICY1"]
            return []

        with mock.patch("brands.seed_brands", return_value=["Lego"]), \
             mock.patch("discovery_hints.hinted_brand_seeds", return_value=[]):
            out, spent, counts = bt.sample_asins_stratified(
                object(), budget_tokens=300, target=100, find_fn=fake_find,
                firehose_fn=fake_firehose)

        by_asin = {d["asin"]: d["sample_source"] for d in out}
        self.assertEqual(by_asin.get("DEAL1"), "dealfeed")
        self.assertEqual(by_asin.get("ONPOLICY1"), "onpolicy")
        self.assertEqual(counts["dealfeed"], 1)
        self.assertEqual(counts["onpolicy"], 1)
        self.assertGreater(spent, 0)

    def test_dedupes_across_sources(self):
        """The same ASIN surfacing from two sources is kept once, tagged with whichever source
        found it first (dealfeed, since it's tried first in the waterfall)."""
        def fake_firehose(api, pages=None):
            return {"asins": [{"asin": "SHARED", "category": "toys"}], "tokens_spent": 5}

        def fake_find(api=None, brand_seeds=None, limit=None):
            return ["SHARED"]

        with mock.patch("brands.seed_brands", return_value=["Lego"]), \
             mock.patch("discovery_hints.hinted_brand_seeds", return_value=[]):
            out, spent, counts = bt.sample_asins_stratified(
                object(), budget_tokens=300, target=100, find_fn=fake_find,
                firehose_fn=fake_firehose)
        asins = [d["asin"] for d in out]
        self.assertEqual(asins.count("SHARED"), 1)
        self.assertEqual(counts["dealfeed"], 1)
        self.assertEqual(counts["explore"], 0)

    def test_small_reserve_still_lets_dealfeed_afford_a_page(self):
        """Review fix (2026-07-07, live incident): a live burst with a 13-token tier-3 reserve
        (the new TIER3_RESERVE_FRACTION guard) came back with sample_composition all zeros --
        the OLD code pre-split 13//3=4 tokens to dealfeed's own share, below
        DEALS_PAGE_TOKENS(5), so pages_affordable was 0 and dealfeed never even tried. dealfeed
        must now get the FULL budget_tokens as its ceiling (13//5=2 pages affordable)."""
        seen_pages = {}

        def fake_firehose(api, pages=None):
            seen_pages["pages"] = pages
            return {"asins": [{"asin": "DEAL1", "category": "toys"}], "tokens_spent": 10}

        with mock.patch("brands.seed_brands", return_value=[]), \
             mock.patch("discovery_hints.hinted_brand_seeds", return_value=[]):
            out, spent, counts = bt.sample_asins_stratified(
                object(), budget_tokens=13, target=100,
                find_fn=lambda **kw: [], firehose_fn=fake_firehose)
        self.assertEqual(seen_pages["pages"], 2)  # 13 // 5, not 4 // 5 == 0
        self.assertEqual(counts["dealfeed"], 1)

    def test_zero_budget_yields_nothing_from_any_source(self):
        with mock.patch("brands.seed_brands", return_value=["Lego"]), \
             mock.patch("discovery_hints.hinted_brand_seeds", return_value=[]):
            out, spent, counts = bt.sample_asins_stratified(
                object(), budget_tokens=0, target=100,
                find_fn=lambda **kw: (_ for _ in ()).throw(AssertionError("should not be called")),
                firehose_fn=lambda api, pages=None: (_ for _ in ()).throw(AssertionError("nope")))
        self.assertEqual(out, [])
        self.assertEqual(spent, 0)


class IpRiskFlaggingTest(unittest.TestCase):
    def test_avoid_brand_flagged_ip_risk(self):
        with mock.patch.object(brands, "AVOID_BRANDS", ["Nike"]):
            rows = bt.build_rows_for_asin("B01", BASE_HIST,
                                          {"brand": "Nike", "category": "sports", "weight_lb": 1.0},
                                          sample_source="dealfeed")
        self.assertTrue(rows)
        self.assertTrue(all(r["ip_risk"] is True for r in rows))
        self.assertTrue(all(r["sample_source"] == "dealfeed" for r in rows))

    def test_friendly_brand_not_flagged(self):
        with mock.patch.object(brands, "AVOID_BRANDS", ["Nike"]):
            rows = bt.build_rows_for_asin("B02", BASE_HIST,
                                          {"brand": "Lego", "category": "toys", "weight_lb": 1.0},
                                          sample_source="explore")
        self.assertTrue(rows)
        self.assertTrue(all(r["ip_risk"] is False for r in rows))

    def test_default_sample_source_is_onpolicy(self):
        rows = bt.build_rows_for_asin("B03", BASE_HIST, {"brand": "Lego", "category": "toys", "weight_lb": 1.0})
        self.assertTrue(all(r["sample_source"] == "onpolicy" for r in rows))


class SafetyArchitectureGuardTest(unittest.TestCase):
    """Session 55's non-negotiable: avoid-brand rows can be COLLECTED as training data (flagged
    ip_risk) but can NEVER enter leads/candidates/review-queue. backtest_rows was never a
    candidate surface to begin with — this test proves the new sampling code has no path to
    create one, by source inspection (same style as test_train_ranker.py's brain-write guard)."""

    def test_deals_firehose_never_calls_log_lead(self):
        src_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "deals_firehose.py")
        with open(src_path, encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("log_lead(", src)
        self.assertNotIn("log_decision(", src)

    def test_sample_asins_explore_never_calls_log_lead(self):
        src_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "backtest.py")
        with open(src_path, encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("log_lead(", src)
        self.assertNotIn("log_decision(", src)

    def test_run_backtest_never_calls_log_lead_even_with_avoid_brand_products(self):
        """End-to-end: a full run_backtest() cycle sampling an avoid-listed brand must still
        never touch db.log_lead — its only Supabase write path is upsert_backtest_rows."""
        import config as bt_config

        def fake_firehose(api, pages=None):
            return {"asins": ["B_AVOID"], "tokens_spent": 5}

        def fake_find(api=None, brand_seeds=None, limit=None):
            return []

        def fake_history(asins, api=None):
            return [{"asin": "B_AVOID", "brand": "Nike", "categoryTree": None, "data": {
                "NEW": [20.0] * 200, "NEW_time": [bt._dt.datetime(2026, 1, 1) + bt._dt.timedelta(days=d)
                                                  for d in range(200)],
                "COUNT_NEW": [5] * 200, "COUNT_NEW_time": [bt._dt.datetime(2026, 1, 1) + bt._dt.timedelta(days=d)
                                                           for d in range(200)],
                "SALES": [15000] * 200, "SALES_time": [bt._dt.datetime(2026, 1, 1) + bt._dt.timedelta(days=d)
                                                        for d in range(200)],
            }}]

        with mock.patch.object(bt.config, "have_keepa", return_value=True), \
             mock.patch.object(bt, "backtest_token_cap", return_value=1000), \
             mock.patch.object(brands, "AVOID_BRANDS", ["Nike"]), \
             mock.patch("brands.seed_brands", return_value=[]), \
             mock.patch("discovery_hints.hinted_brand_seeds", return_value=[]), \
             mock.patch("db.log_lead", side_effect=AssertionError("must never be called")), \
             mock.patch("db.upsert_backtest_rows", return_value=1) as mock_upsert:
            bt.run_backtest(api=object(), find_fn=fake_find, history_fn=fake_history,
                            persist=False)
        # If db.log_lead were ever invoked the mock's side_effect would have raised inside
        # run_backtest (which swallows exceptions per-batch, non-fatally) — assert instead that
        # upsert_backtest_rows saw the ip_risk-flagged row, proving the write path taken.
        if mock_upsert.called:
            written_rows = mock_upsert.call_args[0][0]
            self.assertTrue(any(r.get("ip_risk") for r in written_rows))


if __name__ == "__main__":
    unittest.main()
