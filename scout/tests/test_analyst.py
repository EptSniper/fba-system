"""
Tests for Scout Agent Build Plan Prompt S1: scout/analyst.py + its pipeline wiring.

Zero live network calls — no real ANTHROPIC_API_KEY exists in this environment (the anthropic
SDK IS installed, but the key is a placeholder in API_KEYS.env), so every test mocks the
anthropic client. This validates the LOGIC (anti-sycophancy input filtering, tabular-
hallucination post-validation, graceful degradation, pipeline wiring) — NOT a live integration;
that remains unverified until Mehmet adds a real key.
"""
import ast
import inspect
import os
import sys
import types
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analyst  # noqa: E402
import pipeline  # noqa: E402


def _base(**kw):
    p = {
        "asin": "B0TEST", "price": 30.0, "brand": "Jellycat",
        "rule_score": 80, "blended_score": 85, "model_proba": 0.7, "verdict": "review", "score": 85,
        "explanation": {"gates": [{"name": "bsr", "passed": True}], "adjustments": []},
    }
    p.update(kw)
    return p


def _fake_tool_use_block(input_dict):
    block = types.SimpleNamespace()
    block.type = "tool_use"
    block.name = "submit_analysis"
    block.input = input_dict
    return block


# ---------------------------------------------------------------------------
# AST guard: analyst.py can never touch scoring/gates/ai-brain.json, never writes a file
# ---------------------------------------------------------------------------

_FORBIDDEN_SCORING_CALLS = {"explain_oa", "score_product_oa", "oa_hard_reject", "rule_score"}


def test_analyst_never_calls_scoring_functions():
    tree = ast.parse(inspect.getsource(analyst))
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            called.add(node.attr)
    assert not (called & _FORBIDDEN_SCORING_CALLS), \
        f"analyst.py must never call scoring functions, found: {called & _FORBIDDEN_SCORING_CALLS}"


def test_analyst_never_opens_a_file():
    tree = ast.parse(inspect.getsource(analyst))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
            assert False, "analyst.py has no legitimate reason to open/write any file"


def test_analyst_has_no_ai_brain_json_open_call():
    # NOT a blanket substring ban — the module's own docstring legitimately explains that it
    # has no write path to ai-brain.json, which would false-positive on a naive text search.
    # AST-based: assert no open()/write call anywhere targets that path (there are none, since
    # test_analyst_never_opens_a_file already proves there's no open() call in this file at all).
    tree = ast.parse(inspect.getsource(analyst))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
            assert False, "analyst.py must never open any file, let alone ai-brain.json"


# ---------------------------------------------------------------------------
# configured() honesty + build_input's anti-sycophancy filtering
# ---------------------------------------------------------------------------

def test_not_configured_without_key():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        assert analyst.configured() is False


def test_build_input_excludes_score_and_verdict_fields():
    data = analyst.build_input(_base())
    for forbidden in ("rule_score", "blended_score", "model_proba", "verdict", "score"):
        assert forbidden not in data


def test_build_input_includes_gates_and_adjustments():
    data = analyst.build_input(_base())
    assert data["gates"] == [{"name": "bsr", "passed": True}]
    assert data["asin"] == "B0TEST"
    assert data["brand"] == "Jellycat"


def test_build_input_includes_memory_note_when_given():
    data = analyst.build_input(_base(), memory_note="Always reliable brand.")
    assert data["brand_memory_note"] == "Always reliable brand."


def test_build_input_omits_none_fields():
    data = analyst.build_input({"asin": "B0X"})
    assert "brand" not in data
    assert "gates" not in data


# ---------------------------------------------------------------------------
# _post_validate — the tabular-hallucination guard
# ---------------------------------------------------------------------------

def test_post_validate_keeps_risk_with_valid_evidence_fields():
    input_data = {"asin": "B0X", "offers": 40}
    analysis = {"top_risks": [{"claim": "crowded", "evidence_fields": ["offers"]}]}
    cleaned, rejected = analyst._post_validate(analysis, input_data)
    assert rejected == 0
    assert len(cleaned["top_risks"]) == 1


def test_post_validate_drops_risk_citing_field_not_in_input():
    input_data = {"asin": "B0X"}
    analysis = {"top_risks": [{"claim": "fabricated", "evidence_fields": ["review_count"]}]}
    cleaned, rejected = analyst._post_validate(analysis, input_data)
    assert rejected == 1
    assert cleaned["top_risks"] == []


