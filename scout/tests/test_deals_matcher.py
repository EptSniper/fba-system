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
import scoring  # noqa: E402
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


# ---------------------------------------------------------------------------
# apply_verified_matches — mocked db + real scoring math
# ---------------------------------------------------------------------------
class ApplyVerifiedMatchesTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
