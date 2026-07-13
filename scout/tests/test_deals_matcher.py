"""
Tests for scout/deals/matcher.py (Deal Finder Build Plan Prompt D2; Sourcing & Review-Queue
Plan Phase 2.2/2.3, 2026-07-13).

Zero live network calls — Keepa/Anthropic/Supabase are all mocked, matching test_deals_db.py's
and test_keepa_client_guard.py's conventions.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402
import keepa_client  # noqa: E402
import scoring  # noqa: E402
import spapi  # noqa: E402
from deals import matcher  # noqa: E402


# ---------------------------------------------------------------------------
# _attr_agreement
# ---------------------------------------------------------------------------
class AttrAgreementTest(unittest.TestCase):
    def test_brand_match_true_when_both_present_and_equal(self):
        d = {"brand": "Milwaukee", "pack_count": 1, "size_value": None, "size_unit": None}
        c = {"brand": "milwaukee", "pack_count": 1, "size_value": None, "size_unit": None}
        brand, pack, size = matcher._attr_agreement(d, c)
        self.assertTrue(brand)
        self.assertTrue(pack)
        self.assertIsNone(size)

    def test_brand_match_false_when_both_present_and_differ(self):
        d = {"brand": "Nike", "pack_count": 1, "size_value": None, "size_unit": None}
        c = {"brand": "Adidas", "pack_count": 1, "size_value": None, "size_unit": None}
        brand, _, _ = matcher._attr_agreement(d, c)
        self.assertFalse(brand)

    def test_brand_match_none_when_either_side_unknown(self):
        d = {"brand": None, "pack_count": 1, "size_value": None, "size_unit": None}
        c = {"brand": "Adidas", "pack_count": 1, "size_value": None, "size_unit": None}
        brand, _, _ = matcher._attr_agreement(d, c)
        self.assertIsNone(brand)

    def test_pack_mismatch_detected(self):
        d = {"brand": "Crayola", "pack_count": 2, "size_value": None, "size_unit": None}
        c = {"brand": "Crayola", "pack_count": 24, "size_value": None, "size_unit": None}
        _, pack, _ = matcher._attr_agreement(d, c)
        self.assertFalse(pack)

    def test_size_mismatch_detected(self):
        d = {"brand": "Suave", "pack_count": 1, "size_value": 18.0, "size_unit": "fl_oz"}
        c = {"brand": "Suave", "pack_count": 1, "size_value": 30.0, "size_unit": "fl_oz"}
        _, _, size = matcher._attr_agreement(d, c)
        self.assertFalse(size)

    def test_size_match_true_within_float_tolerance(self):
        d = {"brand": "Suave", "pack_count": 1, "size_value": 18.0, "size_unit": "fl_oz"}
        c = {"brand": "Suave", "pack_count": 1, "size_value": 18.0, "size_unit": "fl_oz"}
        _, _, size = matcher._attr_agreement(d, c)
        self.assertTrue(size)


# ---------------------------------------------------------------------------
# composite_confidence
# ---------------------------------------------------------------------------
class CompositeConfidenceTest(unittest.TestCase):
    def test_known_brand_mismatch_vetoes_below_review_regardless_of_similarity(self):
        conf = matcher.composite_confidence("title", brand_match=False, pack_match=True,
                                            size_match=None, similarity=0.99, price_sane=True,
                                            llm_result=None)
        bands = matcher.brain_config.confidence_bands()
        self.assertLess(conf, bands["review"])

    def test_known_pack_mismatch_vetoes_below_review(self):
        conf = matcher.composite_confidence("title", brand_match=True, pack_match=False,
                                            size_match=None, similarity=0.95, price_sane=True,
                                            llm_result=None)
        bands = matcher.brain_config.confidence_bands()
        self.assertLess(conf, bands["review"])

    def test_known_size_mismatch_vetoes_below_review(self):
        conf = matcher.composite_confidence("title", brand_match=True, pack_match=True,
                                            size_match=False, similarity=0.95, price_sane=True,
                                            llm_result=None)
        bands = matcher.brain_config.confidence_bands()
        self.assertLess(conf, bands["review"])

    def test_upc_with_full_attribute_agreement_reaches_auto_accept(self):
        conf = matcher.composite_confidence("upc", brand_match=True, pack_match=True,
                                            size_match=True, similarity=0.9, price_sane=True,
                                            llm_result=None)
        bands = matcher.brain_config.confidence_bands()
        self.assertGreaterEqual(conf, bands["auto_accept"])

    def test_llm_yes_with_pack_match_reaches_review_band_high_confidence(self):
        llm = {"match": "yes", "pack_match": True}
        conf = matcher.composite_confidence("title", brand_match=True, pack_match=True,
                                            size_match=None, similarity=0.8, price_sane=True,
                                            llm_result=llm)
        bands = matcher.brain_config.confidence_bands()
        self.assertGreaterEqual(conf, bands["review"])
        self.assertLess(conf, bands["auto_accept"])  # 0.85 anchor, below the 0.90 default auto-accept

    def test_algorithmic_only_never_reaches_auto_accept(self):
        """The honest scoping cap (module docstring): no title-path match without a real LLM
        verdict can reach auto-accept, no matter how perfect the algorithmic signal looks."""
        conf = matcher.composite_confidence("title", brand_match=True, pack_match=True,
                                            size_match=True, similarity=1.0, price_sane=True,
                                            llm_result=None)
        bands = matcher.brain_config.confidence_bands()
        self.assertLess(conf, bands["auto_accept"])

    def test_price_sanity_flag_lowers_confidence(self):
        kwargs = dict(method="title", brand_match=True, pack_match=True, size_match=None,
                      similarity=0.8, llm_result=None)
        sane = matcher.composite_confidence(price_sane=True, **kwargs)
        insane = matcher.composite_confidence(price_sane=False, **kwargs)
        self.assertLess(insane, sane)


# ---------------------------------------------------------------------------
# route
# ---------------------------------------------------------------------------
class RouteTest(unittest.TestCase):
    def test_bands(self):
        bands = matcher.brain_config.confidence_bands()
        self.assertEqual(matcher.route(bands["auto_accept"]), "auto")
        self.assertEqual(matcher.route(bands["review"]), "review")
        self.assertEqual(matcher.route(bands["review"] - 0.01), "discard")


# ---------------------------------------------------------------------------
# _llm_configured / _llm_verify
# ---------------------------------------------------------------------------
class LlmConfiguredTest(unittest.TestCase):
    def test_placeholder_length_key_is_not_configured(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "placehld"}):
            self.assertFalse(matcher._llm_configured())

    def test_missing_key_is_not_configured(self):
        env = dict(os.environ)
        env.pop("ANTHROPIC_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            self.assertFalse(matcher._llm_configured())

    def test_real_looking_key_is_configured(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-" + "x" * 80}):
            self.assertTrue(matcher._llm_configured())

    def test_llm_verify_returns_none_and_never_raises_when_unconfigured(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "placehld"}):
            result = matcher._llm_verify({"title_raw": "x"}, {"title": "y"})
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# _eligible_for_matching — free SP-API eligibility pre-filter (2026-07-13 wiring)
# ---------------------------------------------------------------------------
class EligibleForMatchingTest(unittest.TestCase):
    def test_unconfigured_spapi_always_eligible_no_ungating(self):
        """An unconfigured SP-API must never block matching (honest no-op)."""
        with patch.object(spapi, "configured", return_value=False), \
             patch.object(spapi, "get_listings_restrictions") as m_restrict:
            result = matcher._eligible_for_matching("B0TEST")
        self.assertEqual(result, (True, False))
        m_restrict.assert_not_called()

    def test_not_eligible_status_drops_the_candidate(self):
        with patch.object(spapi, "configured", return_value=True), \
             patch.object(spapi, "get_listings_restrictions",
                          return_value={"status": "NOT_ELIGIBLE", "reasons": [], "links": []}):
            result = matcher._eligible_for_matching("B0TEST")
        self.assertEqual(result, (False, False))

    def test_approval_required_status_keeps_and_flags_needs_ungating(self):
        with patch.object(spapi, "configured", return_value=True), \
             patch.object(spapi, "get_listings_restrictions",
                          return_value={"status": "APPROVAL_REQUIRED", "reasons": [], "links": ["u"]}):
            result = matcher._eligible_for_matching("B0TEST")
        self.assertEqual(result, (True, True))

    def test_allowed_status_keeps_unflagged(self):
        with patch.object(spapi, "configured", return_value=True), \
             patch.object(spapi, "get_listings_restrictions",
                          return_value={"status": "ALLOWED", "reasons": [], "links": []}):
            result = matcher._eligible_for_matching("B0TEST")
        self.assertEqual(result, (True, False))

    def test_spapi_exception_degrades_to_eligible_never_raises(self):
        with patch.object(spapi, "configured", return_value=True), \
             patch.object(spapi, "get_listings_restrictions",
                          side_effect=Exception("network blip")):
            result = matcher._eligible_for_matching("B0TEST")  # must not raise
        self.assertEqual(result, (True, False))


# ---------------------------------------------------------------------------
# _upc_candidates / _title_candidates — SP-API preferred, Keepa fallback
# (2026-07-13 wiring: free discovery first, eligibility pre-filter BEFORE enrich())
# ---------------------------------------------------------------------------
class UpcCandidatesSpapiWiringTest(unittest.TestCase):
    def test_prefers_spapi_when_configured_and_it_resolves_asins(self):
        deal = {"upc": "012345678905"}
        with patch.object(spapi, "configured", return_value=True), \
             patch.object(spapi, "catalog_lookup_upc",
                          return_value={"available": True, "asins": ["B0SPAPI1"]}) as m_spapi, \
             patch.object(keepa_client, "upc_lookup") as m_keepa_lookup, \
             patch.object(matcher, "_filter_eligible", return_value=(["B0SPAPI1"], {})), \
             patch.object(keepa_client, "enrich", return_value=[{"asin": "B0SPAPI1"}]):
            result = matcher._upc_candidates(deal)
        m_spapi.assert_called_once_with("012345678905")
        m_keepa_lookup.assert_not_called()
        self.assertEqual(result[0]["_discovery_source"], "spapi")
        self.assertEqual(result[0]["_method"], "upc")

    def test_falls_back_to_keepa_when_spapi_unconfigured(self):
        deal = {"upc": "012345678905"}
        with patch.object(spapi, "configured", return_value=False), \
             patch.object(spapi, "catalog_lookup_upc") as m_spapi, \
             patch.object(keepa_client, "upc_lookup",
                          return_value={"012345678905": ["B0KEEPA1"]}) as m_keepa_lookup, \
             patch.object(keepa_client, "enrich", return_value=[{"asin": "B0KEEPA1"}]):
            result = matcher._upc_candidates(deal)
        m_spapi.assert_not_called()
        m_keepa_lookup.assert_called_once()
        self.assertEqual(result[0]["_discovery_source"], "keepa")

    def test_falls_back_to_keepa_when_spapi_configured_but_resolves_nothing(self):
        deal = {"upc": "012345678905"}
        with patch.object(spapi, "configured", return_value=True), \
             patch.object(spapi, "catalog_lookup_upc",
                          return_value={"available": True, "asins": []}), \
             patch.object(keepa_client, "upc_lookup",
                          return_value={"012345678905": ["B0KEEPA1"]}) as m_keepa_lookup, \
             patch.object(matcher, "_filter_eligible", return_value=(["B0KEEPA1"], {})), \
             patch.object(keepa_client, "enrich", return_value=[{"asin": "B0KEEPA1"}]):
            result = matcher._upc_candidates(deal)
        m_keepa_lookup.assert_called_once()
        self.assertEqual(result[0]["_discovery_source"], "keepa")

    def test_eligibility_filter_runs_before_enrich_when_spapi_resolved_candidates(self):
        deal = {"upc": "012345678905"}
        with patch.object(spapi, "configured", return_value=True), \
             patch.object(spapi, "catalog_lookup_upc",
                          return_value={"available": True, "asins": ["B0KEEP", "B0DROP"]}), \
             patch.object(matcher, "_filter_eligible", return_value=(["B0KEEP"], {})) as m_filter, \
             patch.object(keepa_client, "enrich", return_value=[{"asin": "B0KEEP"}]) as m_enrich:
            matcher._upc_candidates(deal)
        # The filter must see the RAW SP-API candidates, and enrich() must only ever see the
        # SURVIVORS -- proof the eligibility pre-filter ran before any Keepa token was spent.
        m_filter.assert_called_once_with(["B0KEEP", "B0DROP"])
        m_enrich.assert_called_once_with(["B0KEEP"], api=None)


class TitleCandidatesSpapiWiringTest(unittest.TestCase):
    def test_prefers_spapi_when_configured_and_it_resolves_asins(self):
        deal = {"title_raw": "Acme Widget"}
        attrs = {"brand": "Acme", "core_title": "Widget"}
        with patch.object(spapi, "configured", return_value=True), \
             patch.object(spapi, "catalog_search_keywords",
                          return_value={"available": True,
                                       "results": [{"asin": "B0SPAPI1", "title": "Acme Widget",
                                                   "brand": "Acme"}]}) as m_spapi, \
             patch.object(keepa_client, "search_by_term") as m_keepa_search, \
             patch.object(matcher, "_filter_eligible", return_value=(["B0SPAPI1"], {})), \
             patch.object(keepa_client, "enrich", return_value=[{"asin": "B0SPAPI1"}]):
            result = matcher._title_candidates(deal, attrs)
        m_spapi.assert_called_once_with("Acme Widget", brand="Acme", limit=matcher.CANDIDATES_PER_DEAL)
        m_keepa_search.assert_not_called()
        self.assertEqual(result[0]["_discovery_source"], "spapi")
        self.assertEqual(result[0]["_method"], "title")

    def test_falls_back_to_keepa_when_spapi_unconfigured(self):
        deal = {"title_raw": "Acme Widget"}
        attrs = {"brand": "Acme", "core_title": "Widget"}
        with patch.object(spapi, "configured", return_value=False), \
             patch.object(spapi, "catalog_search_keywords") as m_spapi, \
             patch.object(keepa_client, "search_by_term", return_value=["B0KEEPA1"]) as m_keepa_search, \
             patch.object(keepa_client, "enrich", return_value=[{"asin": "B0KEEPA1"}]):
            result = matcher._title_candidates(deal, attrs)
        m_spapi.assert_not_called()
        m_keepa_search.assert_called_once()
        self.assertEqual(result[0]["_discovery_source"], "keepa")

    def test_falls_back_to_keepa_when_spapi_configured_but_resolves_nothing(self):
        deal = {"title_raw": "Acme Widget"}
        attrs = {"brand": "Acme", "core_title": "Widget"}
        with patch.object(spapi, "configured", return_value=True), \
             patch.object(spapi, "catalog_search_keywords",
                          return_value={"available": True, "results": []}), \
             patch.object(keepa_client, "search_by_term", return_value=["B0KEEPA1"]) as m_keepa_search, \
             patch.object(matcher, "_filter_eligible", return_value=(["B0KEEPA1"], {})), \
             patch.object(keepa_client, "enrich", return_value=[{"asin": "B0KEEPA1"}]):
            result = matcher._title_candidates(deal, attrs)
        m_keepa_search.assert_called_once()
        self.assertEqual(result[0]["_discovery_source"], "keepa")

    def test_eligibility_filter_runs_before_enrich_when_spapi_resolved_candidates(self):
        deal = {"title_raw": "Acme Widget"}
        attrs = {"brand": "Acme", "core_title": "Widget"}
        with patch.object(spapi, "configured", return_value=True), \
             patch.object(spapi, "catalog_search_keywords",
                          return_value={"available": True,
                                       "results": [{"asin": "B0KEEP"}, {"asin": "B0DROP"}]}), \
             patch.object(matcher, "_filter_eligible", return_value=(["B0KEEP"], {})) as m_filter, \
             patch.object(keepa_client, "enrich", return_value=[{"asin": "B0KEEP"}]) as m_enrich:
            matcher._title_candidates(deal, attrs)
        m_filter.assert_called_once_with(["B0KEEP", "B0DROP"])
        m_enrich.assert_called_once_with(["B0KEEP"], api=None)


# ---------------------------------------------------------------------------
# match_deal — mocked Keepa candidate generation
# ---------------------------------------------------------------------------
class MatchDealTest(unittest.TestCase):
    def test_no_candidates_returns_empty_list(self):
        with patch.object(matcher, "_upc_candidates", return_value=[]), \
             patch.object(matcher, "_title_candidates", return_value=[]):
            result = matcher.match_deal({"title_raw": "Widget", "brand": "Acme"})
        self.assertEqual(result, [])

    def test_title_candidates_used_when_no_upc(self):
        deal = {"title_raw": "Milwaukee M12 Fuel 2-Tool Combo Kit", "brand": "Milwaukee",
               "price_current": 149.99, "upc": None}
        candidate = {"asin": "B0BQ3WJ12K", "title": "Milwaukee M12 Fuel 2-Tool Combo Kit",
                    "brand": "Milwaukee", "price": 190.97, "_method": "title"}
        with patch.object(matcher, "_upc_candidates", return_value=[]), \
             patch.object(matcher, "_title_candidates", return_value=[candidate]), \
             patch.object(matcher, "_llm_verify", return_value=None):
            result = matcher.match_deal(deal)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["asin"], "B0BQ3WJ12K")
        self.assertEqual(result[0]["method"], "title")

    def test_upc_candidates_preferred_over_title_when_present(self):
        deal = {"title_raw": "Widget", "brand": "Acme", "upc": "012345678905"}
        upc_candidate = {"asin": "BUPC0000001", "title": "Widget", "brand": "Acme",
                         "price": 10.0, "_method": "upc"}
        with patch.object(matcher, "_upc_candidates", return_value=[upc_candidate]) as m_upc, \
             patch.object(matcher, "_title_candidates") as m_title:
            matcher.match_deal(deal)
        m_upc.assert_called_once()
        m_title.assert_not_called()

    def test_results_sorted_highest_confidence_first(self):
        deal = {"title_raw": "Acme Widget", "brand": "Acme", "price_current": 10.0}
        good = {"asin": "GOOD", "title": "Acme Widget", "brand": "Acme", "price": 12.0,
               "_method": "title"}
        bad = {"asin": "BAD", "title": "Nike Shoe", "brand": "Nike", "price": 12.0,
              "_method": "title"}
        with patch.object(matcher, "_upc_candidates", return_value=[]), \
             patch.object(matcher, "_title_candidates", return_value=[bad, good]), \
             patch.object(matcher, "_llm_verify", return_value=None):
            result = matcher.match_deal(deal)
        self.assertEqual(result[0]["asin"], "GOOD")
        self.assertGreaterEqual(result[0]["confidence"], result[-1]["confidence"])


# ---------------------------------------------------------------------------
# run() — batch driver, mocked db
# ---------------------------------------------------------------------------
class RunTest(unittest.TestCase):
    def test_dry_run_never_writes(self):
        deals = [{"id": 1, "title_raw": "Acme Widget", "brand": "Acme", "price_current": 10.0}]
        scored = [{"asin": "A1", "confidence": 0.7, "route": "review", "method": "title",
                  "pack_match": True, "llm_reason": "x"}]
        with patch.object(db, "get_deals_by_status", return_value=deals), \
             patch.object(matcher, "match_deal", return_value=scored), \
             patch.object(db, "upsert_deal_match") as m_upsert, \
             patch.object(db, "update_deal_status") as m_status:
            counts = matcher.run(dry_run=True, notify=False)
        m_upsert.assert_not_called()
        m_status.assert_not_called()
        self.assertEqual(counts["review"], 1)
        self.assertEqual(counts["matches_written"], 1)

    def test_discard_route_is_not_written(self):
        deals = [{"id": 1, "title_raw": "x", "brand": "y", "price_current": 1.0}]
        scored = [{"asin": "A1", "confidence": 0.1, "route": "discard", "method": "title",
                  "pack_match": False, "llm_reason": "x"}]
        with patch.object(db, "get_deals_by_status", return_value=deals), \
             patch.object(matcher, "match_deal", return_value=scored), \
             patch.object(db, "upsert_deal_match") as m_upsert, \
             patch.object(db, "update_deal_status") as m_status:
            counts = matcher.run(dry_run=False, notify=False)
        m_upsert.assert_not_called()
        m_status.assert_called_once_with(1, "discarded")
        self.assertEqual(counts["discard"], 1)
        self.assertEqual(counts["matches_written"], 0)

    def test_written_match_marks_deal_matched(self):
        deals = [{"id": 1, "title_raw": "x", "brand": "y", "price_current": 1.0}]
        scored = [{"asin": "A1", "confidence": 0.7, "route": "review", "method": "title",
                  "pack_match": True, "llm_reason": "x"}]
        with patch.object(db, "get_deals_by_status", return_value=deals), \
             patch.object(matcher, "match_deal", return_value=scored), \
             patch.object(db, "upsert_deal_match", return_value=99) as m_upsert, \
             patch.object(db, "update_deal_status") as m_status:
            matcher.run(dry_run=False, notify=False)
        m_upsert.assert_called_once()
        m_status.assert_called_once_with(1, "matched")

    def test_no_candidates_marks_deal_discarded(self):
        deals = [{"id": 1, "title_raw": "x", "brand": "y", "price_current": 1.0}]
        with patch.object(db, "get_deals_by_status", return_value=deals), \
             patch.object(matcher, "match_deal", return_value=[]), \
             patch.object(db, "update_deal_status") as m_status:
            counts = matcher.run(dry_run=False, notify=False)
        m_status.assert_called_once_with(1, "discarded")
        self.assertEqual(counts["no_candidates"], 1)

    def test_discovery_and_dropped_ineligible_telemetry_surfaces_in_run_counts(self):
        """run()'s new discovery_spapi/discovery_keepa/dropped_ineligible counters (2026-07-13)
        must reflect whatever match_deal's candidate generation tallied into the module-global
        _discovery_stats_this_run while producing this deal's matches."""
        deals = [{"id": 1, "title_raw": "Acme Widget", "brand": "Acme", "price_current": 10.0}]

        def fake_match_deal(deal, api=None):
            # Simulates what a real match_deal -> _upc_candidates/_title_candidates call does:
            # tally discovery source + a dropped-ineligible candidate before returning matches.
            matcher._discovery_stats_this_run["spapi"] += 2
            matcher._discovery_stats_this_run["keepa"] += 1
            matcher._discovery_stats_this_run["dropped_ineligible"] += 3
            return [{"asin": "A1", "confidence": 0.7, "route": "review", "method": "title",
                     "pack_match": True, "llm_reason": "x"}]

        with patch.object(db, "get_deals_by_status", return_value=deals), \
             patch.object(matcher, "match_deal", side_effect=fake_match_deal), \
             patch.object(db, "upsert_deal_match", return_value=99), \
             patch.object(db, "update_deal_status"):
            counts = matcher.run(dry_run=False, notify=False)
        self.assertEqual(counts["discovery_spapi"], 2)
        self.assertEqual(counts["discovery_keepa"], 1)
        self.assertEqual(counts["dropped_ineligible"], 3)

    def test_discovery_telemetry_resets_between_run_calls(self):
        """A stale count from a PRIOR run() call must never leak into the next run's reported
        counts -- the module-global _discovery_stats_this_run is zeroed at the top of run()."""
        deals = [{"id": 1, "title_raw": "x", "brand": "y", "price_current": 1.0}]
        matcher._discovery_stats_this_run["spapi"] = 99  # stale from a hypothetical prior run
        with patch.object(db, "get_deals_by_status", return_value=deals), \
             patch.object(matcher, "match_deal", return_value=[]), \
             patch.object(db, "update_deal_status"):
            counts = matcher.run(dry_run=False, notify=False)
        self.assertEqual(counts["discovery_spapi"], 0)


