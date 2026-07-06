"""
test_collect_hourly.py — the hourly burst collector (DATA_ENGINE_PLAN.md hourly-collector era,
Session 54).

Covers: honest disabled/no-tokens-banked states, the strict priority budget waterfall (tier 1
shadow rechecks -> tier 2 hint-led scan -> tier 3 backtest, each getting whatever the one above
didn't spend), hint_led_scan's own gates/scoring/lead-upsert wiring, non-blocking (wait=False)
calls to keepa_client, and idempotency — a double-fire (the same survivor scored/logged twice)
must be harmless, matching the project's upsert-everywhere convention.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import collect_hourly as ch  # noqa: E402
import db  # noqa: E402
import keepa_client  # noqa: E402


class FakeApi:
    def __init__(self, tokens_left=60):
        self.tokens_left = tokens_left
        self.tokens_consumed = 0

    def update_status(self):
        pass  # real keepa.Keepa refreshes tokens_left here (a free, no-token-cost probe)


class DisabledStatesTest(unittest.TestCase):
    def test_no_keepa_key(self):
        with mock.patch.object(ch.config, "have_keepa", return_value=False):
            r = ch.run_hourly_collect()
        self.assertEqual(r["status"], "disabled")

    def test_no_tokens_banked(self):
        api = FakeApi(tokens_left=0)
        with mock.patch.object(ch.config, "have_keepa", return_value=True), \
             mock.patch.object(db, "start_run", return_value=1), \
             mock.patch.object(db, "finish_run"), \
             mock.patch.object(ch.datalake, "set_run_context"), \
             mock.patch.object(ch.datalake, "reset_stats"), \
             mock.patch.object(ch.datalake, "flush", return_value={}), \
             mock.patch.object(ch.datalake, "digest_line", return_value=""):
            r = ch.run_hourly_collect(api=api)
        self.assertEqual(r["status"], "ok")
        self.assertIn("no tokens currently banked", r["reason"])

    def test_negative_token_debt_reads_as_zero_not_a_crash(self):
        """LIVE-CONFIRMED 2026-07-06: the account can be in token DEBT (a negative tokens_left)
        after heavy usage — must degrade to 'nothing to spend', never crash or go negative in
        the budget math."""
        api = FakeApi(tokens_left=-68)
        self.assertEqual(ch._observed_tokens_left(api), 0)


class ObservedTokensProbeTest(unittest.TestCase):
    def test_calls_update_status_before_reading(self):
        """LIVE-CONFIRMED 2026-07-06: api.tokens_left reads a STALE 0 immediately after
        connecting — only api.update_status() (a free, no-token-cost probe) refreshes it to the
        TRUE current balance. Missing this call would make the collector wrongly skip real
        banked tokens."""
        api = FakeApi(tokens_left=0)
        def _refresh():
            api.tokens_left = 42
        api.update_status = _refresh
        self.assertEqual(ch._observed_tokens_left(api), 42)

    def test_update_status_failure_degrades_to_existing_value(self):
        api = FakeApi(tokens_left=15)
        api.update_status = mock.Mock(side_effect=RuntimeError("network hiccup"))
        self.assertEqual(ch._observed_tokens_left(api), 15)


class BudgetWaterfallTest(unittest.TestCase):
    """The core contract: each tier gets exactly (available - sum of prior tiers' real spend),
    never a pre-allocated fixed share (that fixed-share model is what Session 54 retired)."""

    def _run(self, api, shadow_spent, scan_spent, expect_bt_cap):
        with mock.patch.object(ch.config, "have_keepa", return_value=True), \
             mock.patch.object(db, "start_run", return_value=1), \
             mock.patch.object(db, "finish_run"), \
             mock.patch.object(ch.datalake, "set_run_context"), \
             mock.patch.object(ch.datalake, "reset_stats"), \
             mock.patch.object(ch.datalake, "flush", return_value={}), \
             mock.patch.object(ch.datalake, "digest_line", return_value=""), \
             mock.patch.object(ch.shadow_outcomes, "run_rechecks",
                               return_value={"status": "ok", "tokens_spent": shadow_spent}) as mrecheck, \
             mock.patch.object(ch, "hint_led_scan",
                               return_value={"status": "ok", "tokens_spent": scan_spent,
                                            "candidates": 0, "leads_logged": 0, "survivors": 0}) as mscan, \
             mock.patch.object(ch.backtest, "run_backtest") as mbacktest:
            mbacktest.return_value = {"status": "ok", "tokens_spent": 0}
            r = ch.run_hourly_collect(api=api)
        # tier 1 got the FULL available budget as its cap
        self.assertEqual(mrecheck.call_args.kwargs["token_cap"], api.tokens_left)
        # tier 2 (hint_led_scan) got (available - shadow_spent)
        self.assertEqual(mscan.call_args[0][1], api.tokens_left - shadow_spent)
        if expect_bt_cap is None:
            mbacktest.assert_not_called()
        else:
            self.assertEqual(mbacktest.call_args.kwargs["token_cap"], expect_bt_cap)
        return r

    def test_full_waterfall_with_remainder_for_backtest(self):
        r = self._run(FakeApi(tokens_left=60), shadow_spent=10, scan_spent=20, expect_bt_cap=30)
        self.assertEqual(r["tokens_spent_total"], 10 + 20 + 0)

    def test_shadow_consumes_everything_backtest_skipped(self):
        self._run(FakeApi(tokens_left=60), shadow_spent=60, scan_spent=0, expect_bt_cap=None)

    def test_scan_consumes_remainder_backtest_skipped(self):
        self._run(FakeApi(tokens_left=60), shadow_spent=10, scan_spent=50, expect_bt_cap=None)


class HintLedScanTest(unittest.TestCase):
    def setUp(self):
        self._keepa_patch = mock.patch.object(keepa_client, "_KEEPA", True)
        self._keepa_patch.start()

    def tearDown(self):
        self._keepa_patch.stop()

    def test_no_budget_is_skipped(self):
        r = ch.hint_led_scan(FakeApi(), 0)
        self.assertEqual(r["status"], "skipped")

    def test_no_fresh_hints_is_honest_noop(self):
        with mock.patch.object(ch.discovery_hints, "hinted_brand_seeds", return_value=[]):
            r = ch.hint_led_scan(FakeApi(), 100)
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["candidates"], 0)

    def test_calls_keepa_client_with_wait_false(self):
        """The whole point of the burst collector: never block waiting on a token refill."""
        api = FakeApi()
        with mock.patch.object(ch.discovery_hints, "hinted_brand_seeds", return_value=["Lego"]), \
             mock.patch.object(keepa_client, "find_candidates", return_value=["A1"]) as mfind, \
             mock.patch.object(keepa_client, "enrich", return_value=[{"asin": "A1", "price": 20}]) as menrich, \
             mock.patch.object(ch.model_mod, "load_model", return_value=None), \
             mock.patch.object(ch.pipeline, "_evaluate",
                               return_value=[{"asin": "A1", "price": 20, "blended_score": 80}]), \
             mock.patch.object(ch.scoring, "oa_hard_reject", return_value=None), \
             mock.patch.object(db, "log_lead", return_value=101), \
             mock.patch.object(db, "upsert_keepa_snapshot"), \
             mock.patch.object(ch.predictions, "record_predictions_for"), \
             mock.patch.object(ch.shadow_outcomes, "enqueue_survivors") as menqueue:
            r = ch.hint_led_scan(api, 100, run_id="r1")
        self.assertEqual(mfind.call_args.kwargs.get("wait"), False)
        self.assertEqual(menrich.call_args.kwargs.get("wait"), False)
        self.assertEqual(r["leads_logged"], 1)
        self.assertEqual(r["survivors"], 1)
        menqueue.assert_called_once()  # gate survivors get shadow-enqueued

    def test_hard_rejected_candidate_not_enqueued_as_survivor(self):
        api = FakeApi()
        with mock.patch.object(ch.discovery_hints, "hinted_brand_seeds", return_value=["Nike"]), \
             mock.patch.object(keepa_client, "find_candidates", return_value=["A2"]), \
             mock.patch.object(keepa_client, "enrich", return_value=[{"asin": "A2", "price": 20}]), \
             mock.patch.object(ch.model_mod, "load_model", return_value=None), \
             mock.patch.object(ch.pipeline, "_evaluate",
                               return_value=[{"asin": "A2", "price": 20, "blended_score": 10}]), \
             mock.patch.object(ch.scoring, "oa_hard_reject", return_value="Amazon holds the Buy Box"), \
             mock.patch.object(db, "log_lead", return_value=102), \
             mock.patch.object(db, "upsert_keepa_snapshot"), \
             mock.patch.object(ch.predictions, "record_predictions_for"), \
             mock.patch.object(ch.shadow_outcomes, "enqueue_survivors") as menqueue:
            r = ch.hint_led_scan(api, 100, run_id="r1")
        self.assertEqual(r["survivors"], 0)
        menqueue.assert_not_called()  # nothing survived the hard gate -> nothing to enqueue

    def test_double_fire_is_idempotent(self):
        """An occasional double-fire (two overlapping hourly runs, a retried job) must be
        harmless — db.log_lead's own upsert-on-(asin,found_via) makes calling this path twice
        for the SAME candidate a no-op duplicate write, never two rows."""
        api = FakeApi()
        log_calls = []
        with mock.patch.object(ch.discovery_hints, "hinted_brand_seeds", return_value=["Lego"]), \
             mock.patch.object(keepa_client, "find_candidates", return_value=["A1"]), \
             mock.patch.object(keepa_client, "enrich", return_value=[{"asin": "A1", "price": 20}]), \
             mock.patch.object(ch.model_mod, "load_model", return_value=None), \
             mock.patch.object(ch.pipeline, "_evaluate",
                               return_value=[{"asin": "A1", "price": 20, "blended_score": 80}]), \
             mock.patch.object(ch.scoring, "oa_hard_reject", return_value=None), \
             mock.patch.object(db, "log_lead", side_effect=lambda *a, **k: (log_calls.append((a, k)), 101)[1]), \
             mock.patch.object(db, "upsert_keepa_snapshot"), \
             mock.patch.object(ch.predictions, "record_predictions_for"), \
             mock.patch.object(ch.shadow_outcomes, "enqueue_survivors"):
            ch.hint_led_scan(api, 100, run_id="r1")
            ch.hint_led_scan(api, 100, run_id="r1")
        # both calls used found_via="hourly-collect" -> db.log_lead's real upsert (asin+found_via)
        # collapses them to one row; here we assert the CALL SHAPE is identical both times (the
        # actual dedupe is db.py's own tested upsert behavior, not re-tested here).
        self.assertEqual(len(log_calls), 2)
        self.assertEqual(log_calls[0][1]["found_via"], "hourly-collect")
        self.assertEqual(log_calls[1][1]["found_via"], "hourly-collect")


if __name__ == "__main__":
    unittest.main()
