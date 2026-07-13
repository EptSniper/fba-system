"""
Tests for System Blueprint Prompt G3: scout/spapi.py + its pipeline wiring.

Zero live network calls — no real SP-API credentials exist in this environment (all
SP_API_LWA_CLIENT_ID/SECRET/REFRESH_TOKEN are placeholders in API_KEYS.env as of this writing),
so every test mocks `requests` and/or patches `spapi.configured()`. This validates the LOGIC
(all three restriction outcomes, fee fallback, rate limiting, caching, pipeline wiring) —
NOT a live integration; that remains unverified until Mehmet completes SP-API registration.
"""
import os
import sys
import time
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402
import pipeline  # noqa: E402
import spapi  # noqa: E402


def _configured():
    return (patch.object(spapi, "CLIENT_ID", "fake-id"),
           patch.object(spapi, "CLIENT_SECRET", "fake-secret"),
           patch.object(spapi, "REFRESH_TOKEN", "fake-refresh"))


def _mock_ok(json_body, status=200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_body
    r.raise_for_status = MagicMock()
    return r


# ---------------------------------------------------------------------------
# configured() gate — never claims eligibility it didn't verify
# ---------------------------------------------------------------------------

def test_not_configured_returns_honest_not_configured():
    with patch.object(spapi, "CLIENT_ID", None):
        result = spapi.get_listings_restrictions("B0TEST01")
    assert result["status"] == "NOT_CONFIGURED"
    assert "unverified" in result["message"]


def test_fees_not_configured_returns_available_false():
    with patch.object(spapi, "CLIENT_ID", None):
        result = spapi.get_fees_estimate("B0TEST01", 20.0)
    assert result["available"] is False


# ---------------------------------------------------------------------------
# All three restriction outcomes (the brief's explicit test requirement)
# ---------------------------------------------------------------------------

def test_restriction_allowed_no_restrictions_present():
    id_p, secret_p, refresh_p = _configured()
    with id_p, secret_p, refresh_p, \
            patch.object(db, "get_cached_restriction", return_value=None), \
            patch.object(db, "cache_restriction"), \
            patch.object(spapi, "requests") as mock_requests, \
            patch.object(spapi, "_refresh_access_token", return_value="tok"):
        mock_requests.get.return_value = _mock_ok({"restrictions": []})
        result = spapi.get_listings_restrictions("B0ALLOWED", use_cache=True)
    assert result["status"] == "ALLOWED"
    assert result["reasons"] == []


def test_restriction_approval_required_when_links_present():
    id_p, secret_p, refresh_p = _configured()
    body = {"restrictions": [{"reasons": [{
        "message": "Approval required to sell this brand",
        "links": [{"resource": "https://sellercentral.amazon.com/apply/xyz"}],
    }]}]}
    with id_p, secret_p, refresh_p, \
            patch.object(db, "get_cached_restriction", return_value=None), \
            patch.object(db, "cache_restriction"), \
            patch.object(spapi, "requests") as mock_requests, \
            patch.object(spapi, "_refresh_access_token", return_value="tok"):
        mock_requests.get.return_value = _mock_ok(body)
        result = spapi.get_listings_restrictions("B0APPROVAL", use_cache=True)
    assert result["status"] == "APPROVAL_REQUIRED"
    assert result["links"] == ["https://sellercentral.amazon.com/apply/xyz"]


def test_restriction_not_eligible_when_no_approval_path():
    id_p, secret_p, refresh_p = _configured()
    body = {"restrictions": [{"reasons": [{
        "message": "This ASIN cannot be listed by any seller", "links": [],
    }]}]}
    with id_p, secret_p, refresh_p, \
            patch.object(db, "get_cached_restriction", return_value=None), \
            patch.object(db, "cache_restriction"), \
            patch.object(spapi, "requests") as mock_requests, \
            patch.object(spapi, "_refresh_access_token", return_value="tok"):
        mock_requests.get.return_value = _mock_ok(body)
        result = spapi.get_listings_restrictions("B0NOTELIGIBLE", use_cache=True)
    assert result["status"] == "NOT_ELIGIBLE"
    assert result["links"] == []


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

def test_restriction_uses_cache_when_present():
    id_p, secret_p, refresh_p = _configured()
    cached_row = {"status": "ALLOWED", "reasons": [], "links": []}
    with id_p, secret_p, refresh_p, \
            patch.object(db, "get_cached_restriction", return_value=cached_row), \
            patch.object(spapi, "requests") as mock_requests:
        result = spapi.get_listings_restrictions("B0CACHED", use_cache=True)
    assert result["status"] == "ALLOWED"
    assert result.get("cached") is True
    mock_requests.get.assert_not_called()  # never hit the live API when cached


def test_restriction_skips_cache_when_use_cache_false():
    id_p, secret_p, refresh_p = _configured()
    with id_p, secret_p, refresh_p, \
            patch.object(db, "get_cached_restriction") as get_cache, \
            patch.object(spapi, "requests") as mock_requests, \
            patch.object(spapi, "_refresh_access_token", return_value="tok"):
        mock_requests.get.return_value = _mock_ok({"restrictions": []})
        spapi.get_listings_restrictions("B0NOCACHE", use_cache=False)
    get_cache.assert_not_called()


# ---------------------------------------------------------------------------
# Fee estimate — real value when available, honest fallback flag when not
# ---------------------------------------------------------------------------

def test_fees_estimate_parses_referral_and_fba():
    id_p, secret_p, refresh_p = _configured()
    body = {"payload": {"FeesEstimateResult": {"FeesEstimate": {
        "FeeDetailList": [
            {"FeeType": "ReferralFee", "FeeAmount": {"Amount": 3.0}},
            {"FeeType": "FBAFees", "FeeAmount": {"Amount": 5.5}},
        ],
        "TotalFeesEstimate": {"Amount": 8.5},
    }}}}
    with id_p, secret_p, refresh_p, \
            patch.object(spapi, "requests") as mock_requests, \
            patch.object(spapi, "_refresh_access_token", return_value="tok"):
        mock_requests.post.return_value = _mock_ok(body)
        result = spapi.get_fees_estimate("B0FEES", 20.0)
    assert result["available"] is True
    assert result["referral_fee"] == 3.0
    assert result["fba_fee"] == 5.5
    assert result["total_fees"] == 8.5


# ---------------------------------------------------------------------------
# catalog_search_keywords — free title/keyword -> candidate ASIN(s)
# ---------------------------------------------------------------------------

def test_catalog_search_keywords_not_configured_returns_available_false():
    with patch.object(spapi, "CLIENT_ID", None):
        result = spapi.catalog_search_keywords("acme widget")
    assert result["available"] is False
    assert result["query"] == "acme widget"


def test_catalog_search_keywords_parses_items_into_results():
    id_p, secret_p, refresh_p = _configured()
    body = {"items": [
        {"asin": "B0KW0001", "summaries": [{"itemName": "Acme Widget", "brand": "Acme"}]},
    ]}
    with id_p, secret_p, refresh_p, \
            patch.object(spapi, "requests") as mock_requests, \
            patch.object(spapi, "_refresh_access_token", return_value="tok"):
        mock_requests.get.return_value = _mock_ok(body)
        result = spapi.catalog_search_keywords("acme widget")
    assert result["available"] is True
    assert result["results"] == [{"asin": "B0KW0001", "title": "Acme Widget", "brand": "Acme"}]


def test_catalog_search_keywords_empty_response_degrades_to_available_true_empty_results():
    id_p, secret_p, refresh_p = _configured()
    with id_p, secret_p, refresh_p, \
            patch.object(spapi, "requests") as mock_requests, \
            patch.object(spapi, "_refresh_access_token", return_value="tok"):
        mock_requests.get.return_value = _mock_ok({})  # no "items" key at all
        result = spapi.catalog_search_keywords("acme widget")
    assert result["available"] is True
    assert result["results"] == []


def test_catalog_search_keywords_malformed_items_degrade_to_blank_fields_never_crash():
    id_p, secret_p, refresh_p = _configured()
    body = {"items": [
        {"asin": None, "summaries": [{"itemName": "No ASIN"}]},  # missing asin -> dropped
        {"asin": "B0OK", "summaries": "not-a-list"},              # malformed summaries -> blank fields
        "not-a-dict",                                              # malformed item -> skipped
        {"asin": "B0EMPTYSUM", "summaries": []},                  # empty summaries -> blank fields
    ]}
    with id_p, secret_p, refresh_p, \
            patch.object(spapi, "requests") as mock_requests, \
            patch.object(spapi, "_refresh_access_token", return_value="tok"):
        mock_requests.get.return_value = _mock_ok(body)
        result = spapi.catalog_search_keywords("acme widget")
    assert result["available"] is True
    assert result["results"] == [
        {"asin": "B0OK", "title": None, "brand": None},
        {"asin": "B0EMPTYSUM", "title": None, "brand": None},
    ]


def test_catalog_search_keywords_brand_param_passed_through_when_given():
    id_p, secret_p, refresh_p = _configured()
    with id_p, secret_p, refresh_p, \
            patch.object(spapi, "requests") as mock_requests, \
            patch.object(spapi, "_refresh_access_token", return_value="tok"):
        mock_requests.get.return_value = _mock_ok({"items": []})
        spapi.catalog_search_keywords("widget", brand="Acme")
    params = mock_requests.get.call_args.kwargs["params"]
    assert params["brand"] == "Acme"


def test_catalog_search_keywords_no_brand_param_when_not_given():
    id_p, secret_p, refresh_p = _configured()
    with id_p, secret_p, refresh_p, \
            patch.object(spapi, "requests") as mock_requests, \
            patch.object(spapi, "_refresh_access_token", return_value="tok"):
        mock_requests.get.return_value = _mock_ok({"items": []})
        spapi.catalog_search_keywords("widget")
    params = mock_requests.get.call_args.kwargs["params"]
    assert "brand" not in params


# ---------------------------------------------------------------------------
# Rate limiter — sleeps to stay under the configured rate
# ---------------------------------------------------------------------------

def test_token_bucket_enforces_minimum_interval():
    bucket = spapi._TokenBucket(rate_per_sec=10.0)  # min interval = 0.1s
    start = time.monotonic()
    bucket.wait()
    bucket.wait()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.09  # allow small timing slack


# ---------------------------------------------------------------------------
# Pipeline wiring: no-op when unconfigured, hard-reject / tag / fee-source when configured
# ---------------------------------------------------------------------------

def _candidate(asin="B0PIPE01", price=20.0):
    return {"asin": asin, "price": price, "title": "Test", "blended_score": 80}


def test_pipeline_eligibility_check_is_noop_when_unconfigured():
    with patch.object(spapi, "configured", return_value=False):
        result = pipeline._check_eligibility([_candidate()])
    assert "eligibility" not in result[0]
    assert "hard_reject" not in result[0]


def test_pipeline_marks_not_eligible_as_hard_reject():
    with patch.object(spapi, "configured", return_value=True), \
            patch.object(spapi, "get_listings_restrictions",
                        return_value={"status": "NOT_ELIGIBLE", "reasons": ["brand restricted"], "links": []}), \
            patch.object(spapi, "get_fees_estimate", return_value={"available": False}):
        result = pipeline._check_eligibility([_candidate()])
    assert result[0]["hard_reject"].startswith("account-gated:")
    assert "brand restricted" in result[0]["hard_reject"]


def test_pipeline_marks_approval_required_as_needs_ungating_not_rejected():
    with patch.object(spapi, "configured", return_value=True), \
            patch.object(spapi, "get_listings_restrictions",
                        return_value={"status": "APPROVAL_REQUIRED", "reasons": [], "links": ["url"]}), \
            patch.object(spapi, "get_fees_estimate", return_value={"available": False}):
        result = pipeline._check_eligibility([_candidate()])
    assert result[0].get("needs_ungating") is True
    assert "hard_reject" not in result[0]


def test_pipeline_uses_spapi_fee_when_available_records_source():
    with patch.object(spapi, "configured", return_value=True), \
            patch.object(spapi, "get_listings_restrictions",
                        return_value={"status": "ALLOWED", "reasons": [], "links": []}), \
            patch.object(spapi, "get_fees_estimate",
                        return_value={"available": True, "fba_fee": 6.42, "referral_fee": 3.0}):
        result = pipeline._check_eligibility([_candidate()])
    assert result[0]["fee_source"] == "spapi"
    assert result[0]["spapi_fba_fee"] == 6.42


def test_pipeline_falls_back_to_estimate_when_fees_unavailable():
    with patch.object(spapi, "configured", return_value=True), \
            patch.object(spapi, "get_listings_restrictions",
                        return_value={"status": "ALLOWED", "reasons": [], "links": []}), \
            patch.object(spapi, "get_fees_estimate", return_value={"available": False, "reason": "x"}):
        result = pipeline._check_eligibility([_candidate()])
    assert result[0]["fee_source"] == "estimate"
    assert "spapi_fba_fee" not in result[0]


def test_pipeline_eligibility_check_never_crashes_the_run_on_spapi_error():
    with patch.object(spapi, "configured", return_value=True), \
            patch.object(spapi, "get_listings_restrictions", side_effect=Exception("network blip")):
        result = pipeline._check_eligibility([_candidate()])
    # Candidate passes through unaffected — an SP-API hiccup must never break the scout.
    assert "hard_reject" not in result[0]


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
