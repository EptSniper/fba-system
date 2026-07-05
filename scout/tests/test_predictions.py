"""Tests for predictions.py — the prediction ledger scaffold (Code Review 2026-07-04)."""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import predictions  # noqa: E402


# ---------------------------------------------------------------------------
# build_predictions_for() — pure, no I/O
# ---------------------------------------------------------------------------

def test_price_reversion_fires_on_price_spike():
    p = {"price": 30.0, "avg_price_90": 20.0, "est_sales": None}
    explanation = {"adjustments": [{"name": "price-spike", "points": -15, "reason": "r"}]}
    claims = predictions.build_predictions_for(p, explanation)
    assert len(claims) == 1
    assert claims[0]["claim_type"] == "price_reversion"
    assert claims[0]["threshold"] == 20.0
    assert claims[0]["horizon_days"] == 14


def test_price_reversion_fires_on_price_caution():
    p = {"price": 23.0, "avg_price_90": 20.0}
    explanation = {"adjustments": [{"name": "price-caution", "points": -5, "reason": "r"}]}
    claims = predictions.build_predictions_for(p, explanation)
    assert any(c["claim_type"] == "price_reversion" for c in claims)


def test_price_reversion_does_not_fire_without_avg_price_90():
    p = {"price": 30.0, "avg_price_90": None}
    explanation = {"adjustments": [{"name": "price-spike", "points": -15, "reason": "r"}]}
    claims = predictions.build_predictions_for(p, explanation)
    assert not any(c["claim_type"] == "price_reversion" for c in claims)


def test_offer_trend_fires_on_offers_rising():
    p = {"offers": 20, "avg_offers_90": 10}
    explanation = {"adjustments": [{"name": "offers-rising", "points": -12, "reason": "r"}]}
    claims = predictions.build_predictions_for(p, explanation)
    assert any(c["claim_type"] == "offer_trend" and c["threshold"] == 20 for c in claims)


def test_offer_trend_fires_on_ip_cliff_hard_reject():
    p = {"offers": 1, "avg_offers_90": 40}
    explanation = {"adjustments": [], "hard_reject": "Offer count collapsed (IP-complaint cliff) — account-health risk"}
    claims = predictions.build_predictions_for(p, explanation)
    assert any(c["claim_type"] == "offer_trend" and c["threshold"] == 1 for c in claims)


def test_velocity_always_fires_when_est_sales_present():
    p = {"est_sales": 100}
    explanation = {"adjustments": []}
    claims = predictions.build_predictions_for(p, explanation)
    velocity = [c for c in claims if c["claim_type"] == "velocity"]
    assert len(velocity) == 1
    assert velocity[0]["threshold"] == 70.0  # 70% of 100


def test_velocity_does_not_fire_without_est_sales():
    p = {"est_sales": None}
    explanation = {"adjustments": []}
    claims = predictions.build_predictions_for(p, explanation)
    assert not any(c["claim_type"] == "velocity" for c in claims)


def test_no_claims_from_a_clean_candidate_with_no_signals():
    p = {"price": 20.0, "avg_price_90": 20.0, "offers": 10, "avg_offers_90": 10, "est_sales": None}
    explanation = {"adjustments": []}
    claims = predictions.build_predictions_for(p, explanation)
    assert claims == []


def test_multiple_claims_can_coexist():
    p = {"price": 30.0, "avg_price_90": 20.0, "offers": 20, "avg_offers_90": 10, "est_sales": 100}
    explanation = {"adjustments": [
        {"name": "price-spike", "points": -15, "reason": "r"},
        {"name": "offers-rising", "points": -12, "reason": "r"},
    ]}
    claims = predictions.build_predictions_for(p, explanation)
    types = {c["claim_type"] for c in claims}
    assert types == {"price_reversion", "offer_trend", "velocity"}


# ---------------------------------------------------------------------------
# record_predictions_for() — degrades honestly when Supabase isn't configured
# ---------------------------------------------------------------------------

def test_record_predictions_returns_zero_when_disabled():
    with patch.object(predictions.db, "enabled", return_value=False):
        n = predictions.record_predictions_for("B0TEST", None, {"price": 30.0}, {"adjustments": []})
    assert n == 0