# ---------------------------------------------------------------------------
# apply_verified_matches — mocked db + real scoring math
# ---------------------------------------------------------------------------
class ApplyVerifiedMatchesTest(unittest.TestCase):
    def setUp(self):
        # Test-hygiene regression (2026-07-13): apply_verified_matches() now calls
        # _eligible_for_matching(asin) unconditionally before every write (see the
        # skipped_not_eligible/applied_needs_ungating tests below). spapi.configured() is
        # actually True in this real environment (it only checks non-empty env vars — the
        # placeholders in scout/.env satisfy that), so an unpatched test here would attempt a
        # REAL network call (a Supabase cache read, then a real LWA token POST to Amazon with
        # fake credentials) instead of degrading purely in-process — confirmed live: this class's
        # 6 tests took ~4.7s unpatched vs milliseconds expected for mocked unit tests. Default to
        # the neutral (eligible, no ungating) case; individual tests override this patch to
        # exercise the NOT_ELIGIBLE/APPROVAL_REQUIRED paths specifically.
        self._elig_patch = patch.object(matcher, "_eligible_for_matching", return_value=(True, False))
        self._elig_patch.start()
        self.addCleanup(self._elig_patch.stop)
        # Same issue, second call site: apply_verified_matches() also calls
        # spapi.get_fees_estimate(asin, sell_price) unconditionally when spapi.configured() is
        # True (which it is here) — an unpatched test would attempt a second real network call
        # (this one straight to spapi.py's own _get(), no cache) before falling back to the
        # rule-based estimate. Default to unavailable (the pre-SP-API v1 behavior every existing
        # test here already expects); ApplyVerifiedMatchesRealFeesTest below overrides this to
        # exercise the real-fees path specifically.
        self._fees_patch = patch.object(spapi, "get_fees_estimate", return_value={"available": False})
        self._fees_patch.start()
        self.addCleanup(self._fees_patch.stop)

    def test_a_discount_stack_summing_past_100_percent_never_produces_negative_buy_cost(self):
        """Code review regression (2026-07-13): a bad ai-brain.json discountStack entry (e.g.
        cashbackPct + giftCardPct > 1.0, a plausible manual-data-entry slip since no API
        validates these rates) must never drive buy_cost negative — that would inflate profit
        and blank out ROI via scoring.estimate_oa_profit_roi's own cogs>0 guard."""
        ready = [{"asin": "A1", "human_verdict": "approve",
                 "deals": {"price_current": 10.0, "retailer": "Target", "url": "https://x"}}]
        lead = {"asin": "A1", "source_store": None, "sell_price": 30.0, "category": "toys",
               "features_snapshot": {"weight_lb": 1.0}}
        bad_stack = {"cashback_pct": 0.6, "giftcard_pct": 0.6}  # sums to 1.2 -- over 100%
        with patch.object(db, "get_deal_matches_ready_to_apply", return_value=ready), \
             patch.object(db, "get_lead", return_value=lead), \
             patch.object(matcher.brain_config, "discount_stack", return_value=bad_stack), \
             patch.object(db, "update_lead_source", return_value=True) as m_update:
            matcher.apply_verified_matches(dry_run=False)
        buy_cost = m_update.call_args[0][1]
        profit, roi = m_update.call_args[0][4], m_update.call_args[0][5]
        self.assertGreaterEqual(buy_cost, 0.5)  # clamped to at most a 95% stack, never negative
        self.assertIsNotNone(roi)  # would be None if cogs_fraction went negative

    def test_rejected_match_is_skipped(self):
        ready = [{"asin": "A1", "human_verdict": "reject", "deals": {"price_current": 10.0}}]
        with patch.object(db, "get_deal_matches_ready_to_apply", return_value=ready), \
             patch.object(db, "update_lead_source") as m_update:
            counts = matcher.apply_verified_matches()
        m_update.assert_not_called()
        self.assertEqual(counts["skipped_rejected"], 1)

    def test_no_matching_lead_is_skipped(self):
        ready = [{"asin": "A1", "human_verdict": "approve",
                 "deals": {"price_current": 10.0, "retailer": "Target", "url": "https://x"}}]
        with patch.object(db, "get_deal_matches_ready_to_apply", return_value=ready), \
             patch.object(db, "get_lead", return_value=None), \
             patch.object(db, "update_lead_source") as m_update:
            counts = matcher.apply_verified_matches()
        m_update.assert_not_called()
        self.assertEqual(counts["skipped_no_lead"], 1)

    def test_already_sourced_lead_is_skipped(self):
        ready = [{"asin": "A1", "human_verdict": "approve",
                 "deals": {"price_current": 10.0, "retailer": "Target", "url": "https://x"}}]
        lead = {"asin": "A1", "source_store": "Walmart", "sell_price": 30.0}
        with patch.object(db, "get_deal_matches_ready_to_apply", return_value=ready), \
             patch.object(db, "get_lead", return_value=lead), \
             patch.object(db, "update_lead_source") as m_update:
            counts = matcher.apply_verified_matches()
        m_update.assert_not_called()
        self.assertEqual(counts["skipped_already_sourced"], 1)

    def test_verified_match_backfills_real_cost_and_recomputed_profit(self):
        ready = [{"asin": "A1", "human_verdict": "approve",
                 "deals": {"price_current": 10.0, "retailer": "Target", "url": "https://x"}}]
        lead = {"asin": "A1", "source_store": None, "sell_price": 30.0, "category": "toys",
               "features_snapshot": {"weight_lb": 1.0}}
        with patch.object(db, "get_deal_matches_ready_to_apply", return_value=ready), \
             patch.object(db, "get_lead", return_value=lead), \
             patch.object(db, "update_lead_source", return_value=True) as m_update:
            counts = matcher.apply_verified_matches(dry_run=False)
        self.assertEqual(counts["applied"], 1)
        m_update.assert_called_once()
        args = m_update.call_args[0]
        self.assertEqual(args[0], "A1")
        self.assertEqual(args[1], 10.0)  # buy_cost == deal price_current, no discount stack configured
        self.assertEqual(args[2], "Target")
        # profit/roi should match calling scoring.estimate_oa_profit_roi directly with the same inputs
        expected_profit, expected_roi = scoring.estimate_oa_profit_roi(
            30.0, 1.0, cogs_fraction=10.0 / 30.0, category="toys")
        self.assertEqual(args[4], expected_profit)
        self.assertEqual(args[5], expected_roi)

    def test_not_eligible_asin_is_skipped_never_backfilled(self):
        """Code review regression (2026-07-13, confirmed by an independent verify pass): a
        NOT_ELIGIBLE ASIN must never get real-looking buy_cost/profit/roi written onto its
        lead — it can't be sold at all, so backfilling economics for it would be misleading."""
        ready = [{"asin": "A1", "human_verdict": "approve",
                 "deals": {"price_current": 10.0, "retailer": "Target", "url": "https://x"}}]
        with patch.object(matcher, "_eligible_for_matching", return_value=(False, False)), \
             patch.object(db, "get_deal_matches_ready_to_apply", return_value=ready), \
             patch.object(db, "get_lead") as m_get_lead, \
             patch.object(db, "update_lead_source") as m_update:
            counts = matcher.apply_verified_matches(dry_run=False)
        m_get_lead.assert_not_called()  # never even looks up the lead for a NOT_ELIGIBLE ASIN
        m_update.assert_not_called()
        self.assertEqual(counts["skipped_not_eligible"], 1)
        self.assertEqual(counts["applied"], 0)

    def test_approval_required_match_still_backfills_but_tags_gated_status(self):
        """The economics ARE real for an APPROVAL_REQUIRED match — it still gets backfilled —
        but leads.gated_status must be set so a human sees it isn't immediately buyable."""
        ready = [{"asin": "A1", "human_verdict": "approve",
                 "deals": {"price_current": 10.0, "retailer": "Target", "url": "https://x"}}]
        lead = {"asin": "A1", "source_store": None, "sell_price": 30.0, "category": "toys",
               "features_snapshot": {"weight_lb": 1.0}}
        with patch.object(matcher, "_eligible_for_matching", return_value=(True, True)), \
             patch.object(db, "get_deal_matches_ready_to_apply", return_value=ready), \
             patch.object(db, "get_lead", return_value=lead), \
             patch.object(db, "update_lead_source", return_value=True) as m_update:
            counts = matcher.apply_verified_matches(dry_run=False)
        self.assertEqual(counts["applied"], 1)
        self.assertEqual(counts["applied_needs_ungating"], 1)
        m_update.assert_called_once()
        self.assertEqual(m_update.call_args[1].get("gated_status"), "approval_required")

    def test_eligible_match_writes_no_gated_status(self):
        ready = [{"asin": "A1", "human_verdict": "approve",
                 "deals": {"price_current": 10.0, "retailer": "Target", "url": "https://x"}}]
        lead = {"asin": "A1", "source_store": None, "sell_price": 30.0, "category": "toys",
               "features_snapshot": {"weight_lb": 1.0}}
        with patch.object(db, "get_deal_matches_ready_to_apply", return_value=ready), \
             patch.object(db, "get_lead", return_value=lead), \
             patch.object(db, "update_lead_source", return_value=True) as m_update:
            counts = matcher.apply_verified_matches(dry_run=False)
        self.assertEqual(counts["applied_needs_ungating"], 0)
        self.assertIsNone(m_update.call_args[1].get("gated_status"))

    def test_dry_run_computes_but_does_not_write(self):
        ready = [{"asin": "A1", "human_verdict": "approve",
                 "deals": {"price_current": 10.0, "retailer": "Target", "url": "https://x"}}]
        lead = {"asin": "A1", "source_store": None, "sell_price": 30.0, "category": "toys",
               "features_snapshot": {}}
        with patch.object(db, "get_deal_matches_ready_to_apply", return_value=ready), \
             patch.object(db, "get_lead", return_value=lead), \
             patch.object(db, "update_lead_source") as m_update:
            counts = matcher.apply_verified_matches(dry_run=True)
        m_update.assert_not_called()
        self.assertEqual(counts["applied"], 1)


