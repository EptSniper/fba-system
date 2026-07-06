"""
Tests for System Blueprint Prompt 3.1: label builder + calibration/tuning reports.

Zero live network calls — db.leads_with_outcomes() is mocked; the local-ledger tests use a
temp events.jsonl. Run: python tests/test_labels_and_reports.py  (or pytest).
"""
import ast
import inspect
import json
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402
import labels  # noqa: E402
import tuning_report  # noqa: E402
import calibration_report  # noqa: E402
from ast_guards import assert_only_write_target, open_call_targets_containing  # noqa: E402


# ---------------------------------------------------------------------------
# Leakage prevention
# ---------------------------------------------------------------------------

def test_labels_excludes_post_decision_fields_even_if_stored():
    """Even if a stored features_snapshot somehow carried a post-decision field (e.g. an older
    lead written before this guard existed), assemble_training_rows() must never surface it."""
    leaky_lead = {
        "asin": "B0LEAKTEST", "found_via": "scout",
        "features_snapshot": {
            "asin": "B0LEAKTEST", "price": 20.0, "offers": 5,
            # post-decision fields that must never reach the trainable feature set:
            "rule_score": 95.0, "blended_score": 95.0, "verdict": "review", "reason": "great",
        },
        "outcomes": [{"actual_profit": 10.0, "price_tanked": False}],
    }
    with patch.object(db, "leads_with_outcomes", return_value=[leaky_lead]):
        result = labels.assemble_training_rows()

    assert result["trainable_count"] == 1
    features = result["rows"][0]["features"]
    forbidden = {"rule_score", "blended_score", "verdict", "reason"}
    assert not (forbidden & features.keys()), f"leaked: {forbidden & features.keys()}"
    assert set(features.keys()) <= set(db.PRE_DECISION_FEATURES)


# ---------------------------------------------------------------------------
# Minimum-rows refusal
# ---------------------------------------------------------------------------

def _fake_lead(asin, profit, price_tanked=False):
    return {
        "asin": asin, "found_via": "scout",
        "features_snapshot": {"asin": asin, "price": 20.0, "offers": 5, "bsr": 10000},
        "outcomes": [{"actual_profit": profit, "price_tanked": price_tanked}],
    }


def test_assemble_refuses_below_minimum():
    few = [_fake_lead(f"B0{i:08d}", 5.0) for i in range(5)]  # well below default min (30)
    with patch.object(db, "leads_with_outcomes", return_value=few), \
            patch.object(labels, "_read_events", return_value=[]):
        result = labels.assemble_training_rows()
    assert result["trainable_count"] == 5
    assert result["refused"] is True
    assert "5 trainable" in result["reason"]


def test_assemble_refuses_when_only_one_class_present():
    """Enough rows, but all the SAME outcome — still refused, needs both classes."""
    with patch.object(labels, "min_labeled_rows", return_value=3):
        all_wins = [_fake_lead(f"B0{i:08d}", 5.0) for i in range(5)]
        with patch.object(db, "leads_with_outcomes", return_value=all_wins), \
                patch.object(labels, "_read_events", return_value=[]):
            result = labels.assemble_training_rows()
    assert result["trainable_count"] == 5
    assert result["positive"] == 5 and result["negative"] == 0
    assert result["refused"] is True
    assert "one class" in result["reason"]


def test_assemble_accepts_when_both_conditions_met():
    with patch.object(labels, "min_labeled_rows", return_value=3):
        mixed = [_fake_lead(f"B0{i:08d}", 5.0) for i in range(3)] + \
                [_fake_lead(f"B1{i:08d}", -5.0) for i in range(3)]
        with patch.object(db, "leads_with_outcomes", return_value=mixed), \
                patch.object(labels, "_read_events", return_value=[]):
            result = labels.assemble_training_rows()
    assert result["trainable_count"] == 6
    assert result["positive"] == 3 and result["negative"] == 3
    assert result["refused"] is False


# ---------------------------------------------------------------------------
# Bronze (decision-only, no outcome) — Session 55's training-objective fix: bronze must NEVER
# enter the relevance target (`rows`/`by_tier`), only the separate bronze_rows/bronze_tier for
# train_ranker.py's auxiliary "agreement with operator" metric.
# ---------------------------------------------------------------------------

