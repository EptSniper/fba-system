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

    def category_lookup(self, cat_id, domain=None, wait=True):
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
        keepa_client.reset_guard_telemetry()
        self.tmp = tempfile.mkdtemp()
        self.patch = mock.patch.object(df, "CACHE_PATH", os.path.join(self.tmp, "ids.json"))
        self.patch.start()
        # Review fix (2026-07-08 audit): the category-id cache is now Supabase-Storage-backed,
        # same isolation reasoning as test_backtest.py's RunBacktestBudgetTest — without stubbing
        # these, an unrelated test could silently read/write the REAL production bucket whenever
        # SUPABASE_URL/SUPABASE_SERVICE_KEY happen to be set in the environment running the suite.
        self._remote_patchers = [
            mock.patch.object(df, "_fetch_remote_category_cache", return_value={}),
            mock.patch.object(df, "_upload_remote_category_cache", return_value=False),
        ]
        for p in self._remote_patchers:
            p.start()

    def tearDown(self):
        for p in self._remote_patchers:
            p.stop()
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

    def test_hyphen_vs_underscore_category_key_still_resolves(self):
        """Review fix (2026-07-09, live incident): ai-brain.json's learning.sampling.categories
        spelled this key "electronics-accessories" (hyphen) while keepa_client._CATEGORY_MAP's
        values use "electronics_accessories" (underscore) -- an exact-string inverse lookup
        silently never matched, so this category never resolved and always fell back to an
        unfiltered pull, one contributor to the corpus's category concentration."""
        roots = {"1": {"catId": 111222333, "name": "Cell Phones & Accessories"}}
        api = FakeApi(roots=roots)
        resolved = df.resolve_category_ids(api, ["electronics-accessories"])
        self.assertEqual(resolved.get("electronics-accessories"), 111222333)

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

    def test_wait_false_actually_reaches_the_live_call(self):
        """Review fix (2026-07-07, live incident): wait= used to be silently dropped, always
        defaulting to the keepa package's own wait=True regardless of what the caller asked
        for. Proves wait=False is threaded all the way to the underlying lookup_fn call."""
        roots = {"1": {"catId": 165793011, "name": "Toys & Games"}}
        seen_wait = {}

        def _lookup(cat_id, domain=None, wait=True):
            seen_wait["wait"] = wait
            return roots

        api = FakeApi(roots=roots)
        df.resolve_category_ids(api, ["toys"], lookup_fn=_lookup, wait=False)
        self.assertEqual(seen_wait["wait"], False)

    def test_a_hanging_lookup_is_bounded_by_the_deadline_not_left_to_hang(self):
        """Review fix (2026-07-07, live incident): this call used to have NO deadline wrapper
        at all — a rate-limited response made the keepa package's own internal wait sleep for
        however long a refill actually takes (880s observed live), with nothing bounding it.
        Proves the call now goes through keepa_client._with_deadline (measuring real elapsed
        time, not just checking the exception message)."""
        import time
        from unittest.mock import patch
        import keepa_client as kc

        def _hangs(cat_id, domain=None, wait=True):
            time.sleep(2)
            return {}

        api = FakeApi()
        with patch.object(kc, "KEEPA_NO_WAIT_DEADLINE_SECONDS", 0.2):
            start = time.time()
            resolved = df.resolve_category_ids(api, ["toys"], lookup_fn=_hangs, wait=False)
            elapsed = time.time() - start
        self.assertLess(elapsed, 2, f"should have failed fast on the deadline, took {elapsed}s")
        self.assertEqual(resolved, {})  # degrades to cached (empty here), never raises

    def test_falls_back_to_remote_cache_when_local_is_empty(self):
        """Review fix (2026-07-08 audit): CACHE_PATH is a local file that never survives an
        ephemeral GitHub Actions runner. An empty local cache must fall through to the
        Supabase-Storage-backed copy instead of re-paying the live lookup every run."""
        remote = {"toys": 165793011}
        with mock.patch.object(df, "_fetch_remote_category_cache", return_value=remote):
            api = FakeApi()
            api.category_lookup = mock.Mock(side_effect=AssertionError("should not be called"))
            resolved = df.resolve_category_ids(api, ["toys"])
        self.assertEqual(resolved, remote)

    def test_guard_skips_live_lookup_when_bank_cannot_cover_cost(self):
        """Review fix (2026-07-08 audit): resolve_category_ids() used to hit the live endpoint
        on every cache miss with no check the bank could even cover it — unlike every other
        Keepa call in this module. A starved bank must degrade to whatever's cached (possibly
        empty), never attempt the call."""
        api = FakeApi(tokens_left=0)
        api.category_lookup = mock.Mock(side_effect=AssertionError("should not be called"))
        resolved = df.resolve_category_ids(api, ["toys"])
        self.assertEqual(resolved, {})
        self.assertEqual(keepa_client.guard_telemetry()["skips"], 1)


