"""
Tests for System Blueprint Prompt G1: idempotent Supabase writes + the `runs` table.

Zero live network calls — `requests` is mocked throughout, matching the project's existing
zero-dependency test convention (python tests/test_db_idempotency.py or pytest).
"""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402
import pipeline  # noqa: E402


def _enabled_db():
    """Context: db.enabled() reports True without needing real SUPA/KEY env vars."""
    return patch.object(db, "SUPA", "https://fake.supabase.co"), patch.object(db, "KEY", "fake-key")


def _mock_response(json_body, status=200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_body
    r.raise_for_status = MagicMock() if status < 400 else MagicMock(side_effect=Exception(f"HTTP {status}"))
    return r


# ---------------------------------------------------------------------------
# Upsert idempotency (leads asin+found_via, keepa_snapshots asin+snapshot_date)
# ---------------------------------------------------------------------------

def test_upsert_lead_uses_on_conflict_and_merge_duplicates():
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_response([{"id": 1}])
        db.log_lead({"asin": "B0IDEMP01", "price": 10.0}, 80, "review", "test reason")

        assert mock_requests.post.called
        url = mock_requests.post.call_args[0][0]
        headers = mock_requests.post.call_args[1]["headers"]
        assert "on_conflict=asin%2Cfound_via" in url or "on_conflict=asin,found_via" in url
        assert "merge-duplicates" in headers["Prefer"]


def test_upsert_lead_same_asin_twice_hits_same_endpoint_shape():
    """Two calls with the same ASIN must produce IDENTICAL upsert requests (same on_conflict
    target) — real deduplication is enforced by Postgres's unique index once migration 001 is
    applied; this test locks in that the APPLICATION always asks for that behavior."""
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_response([{"id": 1}])
        db.log_lead({"asin": "B0IDEMP02", "price": 10.0}, 80, "review", "first pass")
        db.log_lead({"asin": "B0IDEMP02", "price": 12.0}, 85, "review", "second pass")

        assert mock_requests.post.call_count == 2
        url1 = mock_requests.post.call_args_list[0][0][0]
        url2 = mock_requests.post.call_args_list[1][0][0]
        assert url1 == url2, "re-scoring the same ASIN must target the same upsert endpoint"


def test_upsert_falls_back_to_plain_insert_when_on_conflict_unavailable():
    """If the unique index doesn't exist yet (migration 001 not applied), the upsert POST
    raises — db.py must fall back to a plain insert rather than losing the write."""
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        upsert_fail = _mock_response({"code": "42P10", "message": "no unique constraint"}, status=400)
        plain_ok = _mock_response([{"id": 7}])
        mock_requests.post.side_effect = [upsert_fail, plain_ok]

        lead_id = db.log_lead({"asin": "B0NOMIGRATION", "price": 10.0}, 80, "review", "reason")

        assert lead_id == 7
        assert mock_requests.post.call_count == 2
        # first call attempted on_conflict, second was a plain insert (no on_conflict param)
        assert "on_conflict" in mock_requests.post.call_args_list[0][0][0]
        assert "on_conflict" not in mock_requests.post.call_args_list[1][0][0]


def test_upsert_keepa_snapshot_no_asin_is_noop():
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        assert db.upsert_keepa_snapshot({"price": 10.0}) is None
        mock_requests.post.assert_not_called()


def test_upsert_keepa_snapshot_sends_explicit_local_snapshot_date():
    """Code Review 2026-07-02, Finding S7: snapshot_date must be sent explicitly (today's
    LOCAL date) — migration 001 no longer derives it from captured_at via a generated UTC
    column, which mis-bucketed late-evening local runs into "tomorrow."""
    import datetime as _dt
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_response([{"id": 1}])
        db.upsert_keepa_snapshot({"asin": "B0DATE01", "price": 10.0})
    sent = mock_requests.post.call_args[1]["json"]
    assert sent.get("snapshot_date") == _dt.date.today().isoformat()


def test_is_missing_constraint_error_detects_42P10():
    r = _mock_response({"code": "42P10", "message": "no unique constraint"}, status=400)
    assert db._is_missing_constraint_error(r) is True


def test_is_missing_constraint_error_false_for_unrelated_errors():
    r = _mock_response({"code": "23505", "message": "duplicate key value"}, status=409)
    assert db._is_missing_constraint_error(r) is False
    assert db._is_missing_constraint_error(None) is False


def test_upsert_error_message_distinguishes_missing_migration_from_other_failures(capsys=None):
    """Code Review 2026-07-02, Finding S11: a non-42P10 failure (network down, bad payload,
    an unrelated conflict) must NOT tell the operator to run a migration that isn't the
    actual problem."""
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests, \
            patch("builtins.print") as mock_print:
        unrelated_fail = _mock_response({"code": "23505", "message": "duplicate key value"}, status=409)
        plain_ok = _mock_response([{"id": 3}])
        mock_requests.post.side_effect = [unrelated_fail, plain_ok]
        db.log_lead({"asin": "B0OTHERFAIL", "price": 10.0}, 80, "review", "reason")

    messages = " ".join(str(call.args[0]) for call in mock_print.call_args_list)
    assert "does NOT look like a missing-migration issue" in messages
    assert "run scout/db/migrations/001" not in messages


def test_run_once_redacts_secrets_from_a_real_exception_before_storing_error_summary():
    """Code Review 2026-07-02, Finding B5: a Keepa/SP-API exception can legitimately embed a
    real API key in its message (they ride in request URLs). pipeline.run_once() must redact
    that before it reaches runs.error_summary (and, downstream, the digest/system_health)."""
    fake_secret = "sk-fake-secret-abc123456"
    with patch.object(pipeline.db, "start_run", return_value=100), \
            patch.object(pipeline.db, "finish_run") as finish, \
            patch.object(pipeline.config, "have_keepa", return_value=True), \
            patch.object(pipeline.keepa_client, "get_client",
                        side_effect=RuntimeError(f"HTTP 401 for url ...?key={fake_secret}")), \
            patch.dict(os.environ, {"FAKE_KEEPA_API_KEY": fake_secret}):
        try:
            pipeline.run_once(dry_run=False, retrain=False)
        except RuntimeError:
            pass
    error_summary = finish.call_args[1].get("error_summary") or ""
    assert fake_secret not in error_summary
    assert "***REDACTED***" in error_summary


def test_log_lead_pre_migration_strips_unknown_columns_on_double_failure():
    """Code Review 2026-07-02, Finding B2: pre-migration, BOTH the upsert (unknown on_conflict
    target) AND a naive plain insert (features_snapshot/explanation aren't real columns yet)
    fail with PGRST204 "column not found." Without the fix, log_lead would return None and the
    row would be lost entirely. With it, a third attempt (stripped payload) succeeds."""
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        upsert_fail = _mock_response({"code": "42P10"}, status=400)
        plain_insert_fail = _mock_response(
            {"code": "PGRST204", "message": "Could not find the 'features_snapshot' column"}, status=400)
        stripped_insert_ok = _mock_response([{"id": 9}])
        mock_requests.post.side_effect = [upsert_fail, plain_insert_fail, stripped_insert_ok]

        lead_id = db.log_lead({"asin": "B0PREMIG01", "price": 10.0}, 80, "review", "reason")

    assert lead_id == 9
    assert mock_requests.post.call_count == 3
    final_payload = mock_requests.post.call_args_list[2][1]["json"]
    assert "features_snapshot" not in final_payload
    assert "explanation" not in final_payload
    assert final_payload["asin"] == "B0PREMIG01"  # the real row data is still there


def test_queue_brand_search_normalizes_to_lowercase():
    """Code Review 2026-07-02, Finding B3: search_log.brand's unique index is now a PLAIN
    column index (not lower(brand) — PostgREST's on_conflict= can't bind to an expression
    index), so case-insensitive dedup must happen by normalizing at write time instead."""
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_response([{"id": 1}])
        db.queue_brand_search("  Jellycat  ")
    sent = mock_requests.post.call_args[1]["json"]
    assert sent["brand"] == "jellycat"


def test_feature_snapshot_excludes_post_decision_fields():
    """Leakage-prevention guard: verdict/score/reason must NEVER appear in the stored
    features_snapshot, only pre-decision inputs."""
    p = {
        "asin": "B0LEAK", "price": 20.0, "weight_lb": 1.0, "sales_rank": 5000,
        "est_sales": 100, "offers": 6, "brand": "Test", "category": "toys",
        "avg_price_90": 19.0, "avg_offers_90": 5, "oos_90": 0,
        "buybox_seller": "A1SELLER", "amazon_bb_share": 0.0,
        # post-decision / the scout's own judgment — must be excluded
        "rule_score": 91.0, "blended_score": 91.0, "model_proba": 0.8,
        "verdict": "review", "reason": "looks good", "hard_reject": None,
    }
    snap = db.feature_snapshot(p)
    forbidden = {"rule_score", "blended_score", "model_proba", "verdict", "reason", "hard_reject"}
    assert not (forbidden & snap.keys()), f"leaked post-decision fields: {forbidden & snap.keys()}"
    assert snap["asin"] == "B0LEAK" and snap["price"] == 20.0


# ---------------------------------------------------------------------------
# runs table — telemetry survives success AND failure
# ---------------------------------------------------------------------------

def test_start_run_noop_without_supabase():
    with patch.object(db, "SUPA", ""), patch.object(db, "KEY", ""):
        assert db.start_run() is None


def test_finish_run_noop_when_run_id_none():
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        db.finish_run(None, "success")
        mock_requests.patch.assert_not_called()


def test_finish_run_patches_with_status_and_counts():
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.patch.return_value = _mock_response(None)
        db.finish_run(42, "success", asins_scanned=10, leads_upserted=3)
        assert mock_requests.patch.called
        url = mock_requests.patch.call_args[0][0]
        body = mock_requests.patch.call_args[1]["json"]
        assert "runs?id=eq.42" in url
        assert body["status"] == "success"
        assert body["asins_scanned"] == 10
        assert body["leads_upserted"] == 3


def test_record_ranker_run_noop_without_supabase():
    with patch.object(db, "SUPA", ""), patch.object(db, "KEY", ""):
        assert db.record_ranker_run(champion_auc=0.7) is False


def test_record_ranker_run_posts_the_given_fields():
    """Migration 013 (2026-07-09) — the durable, queryable record of champion/challenger AUC
    over time that ranker-report.md (cloud runs never commit their copy back) and the Discord
    post (not queryable) never were."""
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_response(None)
        ok = db.record_ranker_run(host="github-actions-hourly", refused=False, row_count=550,
                                  champion_auc=0.72, verdict="CHALLENGER LOSES")
        assert ok is True
        assert mock_requests.post.called
        url = mock_requests.post.call_args[0][0]
        body = mock_requests.post.call_args[1]["json"]
        assert "ranker_runs" in url
        assert body["champion_auc"] == 0.72
        assert body["row_count"] == 550
        assert body["verdict"] == "CHALLENGER LOSES"


def test_record_ranker_run_failure_is_non_fatal():
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_response(None, status=500)
        assert db.record_ranker_run(champion_auc=0.5) is False


def test_pipeline_records_a_failed_run_on_exception():
    """The whole point of G1: a run that raises must still leave a `runs` row behind,
    with status='failed' and the error message — never silently lost."""
    with patch.object(pipeline.db, "start_run", return_value=99) as start, \
            patch.object(pipeline.db, "finish_run") as finish, \
            patch.object(pipeline.config, "have_keepa", return_value=False):
        try:
            pipeline.run_once(dry_run=False, retrain=False)
        except RuntimeError as e:
            assert "KEEPA_KEY" in str(e)
        else:
            raise AssertionError("expected RuntimeError for missing KEEPA_KEY")

    start.assert_called_once()
    finish.assert_called_once()
    args, kwargs = finish.call_args
    assert args[0] == 99
    assert args[1] == "failed"
    assert "KEEPA_KEY" in (kwargs.get("error_summary") or "")


def test_pipeline_dry_run_never_starts_a_run_row():
    """Dry runs make zero external writes — including to the runs table."""
    with patch.object(pipeline.db, "start_run") as start, \
            patch.object(pipeline.config, "have_keepa", return_value=False):
        try:
            pipeline.run_once(dry_run=True, retrain=False)
        except RuntimeError:
            pass
    start.assert_not_called()


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