def _decision_only_lead(asin, decision, snapshot=True):
    lead = {
        "asin": asin, "found_via": "scout",
        "decisions": [{"decision": decision, "created_at": "2026-07-01T00:00:00Z"}],
        "outcomes": [],
    }
    if snapshot:
        lead["features_snapshot"] = {"asin": asin, "price": 20.0, "offers": 5, "bsr": 10000}
    return lead


def test_bronze_rows_excluded_from_relevance_target():
    leads = [_fake_lead(f"B0{i:08d}", 5.0) for i in range(3)] + \
            [_fake_lead(f"B1{i:08d}", -5.0) for i in range(3)] + \
            [_decision_only_lead("B0BRONZE1", "buy"), _decision_only_lead("B0BRONZE2", "pass")]
    with patch.object(labels, "min_labeled_rows", return_value=3), \
            patch.object(db, "leads_with_outcomes", return_value=leads), \
            patch.object(labels, "_read_events", return_value=[]):
        result = labels.assemble_training_rows()

    # the relevance target (`rows`) must contain ONLY the 6 gold rows — never a bronze one
    assert result["trainable_count"] == 6
    assert all(r["label_quality"] != "bronze" for r in result["rows"])
    assert "bronze" not in result["by_tier"]

    # bronze is surfaced SEPARATELY, with both a buy and a pass decision correctly labeled
    assert result["bronze_tier"]["total"] == 2
    assert result["bronze_tier"]["positive"] == 1  # "buy"
    assert result["bronze_tier"]["negative"] == 1  # "pass"
    bronze_asins = {r["asin"]: r["label"] for r in result["bronze_rows"]}
    assert bronze_asins == {"B0BRONZE1": True, "B0BRONZE2": False}


def test_bronze_skips_ambiguous_decisions():
    leads = [_decision_only_lead("B0TEST1", "test"), _decision_only_lead("B0WAIT1", "wait")]
    with patch.object(db, "leads_with_outcomes", return_value=leads), \
            patch.object(labels, "_read_events", return_value=[]):
        result = labels.assemble_training_rows()
    assert result["bronze_tier"]["total"] == 0


def test_bronze_excludes_leads_with_a_real_outcome():
    """A lead with BOTH a decision and a realized outcome is gold, not bronze — never double-count."""
    lead = _fake_lead("B0GOLD1", 5.0)
    lead["decisions"] = [{"decision": "buy", "created_at": "2026-07-01T00:00:00Z"}]
    with patch.object(labels, "min_labeled_rows", return_value=1), \
            patch.object(db, "leads_with_outcomes", return_value=[lead]), \
            patch.object(labels, "_read_events", return_value=[]):
        result = labels.assemble_training_rows()
    assert result["bronze_tier"]["total"] == 0
    assert result["by_tier"]["gold"]["total"] == 1


def test_bronze_without_feature_snapshot_excluded_from_bronze_rows():
    leads = [_decision_only_lead("B0NOSNAP", "buy", snapshot=False)]
    with patch.object(db, "leads_with_outcomes", return_value=leads), \
            patch.object(labels, "_read_events", return_value=[]):
        result = labels.assemble_training_rows()
    assert result["bronze_rows"] == []


# ---------------------------------------------------------------------------
# Linkage round-trip (local ledger, ASIN-matched lead -> outcome)
# ---------------------------------------------------------------------------

def test_local_ledger_links_lead_and_outcome_by_asin():
    events = [
        {"id": "1", "ts": "2026-07-01T10:00:00Z", "kind": "lead",
         "payload": {"product": "Test Widget", "asin": "B0LINKTEST", "status": "researching"}},
        {"id": "2", "ts": "2026-07-02T10:00:00Z", "kind": "outcome",
         "payload": {"product": "Test Widget", "asin": "B0LINKTEST", "boughtQty": 10,
                     "soldQty": 10, "actualProfit": 42.5}},
    ]
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
        path = f.name
    try:
        with patch.object(labels, "EVENTS_PATH", path):
            rows = labels._from_local_ledger()
        assert len(rows) == 1
        assert rows[0]["asin"] == "B0LINKTEST"
        assert rows[0]["label"] is True  # actualProfit=42.5 > 0, not tanked
        assert rows[0]["features"] is None  # local ledger never has a feature snapshot
    finally:
        os.unlink(path)


