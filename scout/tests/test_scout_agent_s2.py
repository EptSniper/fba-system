"""
Tests for Scout Agent Build Plan Prompt S2: operational doctrine wired into scoring/pipeline
(triage ranking, price-caution guard, avg90 BSR preference), scout/search_log.py (brand-growth
loop), and scout/ops_report.py (weekly KPIs).

Zero live network calls where mockable — `requests`/db calls are patched; matches the
project's existing hand-rolled test-runner convention (no pytest in this environment).
"""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import db  # noqa: E402
import ops_report  # noqa: E402
import scoring  # noqa: E402
import search_log  # noqa: E402


def oa_candidate(**kw):
    p = {
        "asin": "B0TEST", "price": 30.0, "weight_lb": 1.0, "sales_rank": 25000,
        "est_sales": 200, "offers": 6, "buybox_seller": "A1SELLER", "brand": "Jellycat",
        "avg_price_90": 29.0, "avg_offers_90": 6,
    }
    p.update(kw)
    return p


# ---------------------------------------------------------------------------
# avg90 BSR preference
# ---------------------------------------------------------------------------

def test_bsr_check_prefers_avg90_over_current_when_present():
    p = oa_candidate(sales_rank=500000, avg_sales_rank_90=50000)  # current fails, avg90 passes
    ex = scoring.explain_oa(p)
    bsr_check = next(c for c in ex["scored_checks"] if c["name"] == "bsr")
    assert bsr_check["source"] == "avg90"
    assert bsr_check["actual"] == 50000
    assert bsr_check["passed"] is True


def test_bsr_check_falls_back_to_current_without_avg90():
    p = oa_candidate(sales_rank=25000)
    ex = scoring.explain_oa(p)
    bsr_check = next(c for c in ex["scored_checks"] if c["name"] == "bsr")
    assert bsr_check["source"] == "current"
    assert bsr_check["actual"] == 25000


def test_bsr_check_source_none_when_neither_available():
    p = oa_candidate(sales_rank=None)
    ex = scoring.explain_oa(p)
    bsr_check = next(c for c in ex["scored_checks"] if c["name"] == "bsr")
    assert bsr_check["source"] == "none"
    assert bsr_check["actual"] is None


# ---------------------------------------------------------------------------
# price-caution vs price-spike (soft vs hard, mutually exclusive)
# ---------------------------------------------------------------------------

def test_price_caution_flagged_in_the_1_15_to_1_5_band():
    # 1.2x avg90 -> in the caution band (1.15-1.5), not yet a spike.
    p = oa_candidate(price=29.0 * 1.2, avg_price_90=29.0)
    ex = scoring.explain_oa(p)
    names = [a["name"] for a in ex["adjustments"]]
    assert "price-caution" in names
    assert "price-spike" not in names


def test_price_spike_supersedes_caution_no_double_penalty():
    # 1.6x avg90 -> a genuine spike; must NOT also fire the caution adjustment.
    p = oa_candidate(price=29.0 * 1.6, avg_price_90=29.0)
    ex = scoring.explain_oa(p)
    names = [a["name"] for a in ex["adjustments"]]
    assert "price-spike" in names
    assert "price-caution" not in names


def test_no_caution_or_spike_when_price_is_normal():
    p = oa_candidate(price=29.0, avg_price_90=29.0)
    ex = scoring.explain_oa(p)
    names = [a["name"] for a in ex["adjustments"]]
    assert "price-caution" not in names
    assert "price-spike" not in names


# ---------------------------------------------------------------------------
# triage_score — review-queue ranking by stressed payback speed, not headline ROI
# ---------------------------------------------------------------------------

def test_triage_score_none_without_price_or_sales():
    assert scoring.triage_score(oa_candidate(price=None)) is None
    assert scoring.triage_score(oa_candidate(est_sales=None)) is None