class CategoryCacheRemotePersistenceTest(unittest.TestCase):
    def test_remote_fetch_failure_degrades_to_empty_not_a_crash(self):
        with mock.patch("requests.get", side_effect=ConnectionError("network down")), \
             mock.patch.dict(os.environ, {"SUPABASE_URL": "https://example.test",
                                          "SUPABASE_SERVICE_KEY": "fake"}):
            cache = df._fetch_remote_category_cache()
        self.assertEqual(cache, {})

    def test_remote_upload_failure_is_non_fatal(self):
        with mock.patch("requests.post", side_effect=ConnectionError("network down")), \
             mock.patch.dict(os.environ, {"SUPABASE_URL": "https://example.test",
                                          "SUPABASE_SERVICE_KEY": "fake"}):
            ok = df._upload_remote_category_cache({"toys": 1})
        self.assertFalse(ok)


class SecondaryAxisFiltersTest(unittest.TestCase):
    """ML de-bias Lever A part 2 (2026-07-09, ML_DEBIAS_PLAN.md): rank/price/drop%-band rotation
    layered on top of the category cursor, so successive runs sweep different SLICES of each
    category instead of always pulling whatever Keepa ranks first."""

    def test_index_zero_is_the_first_band_combo(self):
        filters = df.secondary_axis_filters(0)
        self.assertEqual(filters["salesRankRange"], list(df.RANK_SUB_BANDS[0]))
        self.assertEqual(filters["deltaPercentRange"], list(df.DROP_PERCENT_BANDS[0]))
        lo, hi = df._price_bands_dollars()[0]
        self.assertEqual(filters["currentRange"], [int(lo * 100), int(hi * 100)])  # dollars -> cents

    def test_price_bands_come_from_the_brain_not_a_hardcoded_copy(self):
        """ML audit fix (2026-07-09): the old hardcoded bands capped at $60 while the brain
        declares [60,150] as a stratum — with range filters enabled, dealfeed would never have
        sampled $60-150 at all. Single-sourced from learning.sampling.priceBands now."""
        with mock.patch.object(df, "sampling_config",
                               return_value={"priceBands": [[10, 30], [30, 200]]}):
            bands = df._price_bands_dollars()
        self.assertEqual(bands, [(10.0, 30.0), (30.0, 200.0)])
        # the top brain stratum must be reachable by some cursor index
        with mock.patch.object(df, "sampling_config",
                               return_value={"priceBands": [[10, 30], [30, 200]]}):
            tops = {tuple(df.secondary_axis_filters(i)["currentRange"])
                    for i in range(df._secondary_axis_size())}
        self.assertIn((3000, 20000), tops)

    def test_index_cycles_through_every_combo_before_repeating(self):
        def _hashable(v):
            return tuple(v) if isinstance(v, list) else v

        combos = [df.secondary_axis_filters(i) for i in range(df._secondary_axis_size())]
        seen = {tuple(sorted((k, _hashable(v)) for k, v in combo.items())) for combo in combos}
        self.assertEqual(len(seen), df._secondary_axis_size())  # every combo is distinct
        self.assertEqual(df.secondary_axis_filters(0), df.secondary_axis_filters(df._secondary_axis_size()))

    def test_enables_the_range_filters_keepa_requires(self):
        """Review fix (2026-07-09, fba-code-reviewer, BLOCKER): keepa.Keepa.deals() sends
        deal_parms verbatim -- without isRangeEnabled/isFilterEnabled, salesRankRange/
        currentRange/deltaPercentRange risk being silently ignored by Keepa's own API."""
        filters = df.secondary_axis_filters(0)
        self.assertIs(filters["isRangeEnabled"], True)
        self.assertIs(filters["isFilterEnabled"], True)

    def test_negative_or_oversized_index_wraps_safely(self):
        # harvest() always mods by len(...) before storing, but the function itself degrades
        # gracefully on any index rather than trusting every caller got that right.
        self.assertEqual(df.secondary_axis_filters(df._secondary_axis_size() + 2),
                         df.secondary_axis_filters(2))


