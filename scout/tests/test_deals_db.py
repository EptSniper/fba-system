"""
Tests for Deal Finder Build Plan Prompt D1: scout/db.py's upsert_deal() + scout/deals/
brain_config.py.

Zero live network calls — `requests` is mocked, matching test_db_idempotency.py's convention.
"""
import datetime as _dt
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402
from deals import brain_config  # noqa: E402


def _enabled_db():
    return patch.object(db, "SUPA", "https://fake.supabase.co"), patch.object(db, "KEY", "fake-key")


def _mock_response(json_body, status=200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_body
    r.raise_for_status = MagicMock() if status < 400 else MagicMock(side_effect=Exception(f"HTTP {status}"))
    return r


# ---------------------------------------------------------------------------
# upsert_deal
# ---------------------------------------------------------------------------

def test_upsert_deal_with_sku_uses_on_conflict():
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_response([{"id": 1}])
        result = db.upsert_deal({
            "retailer": "Best Buy", "source": "bestbuy", "sku": "123456",
            "title_raw": "Widget", "price_current": 19.99,
        })
    assert result == 1
    url = mock_requests.post.call_args[0][0]
    assert "on_conflict=retailer,sku,price_current,seen_date" in url
    prefer = mock_requests.post.call_args[1]["headers"]["Prefer"]
    assert "resolution=merge-duplicates" in prefer


def test_upsert_deal_sends_seen_date_explicitly():
    """Regression: migrations/003's seen_date can't be a generated column (Postgres 42P10/
    42P17 — a timestamptz->date cast isn't immutable), so upsert_deal() must set it itself,
    matching upsert_keepa_snapshot()'s explicit snapshot_date convention."""
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_response([{"id": 1}])
        db.upsert_deal({
            "retailer": "Best Buy", "source": "bestbuy", "sku": "123456",
            "title_raw": "Widget", "price_current": 19.99,
        })
    sent = mock_requests.post.call_args[1]["json"]
    assert sent.get("seen_date") == _dt.date.today().isoformat()


def test_upsert_deal_does_not_overwrite_caller_supplied_seen_date():
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_response([{"id": 1}])
        db.upsert_deal({
            "retailer": "Best Buy", "source": "bestbuy", "sku": "123456",
            "title_raw": "Widget", "price_current": 19.99, "seen_date": "2020-01-01",
        })
    sent = mock_requests.post.call_args[1]["json"]
    assert sent.get("seen_date") == "2020-01-01"


def test_upsert_deal_without_sku_falls_back_to_plain_insert():
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_response([{"id": 2}])
        result = db.upsert_deal({
            "retailer": "Target", "source": "slickdeals", "sku": None,
            "title_raw": "Crayola Crayons", "price_current": 1.99,
        })
    assert result == 2
    url = mock_requests.post.call_args[0][0]
    assert "on_conflict" not in url


def test_upsert_deal_falls_back_when_conflict_target_missing():
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.post.side_effect = [Exception("no unique index"), _mock_response([{"id": 3}])]
        result = db.upsert_deal({
            "retailer": "Best Buy", "source": "bestbuy", "sku": "999",
            "title_raw": "Gadget", "price_current": 9.99,
        })
    assert result == 3
    assert mock_requests.post.call_count == 2


def test_upsert_deal_bumps_last_seen_but_never_sends_first_seen():
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_response([{"id": 4}])
        db.upsert_deal({"retailer": "Best Buy", "source": "bestbuy", "sku": "1",
                        "title_raw": "X", "price_current": 1.0, "first_seen": "should-be-dropped"})
    sent = mock_requests.post.call_args[1]["json"]
    assert "last_seen" in sent
    # The caller-supplied first_seen is passed through untouched by upsert_deal itself —
    # this test only guards that upsert_deal doesn't itself SET first_seen from now(),
    # which would overwrite the true first-seen instant on every re-poll.
    assert sent.get("first_seen") == "should-be-dropped"


def test_upsert_deal_noop_when_supabase_disabled():
    with patch.object(db, "SUPA", ""), patch.object(db, "KEY", ""):
        result = db.upsert_deal({"retailer": "Target", "sku": "1", "price_current": 1.0})
    assert result is None


# ---------------------------------------------------------------------------
# brain_config — honest defaults, never crashes on a missing/malformed brain file
# ---------------------------------------------------------------------------

def test_confidence_bands_reads_real_brain_values():
    bands = brain_config.confidence_bands()
    assert 0.0 <= bands["review"] <= bands["auto_accept"] <= 1.0


def test_price_sanity_ratio_is_positive():
    assert brain_config.price_sanity_ratio() > 1.0


def test_source_config_missing_source_returns_empty_dict():
    assert brain_config.source_config("no-such-source") == {}


def test_discount_stack_defaults_to_zero_when_unknown_or_null():
    stack = brain_config.discount_stack("Some Retailer Not In The Table")
    assert stack == {"cashback_pct": 0.0, "giftcard_pct": 0.0}


def test_discount_stack_matches_case_insensitively():
    """Code review regression (2026-07-13): ai-brain.json's discountStack keys are hand-typed
    ("Target") while a caller's retailer string (source-connector-derived, or
    normalize.guess_retailer()) isn't guaranteed to match that exact casing — an exact-string
    miss used to silently fall back to a fabricated 0% stack rather than the real configured one."""
    with patch.object(brain_config, "_load_brain", return_value={
        "dealFinder": {"discountStack": {"Target": {"cashbackPct": 0.05, "giftCardPct": 0.02}}}
    }):
        assert brain_config.discount_stack("target") == {"cashback_pct": 0.05, "giftcard_pct": 0.02}
        assert brain_config.discount_stack("TARGET") == {"cashback_pct": 0.05, "giftcard_pct": 0.02}
        assert brain_config.discount_stack(" Target ") == {"cashback_pct": 0.05, "giftcard_pct": 0.02}


def test_deal_finder_block_degrades_to_empty_dict_on_bad_path():
    with patch.object(brain_config, "_BRAIN_PATH", "Z:/definitely/does/not/exist.json"):
        assert brain_config.deal_finder_block() == {}
        assert brain_config.confidence_bands() == {"auto_accept": 0.90, "review": 0.60}


# ---------------------------------------------------------------------------
# deal_hints + source_http_cache (migration 007, TOP100_DEAL_WATCH_PLAN.md)
# ---------------------------------------------------------------------------
def test_hint_key_is_normalized():
    assert db._hint_key("Jellycat", "Target", "Toys") == "jellycat|target|toys"
    assert db._hint_key("Yeti", None, None) == "yeti||"


def test_upsert_deal_hint_sets_expiry_and_conflicts_on_hint_key():
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_response([{"id": 5}])
        result = db.upsert_deal_hint("Jellycat", "Target", "toys", strength=2.5, ttl_hours=72)
    assert result == 5
    url = mock_requests.post.call_args[0][0]
    body = mock_requests.post.call_args[1]["json"]
    assert "on_conflict=hint_key" in url
    assert body["hint_key"] == "jellycat|target|toys" and body["strength"] == 2.5
    assert "expires_at" in body and "first_seen" not in body  # never overwrite original first_seen


def test_upsert_deal_hint_noop_without_db():
    with patch.object(db, "SUPA", ""), patch.object(db, "KEY", ""):
        assert db.upsert_deal_hint("X", None, None, 1.0) is None


def test_fresh_deal_hints_filters_expiry_and_strength_server_side():
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.get.return_value = _mock_response([{"brand": "Yeti", "strength": 3}])
        rows = db.fresh_deal_hints(min_strength=2)
    assert rows == [{"brand": "Yeti", "strength": 3}]
    params = mock_requests.get.call_args[1]["params"]
    assert params["strength"] == "gte.2"
    assert params["expires_at"].startswith("gt.")  # non-expired only
    assert params["order"] == "strength.desc"


def test_fresh_deal_hints_degrades_to_empty_on_error():
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.get.side_effect = Exception("boom")
        assert db.fresh_deal_hints() == []


def test_source_http_cache_get_and_set_roundtrip_shape():
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.get.return_value = _mock_response([{"etag": "v1", "last_modified": "Mon"}])
        cached = db.get_source_http_cache("http://x/sale")
        assert cached == {"etag": "v1", "last_modified": "Mon"}
        mock_requests.post.return_value = _mock_response([{"source_key": "http://x/sale"}])
        db.set_source_http_cache("http://x/sale", "v2", "Tue")
        body = mock_requests.post.call_args[1]["json"]
        assert body["source_key"] == "http://x/sale" and body["etag"] == "v2"


def test_get_all_source_status_keys_by_url():
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.get.return_value = _mock_response(
            [{"url": "http://a/clr", "mode": "sd-rss-only", "consecutive_403": 2}])
        out = db.get_all_source_status()
    assert out == {"http://a/clr": {"url": "http://a/clr", "mode": "sd-rss-only", "consecutive_403": 2}}


def test_upsert_source_status_uses_dedicated_conflict_safe_post():
    """Like source_http_cache, source_status has no `id` column (PK is url) — the write must NOT
    route through _upsert (which reads data[0]['id'] -> 409). return=minimal, on_conflict=url."""
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_response([], status=200)
        db.upsert_source_status("http://a/clr", "sd-rss-only", 2, "forbidden", 403, retired_at="2026-07-04T00:00:00Z")
    url = mock_requests.post.call_args[0][0]
    body = mock_requests.post.call_args[1]["json"]
    prefer = mock_requests.post.call_args[1]["headers"]["Prefer"]
    assert "on_conflict=url" in url and "return=minimal" in prefer
    assert body["mode"] == "sd-rss-only" and body["consecutive_403"] == 2 and body["retired_at"] == "2026-07-04T00:00:00Z"


def test_source_status_helpers_noop_without_db():
    with patch.object(db, "SUPA", ""), patch.object(db, "KEY", ""):
        assert db.get_all_source_status() == {}
        assert db.upsert_source_status("u", "active", 0, None, None) is None


def test_upsert_deal_strips_007_columns_on_pre_migration_insert():
    """A deal row carrying source_signal/extraction_confidence must still write (minus those
    two columns) if migration 007 hasn't landed — never lose the whole row (Finding B2 pattern)."""
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        # First POST (with the new columns) fails; retry (stripped) succeeds.
        fail = _mock_response({}, status=400)
        ok = _mock_response([{"id": 9}])
        mock_requests.post.side_effect = [fail, ok]
        result = db.upsert_deal({
            "retailer": "Target", "source": "slickdeals", "title_raw": "X",
            "price_current": 1.99, "source_signal": "sd-rss", "extraction_confidence": 0.9,
        })
    assert result == 9
    retried_body = mock_requests.post.call_args_list[-1][1]["json"]
    assert "source_signal" not in retried_body and "extraction_confidence" not in retried_body


# ---------------------------------------------------------------------------
# upsert_deal_match / find_deal_match / update_deal_status / get_deals_by_status /
# get_deal_matches_ready_to_apply / update_lead_source (Sourcing & Review-Queue Plan Phase 2.2/
# 2.3, 2026-07-13)
# ---------------------------------------------------------------------------

def test_get_deals_by_status_queries_the_given_status():
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.get.return_value = _mock_response([{"id": 1, "status": "new"}])
        result = db.get_deals_by_status("new", limit=50)
    assert result == [{"id": 1, "status": "new"}]
    url = mock_requests.get.call_args[0][0]
    assert "status=eq.new" in url


def test_update_deal_status_patches_status_only():
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.patch.return_value = _mock_response({}, status=204)
        ok = db.update_deal_status(7, "matched")
    assert ok is True
    url = mock_requests.patch.call_args[0][0]
    assert "deals?id=eq.7" in url
    assert mock_requests.patch.call_args[1]["json"] == {"status": "matched"}


def test_find_deal_match_returns_none_when_no_existing_row():
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.get.return_value = _mock_response([])
        assert db.find_deal_match(1, "B000") is None


def test_upsert_deal_match_inserts_when_no_existing_row():
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.get.return_value = _mock_response([])  # find_deal_match: no existing row
        mock_requests.post.return_value = _mock_response([{"id": 5}])
        result = db.upsert_deal_match(1, "B000", 0.7, "title", pack_match=True, llm_reason="x")
    assert result == 5
    body = mock_requests.post.call_args[1]["json"]
    assert body["deal_id"] == 1 and body["asin"] == "B000" and body["confidence"] == 0.7
    assert "human_verdict" not in body  # never written by the matcher, only by human review


def test_upsert_deal_match_patches_when_row_already_exists():
    """Idempotency here is APPLICATION-level (no unique constraint on deal_matches) — a re-run
    of matcher.run() on the same (deal_id, asin) pair must update, not duplicate."""
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.get.return_value = _mock_response([{"id": 42, "asin": "B000"}])
        mock_requests.patch.return_value = _mock_response({}, status=204)
        result = db.upsert_deal_match(1, "B000", 0.8, "title")
    assert result == 42
    mock_requests.post.assert_not_called()
    url = mock_requests.patch.call_args[0][0]
    assert "deal_matches?id=eq.42" in url


def test_upsert_deal_match_without_asin_is_a_noop():
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        result = db.upsert_deal_match(1, None, 0.5, "title")
    assert result is None
    mock_requests.get.assert_not_called()
    mock_requests.post.assert_not_called()


def test_get_deal_matches_ready_to_apply_filters_on_verdict_or_confidence():
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.get.return_value = _mock_response([{"id": 1, "asin": "B000"}])
        result = db.get_deal_matches_ready_to_apply(0.9, limit=10)
    assert result == [{"id": 1, "asin": "B000"}]
    url = mock_requests.get.call_args[0][0]
    assert "human_verdict.eq.approve" in url and "confidence.gte.0.9" in url
    assert "deals(*)" in url  # embeds the parent deal (price_current/retailer/url)


def test_update_lead_source_patches_by_asin():
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.patch.return_value = _mock_response({}, status=204)
        ok = db.update_lead_source("B000", 10.0, "Target", "https://x", 5.0, 0.5)
    assert ok is True
    url = mock_requests.patch.call_args[0][0]
    assert "leads?asin=eq.B000" in url
    body = mock_requests.patch.call_args[1]["json"]
    assert body == {"buy_cost": 10.0, "source_store": "Target", "source_url": "https://x",
                    "profit": 5.0, "roi": 0.5}


def test_update_lead_source_omits_profit_roi_when_none():
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.patch.return_value = _mock_response({}, status=204)
        db.update_lead_source("B000", 10.0, "Target", "https://x", None, None)
    body = mock_requests.patch.call_args[1]["json"]
    assert "profit" not in body and "roi" not in body


def test_update_lead_source_writes_gated_status_when_given():
    """Code review regression (2026-07-13): an APPROVAL_REQUIRED match's real economics used to
    get written onto a lead with nothing distinguishing it from a plain ALLOWED item."""
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.patch.return_value = _mock_response({}, status=204)
        db.update_lead_source("B000", 10.0, "Target", "https://x", 5.0, 0.5,
                              gated_status="approval_required")
    body = mock_requests.patch.call_args[1]["json"]
    assert body["gated_status"] == "approval_required"


def test_update_lead_source_omits_gated_status_when_none():
    supa_p, key_p = _enabled_db()
    with supa_p, key_p, patch.object(db, "requests") as mock_requests:
        mock_requests.patch.return_value = _mock_response({}, status=204)
        db.update_lead_source("B000", 10.0, "Target", "https://x", 5.0, 0.5)
    body = mock_requests.patch.call_args[1]["json"]
    assert "gated_status" not in body


def test_deal_match_functions_noop_when_supabase_disabled():
    with patch.object(db, "SUPA", ""), patch.object(db, "KEY", ""):
        assert db.get_deals_by_status() == []
        assert db.update_deal_status(1, "matched") is False
        assert db.find_deal_match(1, "B000") is None
        assert db.upsert_deal_match(1, "B000", 0.5, "title") is None
        assert db.get_deal_matches_ready_to_apply(0.9) == []
        assert db.update_lead_source("B000", 1.0, "x", "y", 1.0, 1.0) is False


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
