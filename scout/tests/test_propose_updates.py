"""
Tests for System Blueprint Prompt G5: scout/propose_updates.py.

Zero live network calls — db.py and the knowledge-driven subprocess call are mocked throughout.
SAFETY: real DISCORD_WEBHOOK_BRAIN_PROPOSALS lives in scout/.env, so any test that reaches
write_report_with_count()/notify_brain_proposals() with a non-empty proposals list patches
discord_router.send defensively (see test_run_daily.py's module docstring for the incident
that established this rule).
"""
import ast
import inspect
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402
import propose_updates  # noqa: E402


# ---------------------------------------------------------------------------
# The guard: NO write path to ai-brain.json, ever
# ---------------------------------------------------------------------------

def test_propose_updates_has_no_write_path_to_ai_brain_json():
    """Static guard via real AST parsing: every open(...) call in the module must target
    REPORT_PATH — never ai-brain.json. This is THE non-negotiable of Prompt G5."""
    tree = ast.parse(inspect.getsource(propose_updates))
    open_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "open"
    ]
    assert open_calls, "expected at least one open() call (writing the report)"
    for call in open_calls:
        first_arg = call.args[0] if call.args else None
        target = getattr(first_arg, "id", None)
        assert target == "REPORT_PATH", f"open() call targets {target!r}, not REPORT_PATH"
    # The module doesn't even define a path constant for ai-brain.json (unlike labels.py,
    # which deliberately READS it for min_labeled_rows) — it can't write what it never opens.
    assert "BRAIN_PATH" not in inspect.getsource(propose_updates)


# ---------------------------------------------------------------------------
# Outcome-driven — honest small-sample wording (the brief's own worked example)
# ---------------------------------------------------------------------------

def _lead(asin, gate_name=None, adj_name=None, gate_passed=False, profit=-5.0):
    explanation = {"gates": [], "adjustments": []}
    if gate_name:
        explanation["gates"].append({"name": gate_name, "passed": gate_passed})
    if adj_name:
        explanation["adjustments"].append({"name": adj_name, "points": -10, "reason": "x"})
    return {"asin": asin, "brand": "TestBrand", "explanation": explanation,
           "outcomes": [{"actual_profit": profit}]}


def test_outcome_driven_reports_small_sample_honestly():
    leads = [_lead(f"B0{i:04d}", gate_name="offers", gate_passed=False) for i in range(2)]
    with patch.object(db, "leads_with_outcomes", return_value=leads):
        proposals = propose_updates.outcome_driven_proposals()
    matching = [p for p in proposals if "gate:offers=fail" in p["finding"]]
    assert matching, "expected a finding for the failed offers gate"
    assert matching[0]["confidence"] == "too small to act"
    assert matching[0]["sample_size"] == 2


def test_outcome_driven_reports_strong_signal_at_scale():
    leads = [_lead(f"B0{i:04d}", gate_name="roi", gate_passed=False) for i in range(12)]
    with patch.object(db, "leads_with_outcomes", return_value=leads):
        proposals = propose_updates.outcome_driven_proposals()
    matching = [p for p in proposals if "gate:roi=fail" in p["finding"]]
    assert matching[0]["confidence"] == "strong signal"
    assert matching[0]["sample_size"] == 12


# ---------------------------------------------------------------------------
# Data-driven — dead gate, cold/IP-cliff brand, token-cost drift (fixture telemetry)
# ---------------------------------------------------------------------------

def test_data_driven_flags_dead_gate_at_100_percent_reject():
    leads = [_lead(f"B0{i:04d}", gate_name="bsr", gate_passed=False) for i in range(6)]
    with patch.object(db, "leads_with_outcomes", return_value=leads), \
            patch.object(db, "recent_runs", return_value=[]):
        proposals = propose_updates.data_driven_proposals()
    matching = [p for p in proposals if "gate:bsr=fail" in p["finding"] and "100%" in p["finding"]]
    assert matching, f"expected a dead-gate finding, got: {proposals}"


