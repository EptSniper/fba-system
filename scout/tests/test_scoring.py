"""
Unit tests for the OA rater. Runnable two ways:
    python tests/test_scoring.py        # standalone (prints PASS/FAIL)
    python -m pytest tests/             # if pytest is installed
Locks in the scoring, hard gates, brand logic, and the price-spike / offers-rising guards.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brands  # noqa: E402
import config  # noqa: E402
import scoring  # noqa: E402


def _base(**kw):
    """A healthy OA candidate (steady price, steady offers, known-good brand, 3P Buy Box)."""
    p = {
        "asin": "B0TEST", "price": 30.0, "weight_lb": 1.0, "sales_rank": 25000,
        "est_sales": 200, "offers": 6, "buybox_seller": "A1SELLER", "brand": "Jellycat",
        "avg_price_90": 29.0, "avg_offers_90": 6,
    }
    p.update(kw)
    return p


def test_profit_roi_positive():
    profit, roi = scoring.estimate_oa_profit_roi(30.0, 1.0)
    assert profit and profit > 0 and roi and roi > 0.30


def test_profit_roi_none_without_price():
    assert scoring.estimate_oa_profit_roi(None, 1.0) == (None, None)


def test_good_product_scores_high():
    score, _, _ = scoring.score_product_oa(_base())
    assert score >= 90


def test_amazon_buybox_is_hard_rejected():
    assert scoring.oa_hard_reject(_base(buybox_seller=config.AMAZON_SELLER_ID))


def test_no_price_is_hard_rejected():
    assert scoring.oa_hard_reject(_base(price=None))


def test_avoid_brand_is_hard_rejected():
    assert scoring.oa_hard_reject(_base(brand="Nike"))


def test_good_candidate_passes_hard_gate():
    assert scoring.oa_hard_reject(_base()) is None


def test_oa_hard_reject_has_exactly_these_5_conditions():
    """Enumeration guard (Code Review 2026-07-02, Finding S4): oa_hard_reject() is the ONLY
    unconditional reject path (applies regardless of score) — everything else in scoring.py
    (the 6 scored_checks, brand/price/offers adjustments) is a point penalty, never a reject on
    its own. If a 6th hard-reject condition is ever added or one of these 5 removed, this test
    should be updated deliberately, not silently drift."""
    amazon_buybox = _base(buybox_seller=config.AMAZON_SELLER_ID)
    amazon_rotation = _base(amazon_bb_share=0.40)
    avoid_brand = _base(brand="Nike")
    ip_cliff = _base(offers=1, avg_offers_90=30)
    no_price = _base(price=None)
    healthy = _base()

    assert scoring.oa_hard_reject(amazon_buybox) is not None
    assert scoring.oa_hard_reject(amazon_rotation) is not None
    assert scoring.oa_hard_reject(avoid_brand) is not None
    assert scoring.oa_hard_reject(ip_cliff) is not None
    assert scoring.oa_hard_reject(no_price) is not None
    assert scoring.oa_hard_reject(healthy) is None

    # None of these 5 appear anywhere in scored_checks — they are a wholly separate mechanism.
    scored_check_names = {c["name"] for c in scoring.explain_oa(healthy)["scored_checks"]}
    assert scored_check_names == {"bsr", "sales", "offers", "roi", "profit", "buybox"}


def test_price_spike_detected_and_penalized():
    spike = _base(avg_price_90=10.0)  # 30 >> 10 * 1.5
    assert scoring._price_spike(spike)
    assert scoring.score_product_oa(spike)[0] < scoring.score_product_oa(_base())[0]
    assert any("spike" in f.lower() for f in scoring.risk_flags_oa(spike))


def test_offers_rising_detected_and_penalized():
    rising = _base(offers=20, avg_offers_90=6)  # 20 >> 6 * 1.4
    assert scoring._offers_rising(rising)
    assert scoring.score_product_oa(rising)[0] < scoring.score_product_oa(_base())[0]
    assert any("rising" in f.lower() for f in scoring.risk_flags_oa(rising))


def test_brand_helpers():
    assert brands.is_avoided("Nike") and not brands.is_avoided("Jellycat")
    assert brands.is_friendly("Jellycat") and not brands.is_avoided("Pineapple Co")


def test_criteria_loaded_from_brain():
    # Criteria are the single source of truth in ai-brain.json.
    assert config.CRITERIA_OA["bsr_max"] == 200000
    assert abs(config.CRITERIA_OA["min_roi"] - 0.30) < 1e-9


def test_amazon_share_threshold_default():
    assert abs(config.OA_AMAZON_SHARE_MAX - 0.20) < 1e-9


def test_amazon_buybox_rotation_is_hard_rejected():
    # Amazon wins the Buy Box 40% of the time (>= 0.20) -> reject even though a 3P holds it now.
    rot = _base(amazon_bb_share=0.40)
    assert scoring._amazon_rotates_buybox(rot)
    assert scoring.oa_hard_reject(rot)


def test_amazon_buybox_minor_share_penalized_and_flagged():
    minor = _base(amazon_bb_share=0.10)  # below the reject bar, above 0 -> penalty + flag, not reject
    assert not scoring._amazon_rotates_buybox(minor)
    assert scoring.oa_hard_reject(minor) is None
    assert scoring.score_product_oa(minor)[0] < scoring.score_product_oa(_base())[0]
    assert any("amazon" in f.lower() and "buy box" in f.lower() for f in scoring.risk_flags_oa(minor))


def test_no_amazon_share_is_unpenalized():
    assert scoring._amazon_share(_base()) is None
    assert scoring.oa_hard_reject(_base()) is None


def test_ip_cliff_is_hard_rejected():
    # Offer count collapsed 30 -> 1: likely brand IP complaints -> account-health risk (reject).
    cliff = _base(offers=1, avg_offers_90=30)
    assert scoring._ip_cliff(cliff)
    assert scoring.oa_hard_reject(cliff)
    assert any("cliff" in f.lower() for f in scoring.risk_flags_oa(cliff))


def test_healthy_offers_are_not_a_cliff():
    assert not scoring._ip_cliff(_base())


def test_generic_brand_penalized():
    assert scoring.score_product_oa(_base(brand="Generic"))[0] < scoring.score_product_oa(_base())[0]


def test_worst_case_low_price_flagged_and_penalized():
    # At a 90-day low Buy-Box price of $9 the deal loses money -> penalty + flag.
    wc = _base(price_low_90=9.0)
    loss = scoring._worst_case_loss(wc)
    assert loss is not None and loss > 2
    assert scoring.score_product_oa(wc)[0] < scoring.score_product_oa(_base())[0]
    assert any("worst case" in f.lower() for f in scoring.risk_flags_oa(wc))


def test_no_featured_offer_penalized():
    nb = _base(has_buybox=False)
    assert scoring._no_featured_offer(nb)
    assert scoring.score_product_oa(nb)[0] < scoring.score_product_oa(_base())[0]
    assert any("buy box" in f.lower() or "featured offer" in f.lower() for f in scoring.risk_flags_oa(nb))


def test_price_out_of_band_penalized_and_flagged():
    # SOURCING_AND_QUEUE_PLAN.md Phase 1.4: CRITERIA_OA['price_min']/['price_max'] ($8-$60) was
    # documented as a pass gate but scoring.py's OA path never checked it at all -- live-
    # reproduced leads at $80-$191 scored 72-91 with zero price signal.
    over = _base(price=190.0)
    assert scoring.score_product_oa(over)[0] < scoring.score_product_oa(_base())[0]
    assert any("price" in f.lower() and "band" in f.lower() for f in scoring.risk_flags_oa(over))
    ex = scoring.explain_oa(over)
    assert any(a["name"] == "price-out-of-band" for a in ex["adjustments"])


def test_price_out_of_band_is_soft_never_a_hard_reject():
    # Matches deal-analyzer.tsx's own design (Finding CS7): out-of-band price demotes score,
    # it must never appear in oa_hard_reject's unconditional 5 reasons.
    over = _base(price=190.0)
    assert scoring.oa_hard_reject(over) is None


def _price_adj_points(price):
    adjustments = scoring.explain_oa(_base(price=price))["adjustments"]
    match = [a["points"] for a in adjustments if a["name"] == "price-out-of-band"]
    return match[0] if match else 0.0


def test_price_out_of_band_penalty_is_graduated_not_flat():
    # A narrow miss ($1 under the $8 floor) must cost far less than a wild outlier ($190) --
    # deal-exam regression, 2026-07-13: a flat penalty crushed real narrator-endorsed deals
    # (a $7/257%-ROI item, an $84 item, a $96.50 item all called "healthy"/"good" in the
    # sourced transcripts) exactly as hard as a genuinely bad $190 candidate. Isolates the
    # price-out-of-band adjustment itself (not the total score, which also swings with price
    # via the derived profit/roi components).
    narrow_miss = _price_adj_points(7.0)
    wild_outlier = _price_adj_points(190.0)
    assert narrow_miss > wild_outlier  # both negative-or-zero; narrow miss is the smaller penalty
    assert narrow_miss > -1.0  # a $1 miss should barely register
    assert wild_outlier < -5.0  # a genuinely extreme outlier should still draw a real penalty


def test_price_in_band_gets_no_penalty():
    ex = scoring.explain_oa(_base(price=20.0))
    assert not any(a["name"] == "price-out-of-band" for a in ex["adjustments"])
    assert not any("target price band" in f.lower() for f in scoring.risk_flags_oa(_base(price=20.0)))


# --- Phase 1, Prompt 1.2: category fees, grocery ROI exception, offer-band bonus, explain-why ---

def test_category_fee_selection():
    # A recognized category (grocery, 8% referral AT/BELOW its $15 price band — Finding CS6)
    # should differ from the flat-15% no-category baseline at a price inside that band; an
    # unrecognized category must fall back to the 15% default rate.
    profit_default, _ = scoring.estimate_oa_profit_roi(12.0, 1.0)
    profit_grocery, _ = scoring.estimate_oa_profit_roi(12.0, 1.0, category="grocery")
    profit_unknown, _ = scoring.estimate_oa_profit_roi(12.0, 1.0, category="Some Made-Up Category")
    assert profit_grocery > profit_default, "grocery's 8% referral (<=$15 band) should mean MORE profit than flat 15%"
    assert round(profit_unknown, 2) == round(profit_default, 2), "unknown category must fall back to the 15% default rate"


def test_grocery_referral_rate_is_banded_by_price():
    """Regression for Code Review 2026-07-02, Finding CS6: grocery's referral rate used to be a
    flat 8% regardless of price, overstating profit/ROI above $15 (the real Amazon rule is 8%
    at/below $15, 15% above). Below the threshold must use the cheaper rate; above it must match
    the flat 15% default exactly (not still get the 8% discount)."""
    profit_below, _ = scoring.estimate_oa_profit_roi(12.0, 1.0, category="grocery")
    profit_default_below, _ = scoring.estimate_oa_profit_roi(12.0, 1.0)
    assert profit_below > profit_default_below

    profit_above, _ = scoring.estimate_oa_profit_roi(30.0, 1.0, category="grocery")
    profit_default_above, _ = scoring.estimate_oa_profit_roi(30.0, 1.0)
    assert round(profit_above, 2) == round(profit_default_above, 2), \
        "above the $15 threshold, grocery must charge the same 15% as the default rate, not still 8%"


def test_category_fee_floor_applies():
    # At a very low price, the $0.30 referral floor must still be respected even when the
    # category rate alone would compute a smaller referral fee.
    referral_uncapped = 1.0 * config.REFERRAL_RATES["grocery"]
    assert referral_uncapped < config.MIN_REFERRAL_FEE
    profit_floor, _ = scoring.estimate_oa_profit_roi(1.0, 0.5, category="grocery")
    profit_if_uncapped = (1.0 - referral_uncapped
                          - scoring.estimate_fulfillment_fee(0.5) * (1 + config.FUEL_SURCHARGE)
                          - 0.5 - config.OA_PREP_COST - scoring.estimate_inbound_shipping(0.5))
    assert profit_floor < profit_if_uncapped, "the $0.30 floor should cost MORE than the uncapped category rate would"


def test_inbound_shipping_is_subtracted_from_profit_and_net_proceeds():
    # Full-crew audit (2026-07-11): inbound shipping-to-FBA was omitted entirely, overstating
    # profit/ROI and the backtest's would_have_profited labels. Locks in that both cost-stack
    # functions now subtract exactly estimate_inbound_shipping(weight_lb).
    price, weight = 30.0, 2.0
    shipping = scoring.estimate_inbound_shipping(weight)
    assert shipping == round(weight * config.OA_INBOUND_SHIP_PER_LB, 2)

    profit, _ = scoring.estimate_oa_profit_roi(price, weight)
    referral = price * config.REFERRAL_RATE
    fulfillment = scoring.estimate_fulfillment_fee(weight) * (1 + config.FUEL_SURCHARGE)
    cogs = price * config.OA_COGS_FRACTION
    profit_without_shipping = price - referral - fulfillment - cogs - config.OA_PREP_COST
    assert round(profit_without_shipping - profit, 2) == shipping

    proceeds = scoring.net_proceeds(price, weight)
    proceeds_without_shipping = price - referral - fulfillment - config.OA_PREP_COST
    assert round(proceeds_without_shipping - proceeds, 2) == shipping


def test_inbound_shipping_defaults_to_neutral_weight_when_missing():
    # Missing weight assumes 1.0 lb, matching estimate_fulfillment_fee's own neutral default.
    assert scoring.estimate_inbound_shipping(None) == round(1.0 * config.OA_INBOUND_SHIP_PER_LB, 2)


def test_automotive_and_industrial_referral_rate_matches_amazons_real_12_percent():
    # Full-crew audit, fba-deal-calculator finding: these 2 of the 5 categories added with the
    # 18-category rotation (2260cb0) were silently taking the 15% default instead of Amazon's
    # real 12% (selling-fees.md: Automotive & Powersports, Business, Industrial & Scientific).
    assert config.REFERRAL_RATES.get("automotive") == 0.12
    assert config.REFERRAL_RATES.get("industrial") == 0.12
    profit_automotive, _ = scoring.estimate_oa_profit_roi(30.0, 1.0, category="automotive")
    profit_default, _ = scoring.estimate_oa_profit_roi(30.0, 1.0)
    assert profit_automotive > profit_default, "12% referral should leave MORE profit than the 15% default"


def test_grocery_roi_exception_lowers_the_bar():
    # A candidate whose ROI clears 25% but not the plain 30% bar must pass the ROI scored-check
    # when tagged "grocery" and use the grocery bar; plain must use the standard 30% bar.
    cand = _base(price=25.0)
    ex_plain = scoring.explain_oa(cand)
    ex_grocery = scoring.explain_oa(dict(cand, category="grocery"))
    roi_check_plain = next(c for c in ex_plain["scored_checks"] if c["name"] == "roi")
    roi_check_grocery = next(c for c in ex_grocery["scored_checks"] if c["name"] == "roi")
    assert ex_grocery["min_roi_applied"] == config.OA_GROCERY_MIN_ROI
    assert ex_plain["min_roi_applied"] == config.CRITERIA_OA["min_roi"]
    # Grocery's ROI actual is also higher than plain's because the referral rate itself is
    # lower for grocery — both effects (lower fee, lower bar) point the same direction.
    assert roi_check_grocery["actual"] >= roi_check_plain["actual"]


def test_offer_band_bonus_applies_at_5_to_7_only():
    # Non-friendly-brand, mid-quality candidate so scores aren't already capped at 100 —
    # otherwise the bonus would be invisible under the ceiling.
    mid = dict(asin="B0MID", price=20.0, weight_lb=1.0, sales_rank=90000, est_sales=60,
              buybox_seller="A1SELLER", brand="SomeBrand", avg_price_90=19.0, avg_offers_90=6)
    bonus = config.PREFERRED_OFFERS["bonus"]
    s4, _, _ = scoring.score_product_oa(dict(mid, offers=4))
    s5, _, _ = scoring.score_product_oa(dict(mid, offers=5))
    s6, _, _ = scoring.score_product_oa(dict(mid, offers=6))
    s7, _, _ = scoring.score_product_oa(dict(mid, offers=7))
    s8, _, _ = scoring.score_product_oa(dict(mid, offers=8))
    # 4 and 8 both sit inside the hard 3-25 offer band (no gate penalty) but outside the 5-7
    # bonus band, so the ONLY difference vs 5/6/7 is the bonus.
    assert round(s5 - s4, 1) == bonus
    assert round(s6 - s4, 1) == bonus
    assert round(s7 - s8, 1) == bonus
    assert s5 == s6 == s7
    assert s4 == s8


def test_explain_oa_structure_names_every_adjustment():
    ex = scoring.explain_oa(_base())
    assert set(["verdict", "score", "scored_checks", "adjustments", "hard_reject"]).issubset(ex.keys())
    assert len(ex["scored_checks"]) == 6
    for c in ex["scored_checks"]:
        assert set(["name", "passed", "actual", "threshold"]).issubset(c.keys())
    for a in ex["adjustments"]:
        assert set(["name", "points", "reason"]).issubset(a.keys())
        assert isinstance(a["points"], (int, float))
        assert isinstance(a["reason"], str) and len(a["reason"]) > 0


def test_explain_oa_hard_reject_gives_pass_verdict():
    rejected = _base(buybox_seller=config.AMAZON_SELLER_ID)
    ex = scoring.explain_oa(rejected)
    assert ex["verdict"] == "pass"
    assert ex["hard_reject"] is not None


def test_score_product_oa_signature_unchanged_without_category():
    # Backward compatibility: calling without `category` must behave exactly as before —
    # existing callers (pipeline.py, older tests) never pass it.
    score, (profit, roi), reason = scoring.score_product_oa(_base())
    assert isinstance(score, float) and isinstance(reason, str)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in tests:
        try:
            fn()
            passed += 1
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {fn.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)
