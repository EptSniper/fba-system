"""
Unit tests for scout_pro's rules-first safety core: gates.py + scoring.py.

These two modules encode the non-negotiable "never buy" gates and the transparent
0-100 rule score that exists even with zero labels and no trained model. They import
only `config` (no DB / Keepa / sklearn), so this suite runs with the standard library
alone — no infrastructure, no `pip install`:

    python tests/test_gates_scoring.py      # standalone
    python -m unittest discover tests       # via unittest
    python -m pytest tests/                 # if pytest is installed
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brands  # noqa: E402
import config  # noqa: E402
import gates  # noqa: E402
import scoring  # noqa: E402


def healthy_features(**kw):
    """A candidate that clears every default gate and scores well."""
    f = {
        "asin": "B0PASS",
        "price": 30.0,
        "est_sales": 300,
        "review_count": 200,
        "rating": 4.1,
        "weight_lb": 0.8,
        "offer_count": 8,
        "margin_est": 0.30,
    }
    f.update(kw)
    return f


def clean_snapshot(**kw):
    s = {"title": "Stainless Steel Water Bottle 20oz", "category_id": "Kitchen", "brand": "Generic"}
    s.update(kw)
    return s


class TestHardGates(unittest.TestCase):
    def test_healthy_candidate_passes(self):
        passed, reasons = gates.hard_gates(healthy_features(), clean_snapshot(), lead_time_days=30)
        self.assertTrue(passed)
        self.assertEqual(reasons, [])

    def test_margin_below_floor_is_rejected(self):
        passed, reasons = gates.hard_gates(healthy_features(margin_est=0.05), clean_snapshot())
        self.assertFalse(passed)
        self.assertTrue(any("margin" in r for r in reasons))

    def test_offer_crowding_is_rejected(self):
        passed, reasons = gates.hard_gates(healthy_features(offer_count=40), clean_snapshot())
        self.assertFalse(passed)
        self.assertTrue(any("crowding" in r for r in reasons))

    def test_oversize_weight_is_rejected(self):
        passed, reasons = gates.hard_gates(healthy_features(weight_lb=9.0), clean_snapshot())
        self.assertFalse(passed)
        self.assertTrue(any("oversize" in r or "weight" in r for r in reasons))

    def test_impossible_lead_time_is_rejected(self):
        passed, reasons = gates.hard_gates(healthy_features(), clean_snapshot(), lead_time_days=120)
        self.assertFalse(passed)
        self.assertTrue(any("lead time" in r for r in reasons))

    def test_compliance_term_in_title_is_rejected(self):
        snap = clean_snapshot(title="9V Lithium Battery 4-pack")
        passed, reasons = gates.hard_gates(healthy_features(), snap)
        self.assertFalse(passed)
        self.assertTrue(any("compliance" in r for r in reasons))

    def test_missing_fields_do_not_crash_or_falsely_reject(self):
        # A sparse row (everything None) should pass gates rather than throw — gates only
        # reject on present, out-of-bound values.
        sparse = {"asin": "B0SPARSE", "margin_est": None, "offer_count": None, "weight_lb": None}
        passed, reasons = gates.hard_gates(sparse, clean_snapshot(), lead_time_days=None)
        self.assertTrue(passed)
        self.assertEqual(reasons, [])

    def test_multiple_violations_accumulate(self):
        bad = healthy_features(margin_est=0.01, offer_count=99, weight_lb=20.0)
        passed, reasons = gates.hard_gates(bad, clean_snapshot(), lead_time_days=999)
        self.assertFalse(passed)
        self.assertGreaterEqual(len(reasons), 4)


class TestComplianceRisk(unittest.TestCase):
    def test_clean_row_has_no_risk(self):
        risk, hits = gates.compliance_risk(clean_snapshot())
        self.assertEqual(risk, 0.0)
        self.assertEqual(hits, [])

    def test_forbidden_term_is_flagged(self):
        risk, hits = gates.compliance_risk(clean_snapshot(title="Herbal Supplement Capsules"))
        self.assertEqual(risk, 1.0)
        self.assertIn("supplement", hits)

    def test_case_insensitive_match(self):
        risk, hits = gates.compliance_risk(clean_snapshot(brand="FLAMMABLE Co"))
        self.assertEqual(risk, 1.0)
        self.assertIn("flammable", hits)


class TestRuleScore(unittest.TestCase):
    def test_score_within_bounds(self):
        score, reason = scoring.rule_score(healthy_features())
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 100.0)
        self.assertIn("/100", reason)

    def test_healthy_outscores_poor(self):
        good, _ = scoring.rule_score(healthy_features())
        poor, _ = scoring.rule_score(
            healthy_features(price=120.0, est_sales=5, review_count=8000, rating=4.9, weight_lb=4.0, offer_count=40, margin_est=0.03)
        )
        self.assertGreater(good, poor)

    def test_none_features_give_partial_credit_not_crash(self):
        score, _ = scoring.rule_score(
            {"price": None, "est_sales": None, "review_count": None, "rating": None,
             "weight_lb": None, "offer_count": None, "margin_est": None}
        )
        # All-None falls back to 25% of every weight -> a low but valid, non-zero score.
        self.assertGreater(score, 0.0)
        self.assertLess(score, 50.0)

    def test_criteria_override_changes_score(self):
        f = healthy_features(price=80.0)  # outside default 15-50 band
        default_score, _ = scoring.rule_score(f)
        widened, _ = scoring.rule_score(f, criteria={**config.CRITERIA, "price_min": 15.0, "price_max": 100.0})
        # Widening the band so 80 is in-range should not lower the price contribution.
        self.assertGreaterEqual(widened, default_score)


def oa_candidate(**kw):
    """A healthy OA candidate (steady price, steady offers, known-good brand, 3P Buy Box).
    Mirrors scout/tests/test_scoring.py's `_base()` fixture."""
    p = {
        "asin": "B0TEST", "price": 30.0, "weight_lb": 1.0, "sales_rank": 25000,
        "est_sales": 200, "offers": 6, "buybox_seller": "A1SELLER", "brand": "Jellycat",
        "avg_price_90": 29.0, "avg_offers_90": 6,
    }
    p.update(kw)
    return p