def test_data_driven_flags_repeated_ip_cliff_brand():
    leads = [_lead(f"B0{i:04d}", adj_name="ip-cliff") for i in range(2)]
    with patch.object(db, "leads_with_outcomes", return_value=leads), \
            patch.object(db, "recent_runs", return_value=[]):
        proposals = propose_updates.data_driven_proposals()
    matching = [p for p in proposals if "TestBrand" in p["finding"] and p.get("ai_brain_key") == "brands.avoid"]
    assert matching, f"expected an IP-cliff brand finding, got: {proposals}"


def test_data_driven_flags_token_cost_drift():
    # System Blueprint assumes ~7500/day; simulate a run using far less (drained-key symptom
    # or a much smaller scan than assumed).
    runs = [{"tokens_consumed": 500} for _ in range(3)]
    with patch.object(db, "leads_with_outcomes", return_value=[]), \
            patch.object(db, "recent_runs", return_value=runs):
        proposals = propose_updates.data_driven_proposals()
    matching = [p for p in proposals if "token usage" in p["finding"]]
    assert matching, f"expected a token-drift finding, got: {proposals}"


def test_data_driven_no_drift_finding_when_usage_matches_assumption():
    runs = [{"tokens_consumed": propose_updates.ASSUMED_DAILY_TOKENS} for _ in range(3)]
    with patch.object(db, "leads_with_outcomes", return_value=[]), \
            patch.object(db, "recent_runs", return_value=runs):
        proposals = propose_updates.data_driven_proposals()
    matching = [p for p in proposals if "token usage" in p["finding"]]
    assert not matching


def test_data_driven_honest_when_no_runs_yet():
    with patch.object(db, "leads_with_outcomes", return_value=[]), \
            patch.object(db, "recent_runs", return_value=[]):
        proposals = propose_updates.data_driven_proposals()
    assert any("No run telemetry yet" in p["finding"] for p in proposals)


# ---------------------------------------------------------------------------
# Knowledge-driven — degrades honestly, never crashes the whole proposal run
# ---------------------------------------------------------------------------

def test_knowledge_driven_degrades_honestly_on_subprocess_failure():
    with patch.object(propose_updates, "os") as mock_os:
        mock_os.path.exists.return_value = True
        mock_os.path.dirname.return_value = "/fake"
        with patch.object(propose_updates.subprocess, "run", side_effect=Exception("timeout")):
            proposals = propose_updates.knowledge_driven_proposals()
    assert len(proposals) == 1
    assert proposals[0]["confidence"] == "unavailable"
    assert "timeout" in proposals[0]["finding"]


def test_knowledge_driven_honest_when_ask_py_missing():
    with patch("os.path.exists", return_value=False):
        proposals = propose_updates.knowledge_driven_proposals()
    assert proposals[0]["confidence"] == "unavailable"
    assert "not found" in proposals[0]["finding"]


# ---------------------------------------------------------------------------
# Report rendering + never touches ai-brain.json in practice, only REPORT_PATH
# ---------------------------------------------------------------------------

def test_render_report_honest_when_no_proposals():
    assert "No proposals this run" in propose_updates.render_report([])


def test_render_report_includes_human_review_note():
    proposals = [{"kind": "data-driven", "finding": "x", "sample_size": 1,
                 "confidence": "too small to act", "ai_brain_key": None}]
    report = propose_updates.render_report(proposals)
    assert "NOT changed by this script" in report
    assert "1 proposal(s) pending" in report