def test_post_validate_drops_risk_with_no_evidence_fields():
    input_data = {"asin": "B0X"}
    analysis = {"top_risks": [{"claim": "vague", "evidence_fields": []}]}
    cleaned, rejected = analyst._post_validate(analysis, input_data)
    assert rejected == 1


# ---------------------------------------------------------------------------
# call_analyst — honest degradation + mocked success path
# ---------------------------------------------------------------------------

def test_call_analyst_unavailable_without_key():
    with patch.object(analyst, "anthropic", None):
        result = analyst.call_analyst({"asin": "B0X"})
    assert result["status"] == "unavailable"


def test_call_analyst_success_with_mocked_client():
    fake_response = types.SimpleNamespace(content=[_fake_tool_use_block({
        "qualitative_risk": "medium", "disagrees_with_rules": True,
        "top_risks": [{"claim": "seller pile-in", "evidence_fields": ["offers"]}],
        "narrative": "Looks fine on paper but offer count is climbing fast.",
        "unknowns": ["true landed cost"],
    })])
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fake-key"}), \
         patch.object(analyst, "anthropic", MagicMock()):
        result = analyst.call_analyst({"asin": "B0X", "offers": 40}, client=fake_client)

    assert result["status"] == "ok"
    assert result["disagrees_with_rules"] is True
    assert result["rejected_risk_count"] == 0
    assert fake_client.messages.create.call_args[1]["tool_choice"] == {"type": "tool", "name": "submit_analysis"}


def test_call_analyst_success_path_filters_hallucinated_risk():
    fake_response = types.SimpleNamespace(content=[_fake_tool_use_block({
        "qualitative_risk": "low", "disagrees_with_rules": False,
        "top_risks": [{"claim": "fabricated claim", "evidence_fields": ["not_a_real_field"]}],
        "narrative": "n/a", "unknowns": [],
    })])
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fake-key"}), \
         patch.object(analyst, "anthropic", MagicMock()):
        result = analyst.call_analyst({"asin": "B0X"}, client=fake_client)

    assert result["rejected_risk_count"] == 1
    assert result["top_risks"] == []


def test_call_analyst_degrades_on_api_exception():
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = RuntimeError("rate limited")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fake-key"}), \
         patch.object(analyst, "anthropic", MagicMock()):
        result = analyst.call_analyst({"asin": "B0X"}, client=fake_client)
    assert result["status"] == "error"
    assert "rate limited" in result["reason"]


def test_call_analyst_error_when_no_tool_use_block_returned():
    fake_response = types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text="oops")])
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fake-key"}), \
         patch.object(analyst, "anthropic", MagicMock()):
        result = analyst.call_analyst({"asin": "B0X"}, client=fake_client)
    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# pipeline._run_analyst_pass wiring
# ---------------------------------------------------------------------------

def test_run_analyst_pass_noop_without_key():
    with patch.object(pipeline.analyst, "configured", return_value=False):
        scored = [_base()]
        result = pipeline._run_analyst_pass(scored)
    assert "analyst_note" not in result[0]


def test_run_analyst_pass_attaches_note_and_merges_into_explanation():
    note = {"status": "ok", "disagrees_with_rules": True, "narrative": "risky"}
    with patch.object(pipeline.analyst, "configured", return_value=True), \
         patch.object(pipeline.analyst, "analyze", return_value=note):
        scored = [_base()]
        result = pipeline._run_analyst_pass(scored)
    assert result[0]["analyst_note"] == note
    assert result[0]["explanation"]["analyst_note"] == note


def test_run_analyst_pass_survives_analyze_raising():
    with patch.object(pipeline.analyst, "configured", return_value=True), \
         patch.object(pipeline.analyst, "analyze", side_effect=RuntimeError("boom")):
        scored = [_base()]
        result = pipeline._run_analyst_pass(scored)
    assert result[0]["analyst_note"]["status"] == "error"


def test_run_analyst_pass_never_touches_score_or_verdict():
    note = {"status": "ok", "disagrees_with_rules": True}
    with patch.object(pipeline.analyst, "configured", return_value=True), \
         patch.object(pipeline.analyst, "analyze", return_value=note):
        scored = [_base(blended_score=85, verdict="review")]
        result = pipeline._run_analyst_pass(scored)
    assert result[0]["blended_score"] == 85
    assert result[0]["verdict"] == "review"


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
