"""
Regression tests for Code Review 2026-07-02:
  - Finding S5: config._load_oa_criteria_from_brain() must actually apply ai-brain.json's
    scoring.adjustments/ipCliffShape/worstCaseLossBarUsd/scoreThreshold/topN/assumedDailyTokens
    overrides, not just happen to match the hardcoded defaults.
  - Finding S6: same loader must also apply fees.fuelSurcharge/fees.prepCost.
  - Finding CS6: same loader must also apply fees.bandedRates (price-banded referral rates).
Writes a temporary brain file with DIFFERENT values than the defaults and asserts the globals
actually change, then restores the real values so later tests aren't affected.
"""
import builtins
import json
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402

_REAL_OPEN = builtins.open


def _redirect_to(fake_path):
    def _opener(p, *a, **kw):
        return _REAL_OPEN(fake_path, *a, **kw) if str(p).endswith("ai-brain.json") else _REAL_OPEN(p, *a, **kw)
    return _opener


def _fake_brain():
    return {
        "criteria": {}, "guards": {},
        "scoring": {
            "adjustments": {
                "friendlyBrand": 99, "priceSpike": -1, "priceCaution": -2,
                "offersRising": -3, "amazonSharesBuybox": -4, "ipCliff": -5,
                "worstCaseLoss": -6, "noFeaturedOffer": -7, "genericBrand": -8,
            },
            "ipCliffShape": {"minAvgOffers": 42, "maxCurrentOffers": 11},
            "worstCaseLossBarUsd": 3.5,
            "scoreThreshold": 55,
            "topN": 9,
            "assumedDailyTokens": 12345,
        },
        "fees": {
            "fuelSurcharge": 0.099, "prepCost": 1.23,
            "bandedRates": {"grocery": {"priceThreshold": 20, "atOrBelowThreshold": 0.05, "aboveThreshold": 0.22}},
        },
    }


def test_brain_overrides_adjustment_magnitudes():
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(_fake_brain(), f)
        path = f.name
    try:
        with patch("builtins.open", side_effect=_redirect_to(path)):
            config._load_oa_criteria_from_brain()
        assert config.OA_ADJ_FRIENDLY_BRAND == 99.0
        assert config.OA_ADJ_PRICE_SPIKE == -1.0
        assert config.OA_ADJ_PRICE_CAUTION == -2.0
        assert config.OA_ADJ_OFFERS_RISING == -3.0
        assert config.OA_ADJ_AMAZON_SHARES_BUYBOX == -4.0
        assert config.OA_ADJ_IP_CLIFF == -5.0
        assert config.OA_ADJ_WORST_CASE_LOSS == -6.0
        assert config.OA_ADJ_NO_FEATURED_OFFER == -7.0
        assert config.OA_ADJ_GENERIC_BRAND == -8.0
        assert config.OA_IP_CLIFF_MIN_AVG_OFFERS == 42.0
        assert config.OA_IP_CLIFF_MAX_CURRENT_OFFERS == 11.0
        assert config.OA_WORST_CASE_LOSS_BAR == 3.5
        assert config.SCORE_THRESHOLD == 55.0
        assert config.TOP_N == 9
        assert config.ASSUMED_DAILY_TOKENS == 12345
        assert config.FUEL_SURCHARGE == 0.099
        assert config.OA_PREP_COST == 1.23
        assert config.BANDED_REFERRAL_RATES["grocery"] == {
            "priceThreshold": 20.0, "atOrBelowThreshold": 0.05, "aboveThreshold": 0.22,
        }
        assert config.referral_rate_for("grocery", price=15.0) == 0.05
        assert config.referral_rate_for("grocery", price=25.0) == 0.22
        # Omitting price keeps the OLD flat-rate behavior — never banded implicitly.
        assert config.referral_rate_for("grocery") == config.REFERRAL_RATES["grocery"]
    finally:
        os.unlink(path)
        config._load_oa_criteria_from_brain()  # restore real values for later tests


def test_brain_missing_scoring_block_keeps_defaults():
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({"criteria": {}, "guards": {}}, f)
        path = f.name
    before = config.OA_ADJ_FRIENDLY_BRAND
    try:
        with patch("builtins.open", side_effect=_redirect_to(path)):
            config._load_oa_criteria_from_brain()
        assert config.OA_ADJ_FRIENDLY_BRAND == before  # unchanged, no crash
    finally:
        os.unlink(path)
        config._load_oa_criteria_from_brain()
