"""
Regression tests for Code Review 2026-07-02, Finding S3: keepa_client._normalize() must
populate "category" (mapped to an ai-brain.json fees.referralRates key) and "category_source"
so scoring.py's category-aware referral rate / grocery ROI exception actually receive real
data instead of always falling back to REFERRAL_RATES["default"].
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import keepa_client  # noqa: E402


def _product(category_tree=None, **extra):
    p = {"asin": "B000TEST", "title": "Test Product", "brand": "Acme", "stats": {}}
    if category_tree is not None:
        p["categoryTree"] = category_tree
    p.update(extra)
    return p


def test_maps_leaf_category_to_brain_key():
    p = _product([{"catId": 1, "name": "Toys & Games"}, {"catId": 2, "name": "Toy Figures & Playsets"}])
    category, source = keepa_client._category_from_tree(p)
    assert category == "toys"
    assert source == "keepa_category_tree"


def test_falls_back_to_a_higher_tree_level_when_leaf_is_unmapped():
    p = _product([{"catId": 1, "name": "Grocery & Gourmet Food"}, {"catId": 2, "name": "Some Obscure Leaf"}])
    category, source = keepa_client._category_from_tree(p)
    assert category == "grocery"
    assert source == "keepa_category_tree"


def test_grocery_detection_for_roi_exception():
    p = _product([{"catId": 1, "name": "Grocery & Gourmet Food"}])
    category, _source = keepa_client._category_from_tree(p)
    assert category == "grocery"


def test_returns_raw_root_name_when_nothing_maps():
    p = _product([{"catId": 1, "name": "Some Weird Category"}])
    category, source = keepa_client._category_from_tree(p)
    assert category == "Some Weird Category"
    assert source == "keepa_category_tree"


def test_no_category_tree_returns_none_none():
    p = _product(None)
    assert keepa_client._category_from_tree(p) == (None, None)


def test_empty_category_tree_returns_none_none():
    p = _product([])
    assert keepa_client._category_from_tree(p) == (None, None)


def test_normalize_populates_category_fields():
    p = _product([{"catId": 1, "name": "Beauty & Personal Care"}])
    out = keepa_client._normalize(p)
    assert out["category"] == "beauty"
    assert out["category_source"] == "keepa_category_tree"


def test_normalize_without_category_tree_degrades_to_none():
    p = _product(None)
    out = keepa_client._normalize(p)
    assert out["category"] is None
    assert out["category_source"] is None
