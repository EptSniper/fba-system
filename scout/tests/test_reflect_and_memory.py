"""
Tests for Scout Agent Build Plan Prompt S3: scout/reflect.py (brand memory) and
scout/memory_report.py (the honest with/without-memory measurement harness).

Zero live network calls — the anthropic client is mocked throughout (no real
ANTHROPIC_API_KEY exists in this environment). File writes are redirected to a temp dir via
patching MEMORY_DIR/REPORT_PATH — nothing here touches the real learning-hub/ tree.
"""
import ast
import inspect
import os
import sys
import tempfile
import types
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import memory_report  # noqa: E402
import reflect  # noqa: E402


def _fake_tool_use_block(name, input_dict):
    block = types.SimpleNamespace()
    block.type = "tool_use"
    block.name = name
    block.input = input_dict
    return block


# ---------------------------------------------------------------------------
# AST guards — real open()-target checks, not blanket text bans (a naive substring ban on
# "ai-brain.json" false-positives on this module's own honest docstrings/comments).
# ---------------------------------------------------------------------------

def _open_call_targets_containing(module, needle):
    tree = ast.parse(inspect.getsource(module))
    hits = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "open" and node.args):
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and needle in arg.value:
                hits.append(arg.value)
    return hits


def test_reflect_never_opens_ai_brain_json():
    assert _open_call_targets_containing(reflect, "ai-brain.json") == []


def test_memory_report_never_opens_ai_brain_json():
    assert _open_call_targets_containing(memory_report, "ai-brain.json") == []


def test_reflect_never_calls_scoring_functions():
    tree = ast.parse(inspect.getsource(reflect))
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    forbidden = {"explain_oa", "score_product_oa", "oa_hard_reject"}
    assert not (attrs & forbidden)


# ---------------------------------------------------------------------------
# reflect.py — slug, read_memory_note, activity detection, post-validation
# ---------------------------------------------------------------------------

def test_slug_normalizes_brand_name():
    assert reflect._slug("Mrs. Meyer's") == "mrs-meyer-s"
    assert reflect._slug("  Jellycat  ") == "jellycat"


def test_read_memory_note_none_when_absent():
    with tempfile.TemporaryDirectory() as d:
        with patch.object(reflect, "MEMORY_DIR", d):
            assert reflect.read_memory_note("Nonexistent Brand") is None


def test_read_memory_note_returns_file_contents():
    with tempfile.TemporaryDirectory() as d:
        with patch.object(reflect, "MEMORY_DIR", d):
            with open(os.path.join(d, "jellycat.md"), "w", encoding="utf-8") as f:
                f.write("## Verdict history\nSafe brand.\n")
            assert "Safe brand" in reflect.read_memory_note("Jellycat")


def test_read_memory_note_none_for_falsy_brand():
    assert reflect.read_memory_note(None) is None
    assert reflect.read_memory_note("") is None


def test_brands_with_recent_activity_via_decision():
    leads = [{"brand": "Jellycat", "decisions": [{"decided_at": "2026-07-02T00:00:00+00:00"}]}]
    brands = reflect._brands_with_recent_activity(leads, "2026-06-25T00:00:00+00:00")
    assert brands == {"Jellycat"}


def test_brands_with_recent_activity_via_analyst_disagreement():
    leads = [{"brand": "Yeti", "explanation": {"analyst_note": {"disagrees_with_rules": True}}}]
    brands = reflect._brands_with_recent_activity(leads, "2026-06-25T00:00:00+00:00")
    assert brands == {"Yeti"}


def test_brands_with_recent_activity_excludes_stale_or_brandless():
    leads = [
        {"brand": "Old Brand", "decisions": [{"decided_at": "2020-01-01T00:00:00+00:00"}]},
        {"brand": None, "decisions": [{"decided_at": "2026-07-02T00:00:00+00:00"}]},
    ]
    brands = reflect._brands_with_recent_activity(leads, "2026-06-25T00:00:00+00:00")
    assert brands == set()


def test_post_validate_accepts_real_asins():
    assert reflect._post_validate("Saw B0ABCDEFGH do well.", {"B0ABCDEFGH"}) is True


def test_post_validate_rejects_fabricated_asin():
    assert reflect._post_validate("Saw B0FAKE0001 do well.", {"B0REAL0001"}) is False


# ---------------------------------------------------------------------------
# reflect_on_brand / run_weekly
# ---------------------------------------------------------------------------

def test_reflect_on_brand_unavailable_without_key():
    with patch.object(reflect.analyst, "configured", return_value=False):
        result = reflect.reflect_on_brand("Jellycat", [])
    assert result["status"] == "unavailable"


def test_reflect_on_brand_success_writes_note():
    fake_response = types.SimpleNamespace(content=[_fake_tool_use_block(
        "submit_note", {"updated_note": "## Verdict history\nB0REAL0001 was a good pick.\n"})])
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response
    leads = [{"asin": "B0REAL0001", "verdict": "review", "decisions": [], "outcomes": []}]

    with tempfile.TemporaryDirectory() as d:
        with patch.object(reflect, "MEMORY_DIR", d), \
             patch.object(reflect.analyst, "configured", return_value=True):
            result = reflect.reflect_on_brand("Jellycat", leads, client=fake_client)
        assert result["status"] == "updated"
        with open(os.path.join(d, "jellycat.md"), encoding="utf-8") as f:
            assert "B0REAL0001" in f.read()


