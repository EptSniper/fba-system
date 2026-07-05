"""
Tests for scout/deals/registry.py (TOP100_DEAL_WATCH_PLAN.md T1) — the Top-100 registry loader
+ validator + the AVOID hard-gate. Runs against the REAL learning-hub/data/top100-sources.json
(it is the single source; a test that mocked it away would prove nothing about the real file)
plus synthetic broken registries for the validation paths.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deals import registry  # noqa: E402


def test_real_registry_validates_clean():
    reg = registry.load_registry()
    assert registry.validate(reg) == []


def test_real_registry_has_100_entries_ranked_1_to_100():
    reg = registry.load_registry()
    entries = registry.all_entries(reg)
    assert len(entries) == 100
    assert sorted(e["rank"] for e in entries) == list(range(1, 101))


def test_parse_detect_splits_on_first_colon_only():
    assert registry.parse_detect("sd-rss:walmart") == ("sd-rss", "walmart")
    assert registry.parse_detect("clr:https://x.com/a:b") == ("clr", "https://x.com/a:b")
    assert registry.parse_detect("nl") == ("nl", None)


def test_detect_args_skips_verify_placeholder():
    entry = {"detect": ["clr:https://real.com/sale", "clr:VERIFY", "aff:impact"]}
    assert registry.detect_args(entry, "clr") == ["https://real.com/sale"]
    assert registry.detect_args(entry, "aff") == ["impact"]


def test_avoid_entries_excluded_from_non_avoid():
    reg = registry.load_registry()
    non_avoid = registry.non_avoid_entries(reg)
    assert all(not registry.entry_is_avoid(e) for e in non_avoid)
    # Disney Store / Nike / adidas are the AVOID-flagged entries in the real registry.
    names = {e["name"] for e in non_avoid}
    assert "Nike" not in names and "adidas" not in names and "Disney Store" not in names


def test_assert_no_avoid_raises_on_avoid_entry():
    avoid_entry = {"name": "Nike", "flags": ["AVOID"]}
    ok_entry = {"name": "Target", "flags": []}
    registry.assert_no_avoid([ok_entry])  # no raise
    try:
        registry.assert_no_avoid([ok_entry, avoid_entry])
    except AssertionError as e:
        assert "Nike" in str(e)
    else:
        raise AssertionError("assert_no_avoid should have raised on an AVOID entry")


def test_fetchable_entries_need_a_machine_method():
    reg = {"tier1": [
        {"name": "HasRss", "detect": ["sd-rss:x"], "flags": []},
        {"name": "ManualOnly", "detect": ["nl"], "flags": []},
        {"name": "NoneOnly", "detect": ["none"], "flags": []},
    ]}
    names = {e["name"] for e in registry.fetchable_entries(reg)}
    assert names == {"HasRss"}


def test_validate_flags_duplicate_rank_and_bad_flag_and_bad_detect():
    reg = {
        "$comment": "x",
        "tier1": [{"rank": 1, "name": "A", "domain": "a.com", "cats": [], "edge": "", "detect": ["bogus:x"], "flags": ["WAT"]}],
        "tier2": [{"rank": 1, "name": "B", "domain": "a.com", "cats": [], "edge": "", "detect": ["sd-rss:b"], "flags": []}],
        "tier3": [],
    }
    problems = registry.validate(reg)
    joined = " ".join(problems)
    assert "duplicate rank 1" in joined
    assert "unknown flag 'WAT'" in joined
    assert "unknown detect code 'bogus'" in joined
    assert "duplicate domain 'a.com'" in joined
    assert "expected 100 entries" in joined


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in tests:
        try:
            fn(); passed += 1; print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            print(f"FAIL  {fn.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)