# ---------------------------------------------------------------------------
# apply_verified_matches — real SP-API fees preferred over the rule-based estimate
# (2026-07-13 wiring)
# ---------------------------------------------------------------------------
class ApplyVerifiedMatchesRealFeesTest(unittest.TestCase):
    def setUp(self):
        # Same test-hygiene fix as ApplyVerifiedMatchesTest.setUp: these tests patch
        # spapi.configured() to True to exercise the real-fees path, which also means an
        # unpatched _eligible_for_matching would make a real spapi.get_listings_restrictions
        # network call. Every test here cares about the FEE path, not eligibility, so default
        # to the neutral (eligible, no ungating) case throughout.
        self._elig_patch = patch.object(matcher, "_eligible_for_matching", return_value=(True, False))
        self._elig_patch.start()
        self.addCleanup(self._elig_patch.stop)

    def test_uses_real_spapi_fees_when_available_and_tallies_fee_source_spapi(self):
        ready = [{"asin": "A1", "human_verdict": "approve",
                 "deals": {"price_current": 10.0, "retailer": "Target", "url": "https://x"}}]
        lead = {"asin": "A1", "source_store": None, "sell_price": 30.0, "category": "toys",
               "features_snapshot": {"weight_lb": 1.0}}
        fees = {"available": True, "referral_fee": 3.0, "fba_fee": 5.5}
        with patch.object(db, "get_deal_matches_ready_to_apply", return_value=ready), \
             patch.object(db, "get_lead", return_value=lead), \
             patch.object(spapi, "configured", return_value=True), \
             patch.object(spapi, "get_fees_estimate", return_value=fees) as m_fees, \
             patch.object(scoring, "estimate_oa_profit_roi_real_fees",
                          return_value=(11.11, 1.111)) as m_real, \
             patch.object(scoring, "estimate_oa_profit_roi") as m_estimate, \
             patch.object(db, "update_lead_source", return_value=True) as m_update:
            counts = matcher.apply_verified_matches(dry_run=False)
        m_fees.assert_called_once_with("A1", 30.0)
        m_real.assert_called_once_with(30.0, 10.0, 3.0, 5.5, weight_lb=1.0)
        m_estimate.assert_not_called()
        self.assertEqual(counts["fee_source_spapi"], 1)
        self.assertEqual(counts["fee_source_estimate"], 0)
        args = m_update.call_args[0]
        self.assertEqual(args[4], 11.11)
        self.assertEqual(args[5], 1.111)

    def test_falls_back_to_rule_based_estimate_when_spapi_fees_unavailable(self):
        ready = [{"asin": "A1", "human_verdict": "approve",
                 "deals": {"price_current": 10.0, "retailer": "Target", "url": "https://x"}}]
        lead = {"asin": "A1", "source_store": None, "sell_price": 30.0, "category": "toys",
               "features_snapshot": {"weight_lb": 1.0}}
        with patch.object(db, "get_deal_matches_ready_to_apply", return_value=ready), \
             patch.object(db, "get_lead", return_value=lead), \
             patch.object(spapi, "configured", return_value=True), \
             patch.object(spapi, "get_fees_estimate",
                          return_value={"available": False, "reason": "x"}) as m_fees, \
             patch.object(scoring, "estimate_oa_profit_roi_real_fees") as m_real, \
             patch.object(db, "update_lead_source", return_value=True) as m_update:
            counts = matcher.apply_verified_matches(dry_run=False)
        m_fees.assert_called_once()
        m_real.assert_not_called()
        self.assertEqual(counts["fee_source_spapi"], 0)
        self.assertEqual(counts["fee_source_estimate"], 1)
        expected_profit, expected_roi = scoring.estimate_oa_profit_roi(
            30.0, 1.0, cogs_fraction=10.0 / 30.0, category="toys")
        args = m_update.call_args[0]
        self.assertEqual(args[4], expected_profit)
        self.assertEqual(args[5], expected_roi)

    def test_spapi_exception_falls_back_to_estimate_never_raises(self):
        ready = [{"asin": "A1", "human_verdict": "approve",
                 "deals": {"price_current": 10.0, "retailer": "Target", "url": "https://x"}}]
        lead = {"asin": "A1", "source_store": None, "sell_price": 30.0, "category": "toys",
               "features_snapshot": {"weight_lb": 1.0}}
        with patch.object(db, "get_deal_matches_ready_to_apply", return_value=ready), \
             patch.object(db, "get_lead", return_value=lead), \
             patch.object(spapi, "configured", return_value=True), \
             patch.object(spapi, "get_fees_estimate", side_effect=Exception("network blip")), \
             patch.object(db, "update_lead_source", return_value=True) as m_update:
            counts = matcher.apply_verified_matches(dry_run=False)  # must not raise
        self.assertEqual(counts["fee_source_spapi"], 0)
        self.assertEqual(counts["fee_source_estimate"], 1)
        m_update.assert_called_once()


if __name__ == "__main__":
    unittest.main()
