"""
test_deals_firehose.py — the Keepa /deal breadth firehose (Session 55, learning.sampling).

All Keepa calls are mocked (a FakeApi below) — no live tokens spent. Covers: the flat-cost guard
skipping when the bank can't cover a page, category id resolution + disk caching, category
rotation across a harvest() run, and graceful degradation when categories can't be resolved.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import deals_firehose as df  # noqa: E402
import keepa_client  # noqa: E402


class FakeApi:
    def __init__(self, tokens_left=60, pages=None, roots=None):
        self.tokens_left = tokens_left
        self.tokens_consumed_total = 0
        self._pages = pages or {}   # (category, page) -> ["ASIN1", ...]
        self._roots = roots or {}

    def update_status(self):
        pass

    def deals(self, deal_parms, domain=None, wait=True):
        self.tokens_consumed_total += keepa_client.DEALS_PAGE_TOKENS
        self.tokens_left -= keepa_client.DEALS_PAGE_TOKENS
        cat_ids = deal_parms.get("includeCategories")
        key = (tuple(cat_ids) if cat_ids else None, deal_parms.get("page", 0))
        asins = self._pages.get(key, [])
        return {"dr": [{"asin": a} for a in asins]}

    def category_lookup(self, cat_id, domain=None):
        return self._roots


class GuardFlatTest(unittest.TestCase):
    def setUp(self):
        keepa_client.reset_guard_telemetry()

    def test_ok_when_bank_covers_cost(self):
        api = FakeApi(tokens_left=10)
        self.assertTrue(keepa_client._guard_flat(api, 5, "test"))

    def test_skips_when_bank_cannot_cover_cost(self):
        api = FakeApi(tokens_left=3)
        self.assertFalse(keepa_client._guard_flat(api, 5, "test"))
        self.assertEqual(keepa_client.guard_telemetry()["skips"], 1)

    def test_skips_when_bank_negative(self):
        api = FakeApi(tokens_left=-21)
        self.assertFalse(keepa_client._guard_flat(api, 5, "test"))

    def test_unreadable_bank_degrades_to_trusting_caller(self):
        self.assertTrue(keepa_client._guard_flat(object(), 5, "test"))


class FetchDealPageTest(unittest.TestCase):
    def setUp(self):
        keepa_client.reset_guard_telemetry()

    def test_returns_asins_from_a_page(self):
        api = FakeApi(tokens_left=60, pages={((11,), 0): ["B001", "B002"]})
        result = df.fetch_deal_page(api, category="toys", category_id=11, page=0)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["asins"], ["B001", "B002"])

    def test_skips_when_bank_insufficient(self):
        api = FakeApi(tokens_left=2)
        result = df.fetch_deal_page(api, category="toys", category_id=11, page=0)
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["asins"], [])

    def test_unfiltered_pull_when_no_category_id(self):
        api = FakeApi(tokens_left=60, pages={(None, 0): ["B003"]})
        result = df.fetch_deal_page(api, category=None, category_id=None, page=0)
        self.assertEqual(result["asins"], ["B003"])


class ResolveCategoryIdsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.patch = mock.patch.object(df, "CACHE_PATH", os.path.join(self.tmp, "ids.json"))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_resolves_and_caches(self):
        roots = {
            "1": {"catId": 165793011, "name": "Toys & Games"},
            "2": {"catId": 284507, "name": "Kitchen & Dining"},
        }
        api = FakeApi(roots=roots)
        resolved = df.resolve_category_ids(api, ["toys", "kitchen", "unmapped_category"])
        self.assertEqual(resolved.get("toys"), 165793011)
        self.assertEqual(resolved.get("kitchen"), 284507)
        self.assertNotIn("unmapped_category", resolved)
        self.assertTrue(os.path.exists(df.CACHE_PATH))

    def test_second_call_uses_cache_not_a_live_lookup(self):
        roots = {"1": {"catId": 165793011, "name": "Toys & Games"}}
        api = FakeApi(roots=roots)
        df.resolve_category_ids(api, ["toys"])
        api.category_lookup = mock.Mock(side_effect=AssertionError("should not be called again"))
        resolved = df.resolve_category_ids(api, ["toys"])
        self.assertEqual(resolved.get("toys"), 165793011)

    def test_lookup_failure_degrades_to_cached_or_empty(self):
        api = FakeApi()
        api.category_lookup = mock.Mock(side_effect=RuntimeError("network down"))
        resolved = df.resolve_category_ids(api, ["toys"])
        self.assertEqual(resolved, {})


class HarvestTest(unittest.TestCase):
    def setUp(self):
        keepa_client.reset_guard_telemetry()

    def test_rotates_categories_and_dedupes(self):
        api = FakeApi(tokens_left=60, pages={
            ((11,), 0): ["B001", "B002"],
            ((22,), 0): ["B002", "B003"],  # B002 overlaps -> dedupe
        })
        result = df.harvest(api, pages=2, categories=["toys", "kitchen"],
                            resolve_fn=lambda api, cats: {"toys": 11, "kitchen": 22})
        self.assertEqual(result["pages_pulled"], 2)
        asins = sorted(a["asin"] for a in result["asins"])
        self.assertEqual(asins, ["B001", "B002", "B003"])
        # B002 is deduped — only counted once, against whichever category's page introduced it
        self.assertEqual(result["by_category"], {"toys": 2, "kitchen": 1})

    def test_stops_early_when_bank_runs_dry(self):
        api = FakeApi(tokens_left=keepa_client.DEALS_PAGE_TOKENS)  # only 1 page affordable
        result = df.harvest(api, pages=4, categories=["toys"],
                            resolve_fn=lambda api, cats: {"toys": 11})
        self.assertEqual(result["pages_pulled"], 2)  # 1 successful + 1 that trips the skip

    def test_unfiltered_when_categories_unresolvable(self):
        api = FakeApi(tokens_left=60, pages={(None, 0): ["B009"]})
        result = df.harvest(api, pages=1, categories=["toys"],
                            resolve_fn=lambda api, cats: {})
        self.assertEqual([a["asin"] for a in result["asins"]], ["B009"])
        self.assertEqual(result["categories_resolved"], [])


if __name__ == "__main__":
    unittest.main()