def test_collect_proposals_runs_once_for_write_report_with_count(tmp_report_path=None):
    """write_report_with_count() must call the underlying generators exactly once each — not
    twice (once for the report, once for the count) — since the knowledge-driven check shells
    out a subprocess."""
    call_count = {"n": 0}

    def fake_knowledge():
        call_count["n"] += 1
        return []

    with patch.object(propose_updates, "outcome_driven_proposals", return_value=[]), \
            patch.object(propose_updates, "data_driven_proposals", return_value=[]), \
            patch.object(propose_updates, "knowledge_driven_proposals", side_effect=fake_knowledge), \
            patch.object(propose_updates, "discord_router") as mock_router, \
            patch.object(propose_updates, "REPORT_PATH", os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "_tmp_brain_proposals_test.md")):
        try:
            block, count = propose_updates.write_report_with_count()
            assert call_count["n"] == 1
            assert count == 0
            mock_router.send.assert_not_called()  # zero proposals -> no Discord notify
        finally:
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_brain_proposals_test.md")
            if os.path.exists(p):
                os.remove(p)


# ---------------------------------------------------------------------------
# notify_brain_proposals — short embed to "brain_proposals", not the whole report
# ---------------------------------------------------------------------------

def test_notify_brain_proposals_noop_when_empty():
    with patch.object(propose_updates, "discord_router") as mock_router:
        assert propose_updates.notify_brain_proposals([]) is False
    mock_router.send.assert_not_called()


def test_notify_brain_proposals_sends_short_embed_with_top_finding():
    proposals = [
        {"kind": "outcome-driven", "finding": "gate:bsr=fail lost 5/6 times", "sample_size": 6,
         "confidence": "strong signal", "ai_brain_key": None},
        {"kind": "data-driven", "finding": "second finding", "sample_size": 2,
         "confidence": "too small to act", "ai_brain_key": None},
    ]
    with patch.object(propose_updates, "discord_router") as mock_router:
        mock_router.send.return_value = True
        ok = propose_updates.notify_brain_proposals(proposals)
    assert ok is True
    stream, embed = mock_router.send.call_args[0]
    assert stream == "brain_proposals"
    assert "2 new brain proposal" in embed["title"]
    assert "gate:bsr=fail" in embed["description"]


def test_write_report_with_count_notifies_when_proposals_exist():
    with patch.object(propose_updates, "outcome_driven_proposals",
                      return_value=[{"kind": "outcome-driven", "finding": "x", "sample_size": 5,
                                    "confidence": "strong signal", "ai_brain_key": None}]), \
            patch.object(propose_updates, "data_driven_proposals", return_value=[]), \
            patch.object(propose_updates, "knowledge_driven_proposals", return_value=[]), \
            patch.object(propose_updates, "discord_router") as mock_router, \
            patch.object(propose_updates, "REPORT_PATH", os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "_tmp_brain_proposals_test2.md")):
        mock_router.send.return_value = True
        try:
            block, count = propose_updates.write_report_with_count()
            assert count == 1
            mock_router.send.assert_called_once()
            assert mock_router.send.call_args[0][0] == "brain_proposals"
        finally:
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_brain_proposals_test2.md")
            if os.path.exists(p):
                os.remove(p)


def test_write_report_with_count_survives_notify_failure():
    """A bug in the Discord notify must never prevent the report from being written."""
    with patch.object(propose_updates, "outcome_driven_proposals",
                      return_value=[{"kind": "outcome-driven", "finding": "x", "sample_size": 5,
                                    "confidence": "strong signal", "ai_brain_key": None}]), \
            patch.object(propose_updates, "data_driven_proposals", return_value=[]), \
            patch.object(propose_updates, "knowledge_driven_proposals", return_value=[]), \
            patch.object(propose_updates, "notify_brain_proposals", side_effect=RuntimeError("boom")), \
            patch.object(propose_updates, "REPORT_PATH", os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "_tmp_brain_proposals_test3.md")):
        try:
            block, count = propose_updates.write_report_with_count()
            assert count == 1
            assert "1 proposal(s) pending" in block
        finally:
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_brain_proposals_test3.md")
            if os.path.exists(p):
                os.remove(p)


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