class HarvestTest(unittest.TestCase):
    def setUp(self):
        keepa_client.reset_guard_telemetry()
        # Review fix (2026-07-09 ML de-bias audit): harvest() now persists a cross-run rotation
        # cursor the same Supabase-Storage-backed way the category-id cache already does — same
        # isolation reasoning as ResolveCategoryIdsTest: without stubbing these, a test could
        # silently read/write the REAL production cursor state.
        self._cursor_patchers = [
            mock.patch.object(df, "_fetch_remote_cursor", return_value=0),
            mock.patch.object(df, "_upload_remote_cursor", return_value=False),
            mock.patch.object(df, "_fetch_remote_secondary_cursor", return_value=0),
            mock.patch.object(df, "_upload_remote_secondary_cursor", return_value=False),
        ]
        for p in self._cursor_patchers:
            p.start()

    def tearDown(self):
        for p in self._cursor_patchers:
            p.stop()

    def test_rotates_categories_and_dedupes(self):
        api = FakeApi(tokens_left=60, pages={
            ((11,), 0): ["B001", "B002"],
            ((22,), 0): ["B002", "B003"],  # B002 overlaps -> dedupe
        })
        result = df.harvest(api, pages=2, categories=["toys", "kitchen"],
                            resolve_fn=lambda api, cats, wait=True: {"toys": 11, "kitchen": 22})
        self.assertEqual(result["pages_pulled"], 2)
        asins = sorted(a["asin"] for a in result["asins"])
        self.assertEqual(asins, ["B001", "B002", "B003"])
        # B002 is deduped — only counted once, against whichever category's page introduced it
        self.assertEqual(result["by_category"], {"toys": 2, "kitchen": 1})

    def test_rotation_starts_from_the_persisted_cursor_not_always_index_zero(self):
        """Review fix (2026-07-09, live incident): harvest()'s rotation used to restart at
        categories[0] on EVERY call -- with `pages` typically capped at 2-4 by the token budget
        and ~10 categories configured, every hourly run only ever touched the first few entries.
        Live-confirmed: 100% of 200 dealfeed-sourced backtest_rows collected were tagged "toys"
        (index 0), driving an 82.5%-toys corpus. A persisted cursor must make a fresh run start
        mid-list, not always at the front."""
        api = FakeApi(tokens_left=60, pages={((99,), 0): ["B_KITCHEN"]})
        with mock.patch.object(df, "_fetch_remote_cursor", return_value=1):
            result = df.harvest(api, pages=1, categories=["toys", "kitchen", "pet"],
                                resolve_fn=lambda api, cats, wait=True: {"kitchen": 99})
        # cursor=1 -> rotation starts at "kitchen", so the single page pulled is "kitchen", not "toys"
        self.assertEqual(result["by_category"], {"kitchen": 1})

    def test_cursor_advances_past_categories_actually_attempted_this_run(self):
        """The next run must pick up where this one left off, not restart -- otherwise a run that
        only ever affords 1-2 pages would still never progress past the front of the list."""
        api = FakeApi(tokens_left=60, pages={
            ((1,), 0): ["A1"], ((2,), 0): ["A2"], ((3,), 0): ["A3"],
        })
        with mock.patch.object(df, "_fetch_remote_cursor", return_value=0), \
             mock.patch.object(df, "_upload_remote_cursor") as mupload:
            df.harvest(api, pages=2, categories=["toys", "kitchen", "pet"],
                      resolve_fn=lambda api, cats, wait=True: {"toys": 1, "kitchen": 2, "pet": 3})
        mupload.assert_called_once_with(2)  # cursor(0) + pulled(2) -> next run starts at "pet"

    def test_cursor_wraps_around_the_end_of_the_category_list(self):
        api = FakeApi(tokens_left=60, pages={((3,), 0): ["A3"], ((1,), 0): ["A1"]})
        with mock.patch.object(df, "_fetch_remote_cursor", return_value=2), \
             mock.patch.object(df, "_upload_remote_cursor") as mupload:
            df.harvest(api, pages=2, categories=["toys", "kitchen", "pet"],
                      resolve_fn=lambda api, cats, wait=True: {"toys": 1, "kitchen": 2, "pet": 3})
        # cursor=2 ("pet") + 2 pulled wraps past the end of a 3-item list -> back to index 1
        mupload.assert_called_once_with(1)

    def test_stops_early_when_bank_runs_dry(self):
        # Give the filtered page real asins so the dry-slot unfiltered refetch (a separate
        # behavior, tested below) doesn't trigger — this test is purely about the bank guard.
        api = FakeApi(tokens_left=keepa_client.DEALS_PAGE_TOKENS,
                      pages={((11,), 0): ["B001"]})  # only 1 page affordable
        result = df.harvest(api, pages=4, categories=["toys"],
                            resolve_fn=lambda api, cats, wait=True: {"toys": 11})
        self.assertEqual(result["pages_pulled"], 2)  # 1 successful + 1 that trips the skip

    def test_dry_filtered_slot_refetches_unfiltered(self):
        """ML audit fix (2026-07-09): one narrow rank/price/drop combo ANDing down to an empty
        page used to zero the whole run's dealfeed yield (still billing 5 tokens/page). A dry
        filtered slot now re-pulls unfiltered (category-only) so the run never comes home empty
        because of one slice."""
        seen_parms = []

        class RecordingApi(FakeApi):
            def deals(self, deal_parms, domain=None, wait=True):
                seen_parms.append(dict(deal_parms))
                result = super().deals(deal_parms, domain=domain, wait=wait)
                if "salesRankRange" in deal_parms:
                    return {"dr": []}  # the narrow slice is dry; unfiltered still has deals
                return result

        api = RecordingApi(tokens_left=60, pages={((11,), 0): ["B001"]})
        result = df.harvest(api, pages=1, categories=["toys"],
                            resolve_fn=lambda api, cats, wait=True: {"toys": 11})
        self.assertEqual([a["asin"] for a in result["asins"]], ["B001"])
        self.assertEqual(result["dry_slots_refetched"], 1)
        self.assertEqual(len(seen_parms), 2)
        self.assertIn("salesRankRange", seen_parms[0])      # first attempt: filtered
        self.assertNotIn("salesRankRange", seen_parms[1])   # refetch: category-only

    def test_unfiltered_when_categories_unresolvable(self):
        api = FakeApi(tokens_left=60, pages={(None, 0): ["B009"]})
        result = df.harvest(api, pages=1, categories=["toys"],
                            resolve_fn=lambda api, cats, wait=True: {})
        self.assertEqual([a["asin"] for a in result["asins"]], ["B009"])
        self.assertEqual(result["categories_resolved"], [])

    def test_tokens_spent_includes_resolution_cost(self):
        """Review fix (2026-07-08 audit): a live category resolution's real token cost used to
        go entirely unmeasured — harvest() only ever counted fetch_deal_page's spend, silently
        understating this run's true cost to every caller (collect_hourly.py's tier-3 waterfall)
        that budgets off the returned tokens_spent."""
        def resolve_with_real_cost(api, cats, wait=True):
            api.tokens_left -= keepa_client.CATEGORY_LOOKUP_TOKENS
            return {"toys": 11}

        api = FakeApi(tokens_left=60, pages={((11,), 0): ["B001"]})
        result = df.harvest(api, pages=1, categories=["toys"], resolve_fn=resolve_with_real_cost)
        self.assertEqual(
            result["tokens_spent"],
            keepa_client.CATEGORY_LOOKUP_TOKENS + keepa_client.DEALS_PAGE_TOKENS,
        )

    def test_secondary_axis_filters_reach_the_live_deal_parms(self):
        """ML de-bias Lever A part 2: rank/price/drop%-band filters must actually reach Keepa's
        deal_parms, not just exist as an unused helper function."""
        seen_parms = []

        class RecordingApi(FakeApi):
            def deals(self, deal_parms, domain=None, wait=True):
                seen_parms.append(dict(deal_parms))
                return super().deals(deal_parms, domain=domain, wait=wait)

        api = RecordingApi(tokens_left=60, pages={((11,), 0): ["B001"]})
        with mock.patch.object(df, "_fetch_remote_secondary_cursor", return_value=5):
            df.harvest(api, pages=1, categories=["toys"],
                      resolve_fn=lambda api, cats, wait=True: {"toys": 11})
        expected = df.secondary_axis_filters(5)
        for key, value in expected.items():
            self.assertEqual(seen_parms[0].get(key), value)

    def test_secondary_cursor_advances_by_exactly_one_per_run(self):
        api = FakeApi(tokens_left=60, pages={((1,), 0): ["A1"], ((2,), 0): ["A2"]})
        with mock.patch.object(df, "_fetch_remote_secondary_cursor", return_value=3), \
             mock.patch.object(df, "_upload_remote_secondary_cursor") as mupload:
            df.harvest(api, pages=2, categories=["toys", "kitchen"],
                      resolve_fn=lambda api, cats, wait=True: {"toys": 1, "kitchen": 2})
        mupload.assert_called_once_with(4)  # +1 regardless of pages pulled this run


if __name__ == "__main__":
    unittest.main()
