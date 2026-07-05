"""
Tests for Scout Agent Build Plan Prompt S4: scout/mcp_server.py's read-only tool functions.

The real `mcp` package requires Python 3.10+ and is NOT installed in this repo's Python 3.9
dev environment (verified: `pip install mcp` fails with "no matching distribution" — a real
package constraint, not a bug). These tests therefore cover the query functions directly
(zero dependency on `mcp`) plus an AST-based guard proving the module can only ever call
read-only db functions. build_server()/FastMCP wiring is exercised only for its honest
ImportError when the package is absent.
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402
import mcp_server  # noqa: E402
from ast_guards import find_module_calls  # noqa: E402

# The ONLY db functions this module may call — every one is read-only. Anything else showing
# up as `db.<name>` in the source (or via `from db import <name>` + a bare call, or `import db
# as <alias>` + `<alias>.<name>` — Code Review 2026-07-02, Finding S9) is a bug this test
# catches structurally, not by string luck.
_ALLOWED_DB_CALLS = {"get_lead", "top_leads_raw", "leads_by_brand", "recent_runs"}


def test_mcp_server_only_calls_allowlisted_read_only_db_functions():
    found = find_module_calls(mcp_server, "db", {"db"})
    assert found, "expected at least one db call in mcp_server.py"
    assert found <= _ALLOWED_DB_CALLS, f"unexpected db call(s) in mcp_server.py: {found - _ALLOWED_DB_CALLS}"


def test_mcp_server_from_import_bypass_is_still_caught():
    """Regression for Finding S9: a hypothetical `from db import queue_brand_search` + a bare
    `queue_brand_search(...)` call has no `db.` prefix at all — the ORIGINAL guard (a plain
    `db.<name>` attribute scan) would have missed this entirely. Prove find_module_calls() still
    catches it, against a raw source snippet (mcp_server.py itself doesn't do this)."""
    fake_source = (
        "from db import queue_brand_search\n"
        "def f():\n"
        "    return queue_brand_search('x')\n"
    )
    found = find_module_calls(fake_source, "db", {"db"})
    assert "queue_brand_search" in found


def test_mcp_server_aliased_import_bypass_is_still_caught():
    """Regression for Finding S9: `import db as d` then `d.<name>(...)` — the alias isn't
    literally "db", so a scan hardcoded to node.value.id == "db" would miss it."""
    fake_source = (
        "import db as d\n"
        "def f():\n"
        "    return d.queue_brand_search('x')\n"
    )
    found = find_module_calls(fake_source, "db", {"db"})
    assert "queue_brand_search" in found


def test_build_server_raises_honest_import_error_without_mcp_package():
    if mcp_server.FastMCP is not None:
        return  # real package IS installed in this environment; nothing to assert here
    try:
        mcp_server.build_server()
        assert False, "expected ImportError"
    except ImportError as e:
        assert "3.10" in str(e) or "mcp" in str(e).lower()


# ---------------------------------------------------------------------------
# get_lead
# ---------------------------------------------------------------------------

def test_get_lead_found():
    with patch.object(mcp_server.db, "get_lead", return_value={"asin": "B0X", "verdict": "review"}):
        result = mcp_server.get_lead("B0X")
    assert result["found"] is True
    assert result["verdict"] == "review"


def test_get_lead_not_found_is_honest():
    with patch.object(mcp_server.db, "get_lead", return_value=None):
        result = mcp_server.get_lead("B0MISSING")
    assert result["found"] is False
    assert "No lead" in result["message"]


# ---------------------------------------------------------------------------
# top_leads — triage-value ranking, unranked leads sort last
# ---------------------------------------------------------------------------

def test_top_leads_ranks_by_triage_value_descending():
    rows = [
        {"asin": "B0LOW", "profit": 2.0, "monthly_sales": 50, "buy_cost": 10.0},
        {"asin": "B0HIGH", "profit": 5.0, "monthly_sales": 300, "buy_cost": 10.0},
    ]
    with patch.object(mcp_server.db, "top_leads_raw", return_value=rows):
        result = mcp_server.top_leads(n=2)
    assert [r["asin"] for r in result] == ["B0HIGH", "B0LOW"]


def test_top_leads_unranked_rows_sort_last_not_as_zero():
    rows = [
        {"asin": "B0UNRANKED", "profit": None, "monthly_sales": None, "buy_cost": None},
        {"asin": "B0RANKED", "profit": 1.0, "monthly_sales": 10, "buy_cost": 5.0},
    ]
    with patch.object(mcp_server.db, "top_leads_raw", return_value=rows):
        result = mcp_server.top_leads(n=2)
    assert result[0]["asin"] == "B0RANKED"
    assert result[-1]["asin"] == "B0UNRANKED"
    assert result[-1]["triage_value"] is None


def test_top_leads_prefers_exact_scoring_triage_score_when_snapshot_present():
    snapshot = {"price": 30.0, "weight_lb": 1.0, "est_sales": 200}
    rows = [{"asin": "B0EXACT", "features_snapshot": snapshot,
            "profit": 999, "monthly_sales": 1, "buy_cost": 1}]  # would rank wildly different via fallback
    with patch.object(mcp_server.db, "top_leads_raw", return_value=rows):
        result = mcp_server.top_leads(n=1)
    expected = mcp_server.scoring.triage_score(snapshot)
    assert result[0]["triage_value"] == expected
    assert expected != round(999 * 1 / 1, 3)  # proves the fallback path was NOT used


# ---------------------------------------------------------------------------
# why_rejected
# ---------------------------------------------------------------------------

def test_why_rejected_no_lead():
    with patch.object(mcp_server.db, "get_lead", return_value=None):
        result = mcp_server.why_rejected("B0MISSING")
    assert result["found"] is False


def test_why_rejected_no_explanation_stored():
    with patch.object(mcp_server.db, "get_lead",
                      return_value={"asin": "B0X", "verdict": "pass", "score": 40, "reason": "low ROI"}):
        result = mcp_server.why_rejected("B0X")
    assert result["found"] is True
    assert "No structured explanation" in result["message"]


def test_why_rejected_returns_stored_scored_checks_and_adjustments():
    explanation = {"verdict": "pass", "score": 20, "hard_reject": "Amazon holds the Buy Box",
                  "scored_checks": [{"name": "bsr", "passed": True}], "adjustments": []}
    with patch.object(mcp_server.db, "get_lead", return_value={"asin": "B0X", "explanation": explanation}):
        result = mcp_server.why_rejected("B0X")
    assert result["hard_reject"] == "Amazon holds the Buy Box"
    assert result["scored_checks"] == explanation["scored_checks"]


# ---------------------------------------------------------------------------
# brand_history
# ---------------------------------------------------------------------------

def test_brand_history_no_leads():
    with patch.object(mcp_server.db, "leads_by_brand", return_value=[]):
        result = mcp_server.brand_history("Nonexistent Brand")
    assert result["lead_count"] == 0


def test_brand_history_counts_verdicts_and_outcomes():
    leads = [
        {"verdict": "review", "outcomes": [{"actual_roi": 0.2}]},
        {"verdict": "review", "outcomes": []},
        {"verdict": "pass", "outcomes": []},
    ]
    with patch.object(mcp_server.db, "leads_by_brand", return_value=leads):
        result = mcp_server.brand_history("Jellycat")
    assert result["lead_count"] == 3
    assert result["verdict_counts"] == {"review": 2, "pass": 1}
    assert result["outcome_count"] == 1


def test_brand_history_reads_memory_note_when_file_exists(tmp_path=None):
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        with patch.object(mcp_server, "MEMORY_BRANDS_DIR", d):
            with open(os.path.join(d, "jellycat.md"), "w", encoding="utf-8") as f:
                f.write("## Verdict history\nAlways a safe brand.\n")
            with patch.object(mcp_server.db, "leads_by_brand", return_value=[{"verdict": "review", "outcomes": []}]):
                result = mcp_server.brand_history("Jellycat")
    assert result["memory_note"] and "safe brand" in result["memory_note"]


def test_brand_history_memory_note_none_when_file_absent():
    with patch.object(mcp_server, "MEMORY_BRANDS_DIR", "Z:/does/not/exist"):
        with patch.object(mcp_server.db, "leads_by_brand", return_value=[{"verdict": "review", "outcomes": []}]):
            result = mcp_server.brand_history("Brand Nobody Wrote Notes For")
    assert result["memory_note"] is None


# ---------------------------------------------------------------------------
# run_stats
# ---------------------------------------------------------------------------

def test_run_stats_no_runs_in_window():
    with patch.object(mcp_server.db, "recent_runs", return_value=[]):
        result = mcp_server.run_stats(days=7)
    assert result["run_count"] == 0


def test_run_stats_aggregates_status_and_tokens():
    import datetime as dt
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    runs = [
        {"started_at": now, "status": "success", "tokens_consumed": 100},
        {"started_at": now, "status": "success", "tokens_consumed": 200},
        {"started_at": now, "status": "failed", "tokens_consumed": None},
    ]
    with patch.object(mcp_server.db, "recent_runs", return_value=runs):
        result = mcp_server.run_stats(days=7)
    assert result["run_count"] == 3
    assert result["status_counts"] == {"success": 2, "failed": 1}
    assert result["avg_tokens_consumed"] == 150.0


def test_run_stats_filters_out_of_window_runs():
    import datetime as dt
    old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)).isoformat()
    with patch.object(mcp_server.db, "recent_runs", return_value=[{"started_at": old, "status": "success"}]):
        result = mcp_server.run_stats(days=7)
    assert result["run_count"] == 0


# ---------------------------------------------------------------------------
# search_log_due
# ---------------------------------------------------------------------------

def test_search_log_due_delegates_to_search_log_module():
    with patch.object(mcp_server.search_log, "due_searches", return_value=[{"brand": "Jellycat"}]):
        result = mcp_server.search_log_due()
    assert result == [{"brand": "Jellycat"}]


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