def test_triage_score_ranks_high_velocity_above_high_roi_low_velocity():
    # A: modest profit but high velocity. B: bigger headline ROI but low velocity.
    # Under the triage formula (profit * velocity / buy_cost), A should out-rank B even though
    # a pure ROI/profit sort would favor B — this is exactly the plan's point.
    a = oa_candidate(asin="B0FAST", price=20.0, est_sales=500)
    b = oa_candidate(asin="B0SLOW", price=20.0, est_sales=5)
    ta = scoring.triage_score(a)
    tb = scoring.triage_score(b)
    assert ta is not None and tb is not None
    assert ta > tb


def test_triage_score_never_appears_in_hard_reject_or_gates():
    # Sanity: triage_score is purely additive metadata, never referenced by oa_hard_reject().
    p = oa_candidate()
    p["triage_score"] = -999999  # an absurd value
    assert scoring.oa_hard_reject(p) is None  # must be unaffected


def test_pipeline_sorts_winners_by_triage_score():
    import pipeline

    fast = oa_candidate(asin="B0FAST", price=20.0, est_sales=500)
    slow = oa_candidate(asin="B0SLOW", price=20.0, est_sales=5)
    evaluated = pipeline._evaluate([slow, fast])  # slow first on purpose
    # Both should clear a low threshold; sort them the way run_once would.
    ordered = sorted(evaluated,
                     key=lambda x: (x.get("triage_score") if x.get("triage_score") is not None
                                    else x.get("blended_score", 0)),
                     reverse=True)
    assert ordered[0]["asin"] == "B0FAST"


# ---------------------------------------------------------------------------
# search_log — brand-growth loop scaffolding
# ---------------------------------------------------------------------------

def test_is_due_true_when_never_run():
    row = {"brand": "Jellycat", "last_run_at": None, "rerun_after_days": 21}
    import datetime as dt
    assert search_log._is_due(row, dt.datetime.now(dt.timezone.utc)) is True


def test_is_due_false_within_cadence():
    import datetime as dt
    now = dt.datetime.now(dt.timezone.utc)
    row = {"brand": "Jellycat", "last_run_at": (now - dt.timedelta(days=5)).isoformat(),
          "rerun_after_days": 21}
    assert search_log._is_due(row, now) is False


def test_is_due_true_after_cadence_elapses():
    import datetime as dt
    now = dt.datetime.now(dt.timezone.utc)
    row = {"brand": "Jellycat", "last_run_at": (now - dt.timedelta(days=30)).isoformat(),
          "rerun_after_days": 21}
    assert search_log._is_due(row, now) is True


def test_is_due_true_on_unparseable_timestamp():
    row = {"brand": "Jellycat", "last_run_at": "not-a-date", "rerun_after_days": 21}
    import datetime as dt
    assert search_log._is_due(row, dt.datetime.now(dt.timezone.utc)) is True


def test_is_due_handles_tz_naive_last_run_at():
    """Regression (Code Review 2026-07-02, nit): a last_run_at with no explicit UTC offset
    (e.g. '2026-06-01T12:00:00', no 'Z'/'+00:00') parses to a tz-NAIVE datetime via
    fromisoformat — subtracting it from the tz-aware `now` used to raise TypeError outright
    ("can't subtract offset-naive and offset-aware datetimes"), reproduced directly before this
    fix. Must degrade to treating it as UTC, not crash."""
    import datetime as dt
    now = dt.datetime.now(dt.timezone.utc)
    naive_5_days_ago = (now - dt.timedelta(days=5)).replace(tzinfo=None).isoformat()
    row_within_cadence = {"brand": "Jellycat", "last_run_at": naive_5_days_ago, "rerun_after_days": 21}
    assert search_log._is_due(row_within_cadence, now) is False  # must not raise, and be correct

    naive_30_days_ago = (now - dt.timedelta(days=30)).replace(tzinfo=None).isoformat()
    row_elapsed = {"brand": "Jellycat", "last_run_at": naive_30_days_ago, "rerun_after_days": 21}
    assert search_log._is_due(row_elapsed, now) is True