class TestOACriteriaFromBrain(unittest.TestCase):
    """ai-brain.json is the single source of truth for OA criteria/guards."""

    def test_criteria_loaded_from_brain(self):
        self.assertEqual(config.CRITERIA_OA["bsr_max"], 200000)
        self.assertAlmostEqual(config.CRITERIA_OA["min_roi"], 0.30)
        self.assertAlmostEqual(config.CRITERIA_OA["min_profit_per_unit"], 3.0)
        self.assertAlmostEqual(config.CRITERIA_OA["price_min"], 8.0)
        self.assertAlmostEqual(config.CRITERIA_OA["price_max"], 60.0)
        self.assertEqual(config.CRITERIA_OA["min_offers"], 3)
        self.assertEqual(config.CRITERIA_OA["max_offers"], 25)
        self.assertEqual(config.CRITERIA_OA["min_monthly_sales"], 50)

    def test_guard_ratios_loaded_from_brain(self):
        self.assertAlmostEqual(config.OA_PRICE_SPIKE_RATIO, 1.5)
        self.assertAlmostEqual(config.OA_OFFERS_RISE_RATIO, 1.4)
        self.assertAlmostEqual(config.OA_AMAZON_SHARE_MAX, 0.20)


class TestOAHardGates(unittest.TestCase):
    def test_healthy_candidate_passes(self):
        passed, reasons = gates.oa_hard_gates(oa_candidate())
        self.assertTrue(passed)
        self.assertEqual(reasons, [])

    def test_amazon_buybox_is_hard_rejected(self):
        passed, reasons = gates.oa_hard_gates(oa_candidate(buybox_seller=config.AMAZON_SELLER_ID))
        self.assertFalse(passed)
        self.assertTrue(any("buy box" in r.lower() for r in reasons))

    def test_amazon_buybox_share_at_20pct_is_hard_rejected(self):
        passed, reasons = gates.oa_hard_gates(oa_candidate(amazon_bb_share=0.20))
        self.assertFalse(passed)
        self.assertTrue(any("wins the buy box" in r.lower() for r in reasons))

    def test_amazon_buybox_share_at_10pct_not_rejected_but_penalized(self):
        minor = oa_candidate(amazon_bb_share=0.10)
        passed, reasons = gates.oa_hard_gates(minor)
        self.assertTrue(passed)
        self.assertEqual(reasons, [])
        # Not a hard reject, but scoring should still penalize + flag it.
        self.assertLess(scoring.oa_rule_score(minor)[0], scoring.oa_rule_score(oa_candidate())[0])

    def test_avoid_brand_is_hard_rejected(self):
        passed, reasons = gates.oa_hard_gates(oa_candidate(brand="Nike"))
        self.assertFalse(passed)
        self.assertTrue(any("brand" in r.lower() for r in reasons))

    def test_ip_cliff_is_hard_rejected(self):
        cliff = oa_candidate(offers=1, avg_offers_90=30)
        passed, reasons = gates.oa_hard_gates(cliff)
        self.assertFalse(passed)
        self.assertTrue(any("cliff" in r.lower() for r in reasons))

    def test_healthy_offers_are_not_a_cliff(self):
        self.assertFalse(gates._ip_cliff(oa_candidate()))
        passed, _ = gates.oa_hard_gates(oa_candidate())
        self.assertTrue(passed)

    def test_no_price_is_hard_rejected(self):
        passed, reasons = gates.oa_hard_gates(oa_candidate(price=None))
        self.assertFalse(passed)
        self.assertTrue(any("no price" in r.lower() for r in reasons))


