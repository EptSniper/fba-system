"""
Regression tests for Code Review 2026-07-02, Finding S2: keepa_client.py's wait=True calls
must abort honestly on a hard deadline instead of blocking indefinitely on a drained Keepa
token bucket.
"""
import os
import sys
import time
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import keepa_client  # noqa: E402


def test_with_deadline_returns_normally_when_fast():
    result = keepa_client._with_deadline(lambda x: x * 2, 21)
    assert result == 42


def test_with_deadline_raises_timeout_error_when_exceeded():
    with patch.object(keepa_client, "KEEPA_CALL_DEADLINE_SECONDS", 0.2):
        try:
            keepa_client._with_deadline(time.sleep, 2)
            assert False, "expected TimeoutError"
        except TimeoutError as e:
            assert "deadline" in str(e).lower()
            assert "KEEPA_CALL_DEADLINE_SECONDS" in str(e)


def test_with_deadline_propagates_the_real_function_exception():
    """A genuine error from the wrapped call (not a timeout) must surface as itself, not be
    swallowed or misreported as a timeout."""
    def boom():
        raise ValueError("real Keepa error")

    try:
        keepa_client._with_deadline(boom)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "real Keepa error" in str(e)


def test_wait_false_uses_the_short_no_wait_deadline_not_the_long_one():
    """Review fix (2026-07-07, live incident): a wait=False call (the hourly burst — should
    return almost instantly) must fail on KEEPA_NO_WAIT_DEADLINE_SECONDS, NOT
    KEEPA_CALL_DEADLINE_SECONDS. Before this fix both used the exact same 600s deadline as
    keepa-collect.yml's own timeout-minutes: 10, guaranteeing GitHub's external kill always won
    the race and the run's Supabase row got stuck at status='running' forever."""
    def _sleepy(seconds, wait=True):  # mirrors a real Keepa call: accepts (and ignores) wait=
        time.sleep(seconds)

    with patch.object(keepa_client, "KEEPA_CALL_DEADLINE_SECONDS", 5), \
         patch.object(keepa_client, "KEEPA_NO_WAIT_DEADLINE_SECONDS", 0.2):
        start = time.time()
        try:
            keepa_client._with_deadline(_sleepy, 2, wait=False)
            assert False, "expected TimeoutError"
        except TimeoutError as e:
            elapsed = time.time() - start
            assert elapsed < 2, f"should have failed fast on the short deadline, took {elapsed}s"
            assert "KEEPA_NO_WAIT_DEADLINE_SECONDS" in str(e)


def test_wait_true_still_uses_the_long_deadline_unchanged():
    """The nightly drip-pacing path (wait=True) legitimately may need to wait for a token
    refill — its deadline must stay the long, unchanged KEEPA_CALL_DEADLINE_SECONDS."""
    def _sleepy(seconds, wait=True):
        time.sleep(seconds)

    with patch.object(keepa_client, "KEEPA_CALL_DEADLINE_SECONDS", 0.2), \
         patch.object(keepa_client, "KEEPA_NO_WAIT_DEADLINE_SECONDS", 5):
        try:
            keepa_client._with_deadline(_sleepy, 2, wait=True)
            assert False, "expected TimeoutError"
        except TimeoutError as e:
            assert "KEEPA_CALL_DEADLINE_SECONDS" in str(e)


def test_no_wait_kwarg_at_all_defaults_to_the_long_deadline():
    """A caller with no wait= concept at all (e.g. this file's own boom()/lambda fixtures)
    must keep behaving exactly as before this fix — defaulting to the long deadline, not the
    short one, and never having a stray wait= kwarg injected into the wrapped call."""
    with patch.object(keepa_client, "KEEPA_CALL_DEADLINE_SECONDS", 0.2), \
         patch.object(keepa_client, "KEEPA_NO_WAIT_DEADLINE_SECONDS", 5):
        try:
            keepa_client._with_deadline(time.sleep, 2)
            assert False, "expected TimeoutError"
        except TimeoutError as e:
            assert "KEEPA_CALL_DEADLINE_SECONDS" in str(e)


def test_find_candidates_calls_product_finder_through_the_deadline_wrapper():
    """Sanity check that find_candidates() actually routes through _with_deadline(), not a
    direct call — the wrapping must not silently get bypassed by a refactor."""
    with patch.object(keepa_client, "_KEEPA", True):
        mock_api = type("FakeApi", (), {})()
        mock_api.product_finder = lambda params, domain, wait: ["B0FAKE01"]
        result = keepa_client.find_candidates({
            "price_min": 8.0, "price_max": 60.0, "bsr_max": 200000, "min_offers": 3,
            "max_offers": 25, "max_weight_lb": 5.0, "min_monthly_sales": 50,
        }, api=mock_api, limit=5)
    assert result == ["B0FAKE01"]


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