def test_record_predictions_writes_one_row_per_claim():
    p = {"price": 30.0, "avg_price_90": 20.0, "est_sales": 100}
    explanation = {"adjustments": [{"name": "price-spike", "points": -15, "reason": "r"}]}
    with patch.object(predictions.db, "enabled", return_value=True), \
         patch.object(predictions.db, "_post", return_value=1) as mock_post:
        n = predictions.record_predictions_for("B0TEST", 42, p, explanation)
    assert n == 2  # price_reversion + velocity
    assert mock_post.call_count == 2
    for call in mock_post.call_args_list:
        row = call[0][1]
        assert row["asin"] == "B0TEST"
        assert row["lead_id"] == 42


# ---------------------------------------------------------------------------
# _resolve_hit() — the hit/miss arithmetic for each claim type
# ---------------------------------------------------------------------------

def test_resolve_hit_price_reversion():
    assert predictions._resolve_hit("price_reversion", threshold=20.0, actual=21.0) is True   # within 10%
    assert predictions._resolve_hit("price_reversion", threshold=20.0, actual=25.0) is False  # still elevated


def test_resolve_hit_offer_trend():
    assert predictions._resolve_hit("offer_trend", threshold=20, actual=25) is True   # kept rising
    assert predictions._resolve_hit("offer_trend", threshold=20, actual=10) is False  # recovered


def test_resolve_hit_velocity():
    assert predictions._resolve_hit("velocity", threshold=70.0, actual=80.0) is True   # held
    assert predictions._resolve_hit("velocity", threshold=70.0, actual=40.0) is False  # collapsed


# ---------------------------------------------------------------------------
# score_matured_predictions() — key-gated (Keepa-gated) honesty
# ---------------------------------------------------------------------------

def test_score_matured_predictions_unavailable_without_fetch_fn():
    result = predictions.score_matured_predictions(fetch_fresh_stats=None)
    assert result["status"] == "unavailable"
    assert "KEEPA_KEY" in result["reason"] or "Keepa" in result["reason"]


def test_score_matured_predictions_unavailable_without_supabase():
    with patch.object(predictions.db, "enabled", return_value=False):
        result = predictions.score_matured_predictions(fetch_fresh_stats=lambda asin: {"price": 1})
    assert result["status"] == "unavailable"


def test_score_matured_predictions_scores_a_mocked_matured_row():
    matured_row = {
        "id": 1, "asin": "B0TEST", "claim_type": "price_reversion", "threshold": 20.0,
        "horizon_days": 14, "made_at": "2020-01-01T00:00:00Z",
    }
    with patch.object(predictions.db, "enabled", return_value=True), \
         patch.object(predictions, "fetch_unresolved", return_value=[matured_row]), \
         patch.object(predictions, "_mark_resolved") as mock_mark:
        result = predictions.score_matured_predictions(fetch_fresh_stats=lambda asin: {"price": 21.0})
    assert result["status"] == "ok"
    assert result["scored"] == 1
    assert result["hits"] == 1
    mock_mark.assert_called_once_with(1, True, 21.0)


# ---------------------------------------------------------------------------
# hit_rate_summary() — the ops-report.md line
# ---------------------------------------------------------------------------

def test_hit_rate_summary_unavailable():
    summary = predictions.hit_rate_summary(fetch_fresh_stats=None)
    assert "not available" in summary


def test_hit_rate_summary_no_matured():
    with patch.object(predictions, "score_matured_predictions",
                      return_value={"status": "ok", "scored": 0, "hits": 0, "by_claim_type": {}}):
        summary = predictions.hit_rate_summary(fetch_fresh_stats=lambda asin: None)
    assert "no matured predictions" in summary


def test_hit_rate_summary_with_results():
    fake_result = {"status": "ok", "scored": 4, "hits": 3,
                   "by_claim_type": {"price_reversion": {"scored": 4, "hits": 3}}}
    with patch.object(predictions, "score_matured_predictions", return_value=fake_result):
        summary = predictions.hit_rate_summary(fetch_fresh_stats=lambda asin: None)
    assert "4 matured" in summary
    assert "75%" in summary
    assert "price_reversion" in summary
