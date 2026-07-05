"""
Tests for TOP100_DEAL_WATCH_PLAN.md T3: scout/discovery_hints.py (the scout's hint consumer)
and pipeline's two-pass hint-led discovery ordering. Keepa + Supabase fully mocked — this
validates the ORDERING/attribution/AVOID-gate logic, which is Keepa-gated but built now.
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discovery_hints  # noqa: E402
import pipeline  # noqa: E402


# ---------------------------------------------------------------------------
# discovery_hints — AVOID gate (second layer), config, fresh filtering
# ---------------------------------------------------------------------------
def test_fresh_hints_excludes_avoid_brands_second_layer():
    rows = [{"brand": "Jellycat", "store": "Target", "strength": 3},
            {"brand": "Nike", "store": "Kohl's", "strength": 5}]   # avoid — must be dropped
    with patch.object(discovery_hints.db, "fresh_deal_hints", return_value=rows), \
         patch.object(discovery_hints.brands, "AVOID_BRANDS", ["Nike", "Adidas"]):
        fresh = discovery_hints.fresh_hints()
    assert [h["brand"] for h in fresh] == ["Jellycat"]


def test_hinted_brand_seeds_dedup_and_order_by_strength():
    rows = [{"brand": "Yeti", "strength": 5}, {"brand": "Jellycat", "strength": 3},
            {"brand": "Yeti", "strength": 2}]  # dup Yeti — strongest first, deduped
    with patch.object(discovery_hints.db, "fresh_deal_hints", return_value=rows), \
         patch.object(discovery_hints.brands, "AVOID_BRANDS", []):
        seeds = discovery_hints.hinted_brand_seeds()
    assert seeds == ["Yeti", "Jellycat"]


def test_token_share_clamped_to_unit_interval():
    with patch.object(discovery_hints.brain_config, "deal_finder_block", return_value={"hints": {"tokenShare": 5.0}}):
        assert discovery_hints.token_share() == 1.0
    with patch.object(discovery_hints.brain_config, "deal_finder_block", return_value={"hints": {"tokenShare": -1}}):
        assert discovery_hints.token_share() == 0.0


def test_defaults_when_brain_block_absent():
    with patch.object(discovery_hints.brain_config, "deal_finder_block", return_value={}):
        assert discovery_hints.min_strength() == 2.0
        assert discovery_hints.token_share() == 0.5


# ---------------------------------------------------------------------------
# pipeline._discover_candidates — hint-led FIRST, budget cap, fallback, attribution
# ---------------------------------------------------------------------------
def test_no_fresh_hints_means_100_percent_normal_discovery():
    with patch.object(pipeline.discovery_hints, "hinted_brand_seeds", return_value=[]), \
         patch.object(pipeline.keepa_client, "find_candidates", return_value=["A1", "A2"]) as fc:
        out = pipeline._discover_candidates({}, api=None, limit=100)
    assert out["asins"] == ["A1", "A2"] and out["hints_followed"] == 0 and out["hinted"] == {}
    fc.assert_called_once()  # single normal pass, no hint pass


def test_hint_led_pass_runs_first_and_respects_token_share():
    calls = []

    def fake_fc(criteria, api=None, limit=None, brand_seeds=None):
        calls.append({"limit": limit, "brand_seeds": brand_seeds})
        return ["H1", "H2"] if brand_seeds else ["N1", "N2"]

    with patch.object(pipeline.discovery_hints, "hinted_brand_seeds", return_value=["Yeti"]), \
         patch.object(pipeline.discovery_hints, "fresh_hints",
                      return_value=[{"brand": "Yeti", "store": "Target"}]), \
         patch.object(pipeline.discovery_hints, "token_share", return_value=0.5), \
         patch.object(pipeline.keepa_client, "find_candidates", side_effect=fake_fc):
        out = pipeline._discover_candidates({}, api=None, limit=100)
    # First call is the hint pass (brand_seeds set), budget = 50% of 100.
    assert calls[0]["brand_seeds"] == ["Yeti"] and calls[0]["limit"] == 50
    # Second call is the normal pass for the remainder.
    assert calls[1]["brand_seeds"] is None
    assert out["asins"] == ["H1", "H2", "N1", "N2"]  # hint-led first, deduped
    assert out["hints_followed"] == 1
    assert out["hinted"] == {"H1": True, "H2": True}
    assert out["brand_store"] == {"Yeti": "Target"}


def test_hint_led_dedups_overlap_between_passes():
    def fake_fc(criteria, api=None, limit=None, brand_seeds=None):
        return ["X1", "X2"] if brand_seeds else ["X2", "X3"]  # X2 overlaps
    with patch.object(pipeline.discovery_hints, "hinted_brand_seeds", return_value=["Yeti"]), \
         patch.object(pipeline.discovery_hints, "fresh_hints", return_value=[{"brand": "Yeti", "store": "T"}]), \
         patch.object(pipeline.discovery_hints, "token_share", return_value=0.5), \
         patch.object(pipeline.keepa_client, "find_candidates", side_effect=fake_fc):
        out = pipeline._discover_candidates({}, api=None, limit=100)
    assert out["asins"] == ["X1", "X2", "X3"]  # no duplicate X2


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in tests:
        try:
            fn(); passed += 1; print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {fn.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)
