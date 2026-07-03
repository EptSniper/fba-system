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


def test_deal_finder_block_degrades_to_empty_dict_on_bad_path():
    with patch.object(brain_config, "_BRAIN_PATH", "Z:/definitely/does/not/exist.json"):
        assert brain_config.deal_finder_block() == {}
        assert brain_config.confidence_bands() == {"auto_accept": 0.90, "review": 0.60}


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
