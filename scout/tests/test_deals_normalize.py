"""
Tests for Deal Finder Build Plan Prompt D1: scout/deals/normalize.py's attribute extractor.

Zero network/dependency — pure regex logic, matching the project's zero-dependency test
convention (python tests/test_deals_normalize.py or pytest).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deals import normalize  # noqa: E402


# ---------------------------------------------------------------------------
# Pack-count extraction — the #1 documented OA matching killer per the build plan's research
# ---------------------------------------------------------------------------

def test_pack_of_n_phrasing():
    assert normalize.extract_pack_count("Tide Pods Pack of 3") == 3


def test_n_dash_pack_phrasing():
    assert normalize.extract_pack_count("Bounty Paper Towels 2-Pack") == 2


def test_n_pack_no_dash():
    assert normalize.extract_pack_count("Dove Soap 6 pack") == 6


def test_npk_abbreviation():
    assert normalize.extract_pack_count("AA Batteries 4pk") == 4


def test_nct_abbreviation():
    assert normalize.extract_pack_count("Energy Drink 12ct") == 12


def test_n_count_phrasing():
    assert normalize.extract_pack_count("Vitamin Gummies 60 count") == 60


def test_no_pack_mentioned_returns_none():
    assert normalize.extract_pack_count("Stainless Steel Water Bottle 20oz") is None


def test_single_pack_not_confused_with_size_number():
    # "20oz" must not be misread as a pack count.
    assert normalize.extract_pack_count("Yeti Tumbler 20oz Stainless Steel") is None


# ---------------------------------------------------------------------------
# Size/volume/weight extraction
# ---------------------------------------------------------------------------

def test_fl_oz_size():
    value, unit = normalize.extract_size("Gatorade 16.9 fl oz")
    assert value == 16.9
    assert unit == "fl_oz"


def test_oz_size():
    value, unit = normalize.extract_size("Water Bottle 20oz")
    assert value == 20.0
    assert unit == "oz"


def test_ml_size():
    value, unit = normalize.extract_size("Perfume 500ml Spray")
    assert value == 500.0
    assert unit == "ml"


def test_lb_size():
    value, unit = normalize.extract_size("Dog Food 15 lb Bag")
    assert value == 15.0
    assert unit == "lb"


def test_g_size():
    value, unit = normalize.extract_size("Coffee 340g Bag")
    assert value == 340.0
    assert unit == "g"


def test_no_size_returns_none_none():
    value, unit = normalize.extract_size("Assorted Building Blocks Set")
    assert value is None
    assert unit is None


# ---------------------------------------------------------------------------
# core_title — strip pack/size/brand boilerplate so embedding comparison isn't diluted
# ---------------------------------------------------------------------------

def test_core_title_strips_pack_and_brand():
    t = normalize.core_title("Tide Pods Pack of 3 - Original Scent", brand="Tide")
    assert "tide" not in t.lower()
    assert "pack of 3" not in t.lower()
    assert "original scent" in t.lower()


def test_core_title_strips_size():
    t = normalize.core_title("Gatorade 16.9 fl oz Fruit Punch")
    assert "16.9" not in t
    assert "fruit punch" in t.lower()


# ---------------------------------------------------------------------------
# extract_attributes — the full cascade-step-1 output, plus the multipack traps
# ---------------------------------------------------------------------------

def test_attributes_default_pack_count_is_one_when_unstated():
    attrs = normalize.extract_attributes("Stainless Steel Water Bottle 20oz")
    assert attrs["pack_count"] == 1
    assert attrs["size_value"] == 20.0
    assert attrs["size_unit"] == "oz"


def test_attributes_multipack_trap_1pack_vs_2pack():
    # The exact failure mode the build plan calls out: same brand/item, different pack count.
    one = normalize.extract_attributes("Bounty Paper Towels 8 Rolls", brand="Bounty")
    two = normalize.extract_attributes("Bounty Paper Towels 2-Pack 8 Rolls Each", brand="Bounty")
    assert one["pack_count"] == 1
    assert two["pack_count"] == 2
    assert one["pack_count"] != two["pack_count"]


def test_attributes_multipack_trap_size_variant():
    small = normalize.extract_attributes("Gatorade 16.9 fl oz Fruit Punch", brand="Gatorade")
    large = normalize.extract_attributes("Gatorade 32 fl oz Fruit Punch", brand="Gatorade")
    assert small["size_value"] == 16.9
    assert large["size_value"] == 32.0
    assert small["size_value"] != large["size_value"]


def test_attributes_llm_fallback_invoked_only_when_regex_finds_nothing():
    calls = []

    def fake_llm(title, brand):
        calls.append((title, brand))
        return {"pack_count": 4, "size_value": 12.0, "size_unit": "oz"}

    # Regex finds a pack count -> fallback must NOT be called.
    normalize.extract_attributes("Widget 3-Pack", llm_fallback=fake_llm)
    assert calls == []

    # Regex finds nothing -> fallback IS called and its values are used.
    attrs = normalize.extract_attributes("Mystery Widget Assortment", llm_fallback=fake_llm)
    assert calls == [("Mystery Widget Assortment", None)]
    assert attrs["pack_count"] == 4
    assert attrs["size_value"] == 12.0
    assert attrs["size_unit"] == "oz"


def test_attributes_llm_fallback_error_degrades_to_regex_only():
    def broken_llm(title, brand):
        raise RuntimeError("API down")

    # Must not raise — degrades to the regex-only (pack_count defaults to 1) result.
    attrs = normalize.extract_attributes("Mystery Widget Assortment", llm_fallback=broken_llm)
    assert attrs["pack_count"] == 1


def test_attributes_llm_fallback_non_dict_is_ignored():
    attrs = normalize.extract_attributes("Mystery Widget Assortment", llm_fallback=lambda t, b: "not a dict")
    assert attrs["pack_count"] == 1


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