def test_due_searches_filters_via_db_rows():
    import datetime as dt
    now = dt.datetime.now(dt.timezone.utc)
    rows = [
        {"brand": "Due Brand", "last_run_at": None},
        {"brand": "Not Due Brand", "last_run_at": now.isoformat(), "rerun_after_days": 21},
    ]
    with patch.object(search_log.db, "all_search_log_rows", return_value=rows):
        due = search_log.due_searches(now)
    assert [r["brand"] for r in due] == ["Due Brand"]


def test_queue_brand_if_new_noop_for_falsy_brand():
    with patch.object(search_log.db, "queue_brand_search") as mock_queue:
        assert search_log.queue_brand_if_new(None) is None
        assert search_log.queue_brand_if_new("") is None
    mock_queue.assert_not_called()


def test_queue_brand_if_new_delegates_to_db():
    with patch.object(search_log.db, "queue_brand_search", return_value=7) as mock_queue:
        result = search_log.queue_brand_if_new("Jellycat", {"bsr_max": 200000})
    assert result == 7
    mock_queue.assert_called_once_with("Jellycat", {"bsr_max": 200000})


def test_log_decision_buy_queues_brand():
    supa_p = patch.object(db, "SUPA", "https://fake.supabase.co")
    key_p = patch.object(db, "KEY", "fake-key")
    with supa_p, key_p, patch.object(db, "requests") as mock_requests, \
         patch.object(db, "queue_brand_search") as mock_queue:
        r = MagicMock()
        r.raise_for_status = MagicMock()
        r.json.return_value = [{"id": 1}]
        mock_requests.post.return_value = r
        db.log_decision(1, "buy", brand="Jellycat")
    mock_queue.assert_called_once_with("Jellycat")


def test_log_decision_non_buy_does_not_queue_brand():
    supa_p = patch.object(db, "SUPA", "https://fake.supabase.co")
    key_p = patch.object(db, "KEY", "fake-key")
    with supa_p, key_p, patch.object(db, "requests") as mock_requests, \
         patch.object(db, "queue_brand_search") as mock_queue:
        r = MagicMock()
        r.raise_for_status = MagicMock()
        r.json.return_value = [{"id": 1}]
        mock_requests.post.return_value = r
        db.log_decision(1, "pass", brand="Jellycat")
    mock_queue.assert_not_called()


# ---------------------------------------------------------------------------
# ops_report — honest weekly KPIs
# ---------------------------------------------------------------------------

def test_ops_report_honest_empty_state():
    with patch.object(ops_report.db, "leads_with_outcomes", return_value=[]):
        block = ops_report.generate_report()
    assert "No realized outcomes yet" in block


def test_ops_report_computes_sell_through_and_roi_gap():
    leads = [
        {"roi": 0.35, "outcomes": [{"bought_qty": 10, "sold_qty": 30, "actual_roi": 0.20,
                                    "days_to_sell": 20}]},
        {"roi": 0.40, "outcomes": [{"bought_qty": 10, "sold_qty": 10, "actual_roi": 0.15,
                                    "days_to_sell": 40}]},
    ]
    with patch.object(ops_report.db, "leads_with_outcomes", return_value=leads):
        block = ops_report.generate_report()
    assert "Sell-through" in block
    assert "ROI gap" in block
    assert "NOT TRACKABLE" in block  # profit-per-review-hour is honestly unavailable


def test_ops_report_never_claims_untrackable_kpi_as_computed():
    with patch.object(ops_report.db, "leads_with_outcomes", return_value=[
        {"roi": 0.3, "outcomes": [{"bought_qty": 5, "sold_qty": 5, "days_to_sell": 10}]},
    ]):
        block = ops_report.generate_report()
    assert "Profit per review-hour" in block
    assert "NOT TRACKABLE" in block


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