def test_local_ledger_ignores_leads_without_a_matching_outcome():
    events = [
        {"id": "1", "ts": "2026-07-01T10:00:00Z", "kind": "lead",
         "payload": {"product": "No Outcome Yet", "asin": "B0NOOUTCOME", "status": "researching"}},
    ]
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
        path = f.name
    try:
        with patch.object(labels, "EVENTS_PATH", path):
            rows = labels._from_local_ledger()
        assert rows == []
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# label_from_outcome — both naming conventions, both signals
# ---------------------------------------------------------------------------

def test_label_from_outcome_prefers_would_rebuy():
    assert labels.label_from_outcome({"would_rebuy": True, "actual_profit": -100}) is True
    assert labels.label_from_outcome({"would_rebuy": False, "actual_profit": 100}) is False


def test_label_from_outcome_falls_back_to_profit():
    assert labels.label_from_outcome({"actual_profit": 10}) is True
    assert labels.label_from_outcome({"actualProfit": 10}) is True  # local-ledger naming
    assert labels.label_from_outcome({"actual_profit": -1}) is False
    assert labels.label_from_outcome({"actual_profit": 10, "price_tanked": True}) is False
    assert labels.label_from_outcome({}) is None


# ---------------------------------------------------------------------------
# tuning_report — never writes to ai-brain.json (guard test)
# ---------------------------------------------------------------------------

def test_tuning_report_has_no_write_path_to_ai_brain_json():
    """Static guard via real AST parsing (not text-matching, which false-positives on the
    module's own docstrings): every write-like call in the file (bare open(), os/io/codecs-style
    open(), and pathlib .write_text()/.write_bytes()/.open() method calls — Code Review
    2026-07-02, Finding S9 broadened this beyond a bare open() scan) must target REPORT_PATH.
    Catches a future edit accidentally adding an ai-brain.json write/auto-apply path."""
    assert_only_write_target(tuning_report, "REPORT_PATH")
    assert open_call_targets_containing(tuning_report, "ai-brain.json") == []
    # The module doesn't even define a path constant for ai-brain.json (unlike labels.py,
    # which deliberately READS it, via BRAIN_PATH, only for min_labeled_rows).
    assert "BRAIN_PATH" not in inspect.getsource(tuning_report)


def test_tuning_report_honest_when_no_data():
    with patch.object(db, "leads_with_outcomes", return_value=[]):
        report = tuning_report.generate_report()
    assert "Nothing to analyze" in report


def test_tuning_report_flags_lopsided_pattern_with_enough_samples():
    leads = []
    for i in range(4):
        leads.append({
            "asin": f"B0BAD{i:04d}",
            "explanation": {"scored_checks": [], "adjustments": [{"name": "price-spike", "points": -15, "reason": "x"}]},
            "outcomes": [{"actual_profit": -5.0}],
        })
    with patch.object(db, "leads_with_outcomes", return_value=leads):
        report = tuning_report.generate_report()
    assert "adjustment:price-spike" in report
    assert "Suggestions for human review" in report
    assert "ai-brain.json is NOT changed" in report


def test_tuning_report_does_not_suggest_below_sample_floor():
    leads = [{
        "asin": "B0SINGLE", "explanation": {"scored_checks": [], "adjustments": [{"name": "ip-cliff", "points": -20, "reason": "x"}]},
        "outcomes": [{"actual_profit": -5.0}],
    }]
    with patch.object(db, "leads_with_outcomes", return_value=leads):
        report = tuning_report.generate_report()
    assert "No pattern crosses the suggestion bar" in report


# ---------------------------------------------------------------------------
# calibration_report — honest refusal, no promotion claim
# ---------------------------------------------------------------------------

def test_calibration_report_refuses_with_no_data():
    with patch.object(labels, "assemble_training_rows", return_value={
        "rows": [], "trainable_count": 0, "labeled_count": 0, "positive": 0, "negative": 0,
        "min_required": 30, "refused": True, "reason": "0 trainable labeled rows (< 30 required)",
    }):
        report = calibration_report.generate_report()
    assert "NOT enough data to promote" in report
    assert "nothing was promoted" in report


def test_calibration_summary_available_false_below_ten_rows():
    rows = [{"features": {"price": 10.0, "offers": 5}, "label": True} for _ in range(5)]
    summary = calibration_report.calibration_summary(rows)
    assert summary["available"] is False


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