def test_reflect_on_brand_rejects_hallucinated_asin_and_does_not_write():
    fake_response = types.SimpleNamespace(content=[_fake_tool_use_block(
        "submit_note", {"updated_note": "B0FAKE0001 was great."})])
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response
    leads = [{"asin": "B0REAL0001", "verdict": "review", "decisions": [], "outcomes": []}]

    with tempfile.TemporaryDirectory() as d:
        with patch.object(reflect, "MEMORY_DIR", d), \
             patch.object(reflect.analyst, "configured", return_value=True):
            result = reflect.reflect_on_brand("Jellycat", leads, client=fake_client)
        assert result["status"] == "rejected"
        assert not os.path.exists(os.path.join(d, "jellycat.md"))


def test_reflect_on_brand_truncates_long_note():
    long_note = "\n".join(f"line {i}" for i in range(200))
    fake_response = types.SimpleNamespace(content=[_fake_tool_use_block(
        "submit_note", {"updated_note": long_note})])
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    with tempfile.TemporaryDirectory() as d:
        with patch.object(reflect, "MEMORY_DIR", d), \
             patch.object(reflect.analyst, "configured", return_value=True):
            reflect.reflect_on_brand("Jellycat", [], client=fake_client)
        with open(os.path.join(d, "jellycat.md"), encoding="utf-8") as f:
            assert len(f.read().splitlines()) <= reflect.MAX_NOTE_LINES


def test_reflect_on_brand_degrades_on_api_exception():
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = RuntimeError("down")
    with patch.object(reflect.analyst, "configured", return_value=True):
        result = reflect.reflect_on_brand("Jellycat", [], client=fake_client)
    assert result["status"] == "error"


def test_run_weekly_unavailable_without_key():
    with patch.object(reflect.analyst, "configured", return_value=False):
        result = reflect.run_weekly()
    assert result["status"] == "unavailable"


def test_run_weekly_reflects_on_each_active_brand():
    leads = [{"brand": "Jellycat", "decisions": [{"decided_at": "2026-07-02T00:00:00+00:00"}]}]
    with patch.object(reflect.analyst, "configured", return_value=True), \
         patch.object(reflect.db, "leads_with_outcomes", return_value=leads), \
         patch.object(reflect.db, "leads_by_brand", return_value=leads), \
         patch.object(reflect, "reflect_on_brand", return_value={"brand": "Jellycat", "status": "updated"}) as mock_reflect:
        result = reflect.run_weekly()
    mock_reflect.assert_called_once()
    assert result["brands_updated"] == 1


def test_run_weekly_survives_a_brand_erroring():
    leads = [{"brand": "Jellycat", "decisions": [{"decided_at": "2026-07-02T00:00:00+00:00"}]}]
    with patch.object(reflect.analyst, "configured", return_value=True), \
         patch.object(reflect.db, "leads_with_outcomes", return_value=leads), \
         patch.object(reflect.db, "leads_by_brand", return_value=leads), \
         patch.object(reflect, "reflect_on_brand", side_effect=RuntimeError("boom")):
        result = reflect.run_weekly()
    assert result["brands_updated"] == 0
    assert result["results"][0]["status"] == "error"


# ---------------------------------------------------------------------------
# memory_report.py
# ---------------------------------------------------------------------------

def _lead(memory_used=None, disagrees=None, label_good=None):
    note = {}
    if memory_used is not None:
        note["memory_used"] = memory_used
    if disagrees is not None:
        note["disagrees_with_rules"] = disagrees
    outcomes = []
    if label_good is not None:
        outcomes = [{"would_rebuy": label_good, "closed_at": "2026-07-01T00:00:00+00:00"}]
    return {"explanation": {"analyst_note": note} if note else {}, "outcomes": outcomes}


def test_group_by_memory_used_excludes_leads_without_the_flag():
    leads = [_lead(memory_used=True), _lead(memory_used=False), {"explanation": {}}]
    with_mem, without_mem = memory_report._group_by_memory_used(leads)
    assert len(with_mem) == 1 and len(without_mem) == 1


def test_disagreement_hit_rate_none_when_no_disagreements():
    leads = [_lead(memory_used=True, disagrees=False, label_good=True)]
    assert memory_report.disagreement_hit_rate(leads) is None


def test_disagreement_hit_rate_counts_bad_outcomes_as_hits():
    leads = [
        _lead(memory_used=True, disagrees=True, label_good=False),  # hit: disagreed, went bad
        _lead(memory_used=True, disagrees=True, label_good=True),   # miss: disagreed, went fine
    ]
    result = memory_report.disagreement_hit_rate(leads)
    assert result == {"hit_rate": 0.5, "n": 2}


def test_generate_report_honest_when_below_sample_bar():
    with patch.object(memory_report.db, "leads_with_outcomes", return_value=[]):
        block = memory_report.generate_report()
    assert "Not enough data yet" in block


def test_generate_report_compares_groups_once_bar_is_cleared():
    with_memory = [_lead(memory_used=True, disagrees=True, label_good=False)
                  for _ in range(memory_report.MIN_SAMPLE_PER_GROUP)]
    without_memory = [_lead(memory_used=False, disagrees=True, label_good=True)
                      for _ in range(memory_report.MIN_SAMPLE_PER_GROUP)]
    with patch.object(memory_report.db, "leads_with_outcomes", return_value=with_memory + without_memory):
        block = memory_report.generate_report()
    assert "With-memory group" in block
    assert "Without-memory group" in block
    assert "Not enough data yet" not in block


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