class TestOARuleScore(unittest.TestCase):
    def test_good_candidate_scores_high(self):
        score, _, reason = scoring.oa_rule_score(oa_candidate())
        self.assertGreaterEqual(score, 90)
        self.assertIn("/100", reason)

    def test_price_spike_penalized_and_flagged(self):
        spike = oa_candidate(avg_price_90=10.0)  # 30 >> 10 * 1.5
        self.assertTrue(scoring._price_spike(spike))
        base_score = scoring.oa_rule_score(oa_candidate())[0]
        spike_score, _, reason = scoring.oa_rule_score(spike)
        self.assertLess(spike_score, base_score)
        self.assertIn("price-spike", reason)

    def test_offers_rising_penalized_and_flagged(self):
        rising = oa_candidate(offers=20, avg_offers_90=6)  # 20 >> 6 * 1.4
        self.assertTrue(scoring._offers_rising(rising))
        base_score = scoring.oa_rule_score(oa_candidate())[0]
        rising_score, _, reason = scoring.oa_rule_score(rising)
        self.assertLess(rising_score, base_score)
        self.assertIn("offers-rising", reason)

    def test_worst_case_loss_penalized_and_flagged(self):
        wc = oa_candidate(price_low_90=9.0)  # loses money at the 90-day low
        loss = scoring._worst_case_loss(wc)
        self.assertIsNotNone(loss)
        self.assertGreater(loss, 2)
        base_score = scoring.oa_rule_score(oa_candidate())[0]
        wc_score, _, reason = scoring.oa_rule_score(wc)
        self.assertLess(wc_score, base_score)
        self.assertIn("worst-case", reason)

    def test_no_featured_offer_penalized_and_flagged(self):
        nb = oa_candidate(has_buybox=False)
        self.assertTrue(scoring._no_featured_offer(nb))
        base_score = scoring.oa_rule_score(oa_candidate())[0]
        nb_score, _, reason = scoring.oa_rule_score(nb)
        self.assertLess(nb_score, base_score)
        self.assertIn("no-BuyBox", reason)

    def test_generic_brand_penalized(self):
        base_score = scoring.oa_rule_score(oa_candidate())[0]
        generic_score = scoring.oa_rule_score(oa_candidate(brand="Generic"))[0]
        self.assertLess(generic_score, base_score)

    def test_friendly_brand_bonus(self):
        # Use a candidate that doesn't already cap at 100 (and doesn't trip any other
        # flag) so the +5 friendly-brand nudge is cleanly visible.
        weaker = oa_candidate(sales_rank=250000, est_sales=40, offers=22, avg_offers_90=22)
        friendly_score = scoring.oa_rule_score({**weaker, "brand": "Jellycat"})[0]
        neutral_score = scoring.oa_rule_score({**weaker, "brand": "Some Neutral Co"})[0]
        self.assertGreater(friendly_score, neutral_score)
        self.assertAlmostEqual(friendly_score - neutral_score, 5.0)


class TestOABrands(unittest.TestCase):
    def test_brand_helpers(self):
        self.assertTrue(brands.is_avoided("Nike"))
        self.assertFalse(brands.is_avoided("Jellycat"))
        self.assertTrue(brands.is_friendly("Jellycat"))
        self.assertFalse(brands.is_friendly("Pineapple Co"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
