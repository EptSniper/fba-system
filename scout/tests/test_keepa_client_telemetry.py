"""
test_keepa_client_telemetry.py — regression tests for the token-spend telemetry fix
(2026-07-07, live incident).

_tokens_consumed()/_delta() used to read tokens_consumed_total/tokens_consumed off the api
object — attributes the `keepa` PyPI package has NEVER actually exposed, in any version. Every
before/after spend measurement across the project silently returned None -> fell back to 0,
which let run_hourly_collect()'s cross-tier budget tracking stay at its stale starting value
even after an earlier tier had already overdrawn the account, letting a later tier run anyway
against an already-negative bank.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import keepa_client  # noqa: E402


class _FakeApi:
    def __init__(self, tokens_left):
        self.tokens_left = tokens_left


class TokensConsumedTest(unittest.TestCase):
    def test_reads_tokens_left_not_a_nonexistent_counter(self):
        api = _FakeApi(tokens_left=42)
        self.assertEqual(keepa_client._tokens_consumed(api), 42)

    def test_never_reads_the_nonexistent_tokens_consumed_total_attribute(self):
        """Even if some OTHER code sets a stray tokens_consumed_total attribute (e.g. a stale
        test fixture), this must still report the real tokens_left balance, not that value —
        proving the fix reads the right attribute rather than merely falling back correctly."""
        api = _FakeApi(tokens_left=42)
        api.tokens_consumed_total = 999
        self.assertEqual(keepa_client._tokens_consumed(api), 42)

    def test_missing_attribute_degrades_to_none(self):
        self.assertIsNone(keepa_client._tokens_consumed(object()))

    def test_negative_balance_is_read_correctly(self):
        """Keepa allows overdraw — a negative balance must be readable, not treated as missing."""
        api = _FakeApi(tokens_left=-14)
        self.assertEqual(keepa_client._tokens_consumed(api), -14)


class DeltaTest(unittest.TestCase):
    def test_spend_is_before_minus_after(self):
        """The account went from 50 to -14 across a real 16-ASIN enrich() call in the live
        incident this fix targets — must report 64 tokens spent, not None/0."""
        self.assertEqual(keepa_client._delta(50, -14), 64)

    def test_cross_tier_budget_actually_decreases_now(self):
        """The exact scenario that let tier 3 run against an already-overdrawn bank: tier 2
        spends real tokens, and the run's own before/after reads must reflect that spend so
        run_hourly_collect()'s budget = max(0, budget - spent) actually zeroes out."""
        before = keepa_client._tokens_consumed(_FakeApi(tokens_left=60))
        after = keepa_client._tokens_consumed(_FakeApi(tokens_left=-34))
        spent = keepa_client._delta(before, after)
        budget = max(0, 60 - int(spent or 0))
        self.assertEqual(spent, 94)
        self.assertEqual(budget, 0)

    def test_a_small_refill_mid_operation_reports_honestly_negative(self):
        self.assertEqual(keepa_client._delta(10, 11), -1)

    def test_either_read_missing_degrades_to_none(self):
        self.assertIsNone(keepa_client._delta(None, 10))
        self.assertIsNone(keepa_client._delta(10, None))
        self.assertIsNone(keepa_client._delta(None, None))


if __name__ == "__main__":
    unittest.main()
