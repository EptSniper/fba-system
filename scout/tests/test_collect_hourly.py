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


class EnrichNoWaitSellerRecordingTest(unittest.TestCase):
    """Keepa throughput plan Action D (2026-07-11): every enrich() call already paid for
    buybox_seller, whatever it was called for (shadow rechecks, hint-led-scan buy-discovery) —
    _enrich_no_wait opportunistically feeds the seller pool at ZERO marginal token cost."""

    def test_records_sellers_from_enrich_result(self):
        import deals_firehose
        enriched = [{"asin": "A1", "buybox_seller": "SELLER1"},
                   {"asin": "A2", "buybox_seller": "SELLER2"},
                   {"asin": "A3", "buybox_seller": None}]
        with mock.patch.object(keepa_client, "enrich", return_value=enriched), \
             mock.patch.object(deals_firehose, "record_seen_sellers") as mrecord:
            out = ch._enrich_no_wait(["A1", "A2", "A3"])
        self.assertEqual(out, enriched)
        mrecord.assert_called_once_with(["SELLER1", "SELLER2"])

    def test_no_sellers_in_result_is_a_noop(self):
        import deals_firehose
        with mock.patch.object(keepa_client, "enrich",
                              return_value=[{"asin": "A1", "buybox_seller": None}]), \
             mock.patch.object(deals_firehose, "record_seen_sellers") as mrecord:
            ch._enrich_no_wait(["A1"])
        mrecord.assert_not_called()

    def test_seller_recording_failure_never_breaks_the_real_caller(self):
        import deals_firehose
        enriched = [{"asin": "A1", "buybox_seller": "SELLER1"}]
        with mock.patch.object(keepa_client, "enrich", return_value=enriched), \
             mock.patch.object(deals_firehose, "record_seen_sellers",
                              side_effect=RuntimeError("storage down")):
            out = ch._enrich_no_wait(["A1"])
        self.assertEqual(out, enriched)  # the real (shadow/hint-scan) caller still gets its data


class BudgetWaterfallTest(unittest.TestCase):
    """The core contract (revised 2026-07-08, live incident): tier 1 (shadow rechecks) is now
    capped to TIER1_RESERVE_FRACTION of the ORIGINAL available bank, not handed the whole thing —
    due_shadow_checkpoints()'s own 400-error bug (fixed the same day) had silently zeroed tier 1's
    real work on every run until now, masking the fact it was never actually bounded; a real
    backlog (up to 500 overdue rows) could otherwise drain an entire run's budget on tier 1 alone,
    the same failure tier 2 used to cause. Tier 2 (hint-led scan) is capped to (post-tier-1 budget
    minus TIER3_RESERVE_FRACTION of the ORIGINAL available bank, not of whatever tier 1 leaves
    behind) — so tier 3's guarantee can't shrink just because tier 1 had a big backlog that run.
    Tier 3 itself still gets 'whatever tier 1 + tier 2 actually measured-spent, no further
    constraint' — only tiers 1 and 2's OWN input budgets are reserve-adjusted."""

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
             mock.patch.object(ch, "_corpus_acceleration_status",
                               return_value={"active": False, "pending_asins": 0}), \
             mock.patch.object(ch, "_tier1_reserve_fraction",
                               return_value=ch.TIER1_RESERVE_FRACTION), \
             mock.patch.object(ch, "hint_led_scan",
                               return_value={"status": "ok", "tokens_spent": scan_spent,
                                            "candidates": 0, "leads_logged": 0, "survivors": 0}) as mscan, \
             mock.patch.object(ch.backtest, "run_backtest") as mbacktest:
            mbacktest.return_value = {"status": "ok", "tokens_spent": 0}
            r = ch.run_hourly_collect(api=api)
        # tier 1 got TIER1_RESERVE_FRACTION of the ORIGINAL available bank as its cap, not the
        # full bank.
        expected_tier1_cap = int(api.tokens_left * ch.TIER1_RESERVE_FRACTION)
        self.assertEqual(mrecheck.call_args.kwargs["token_cap"], expected_tier1_cap)
        # tier 2 (hint_led_scan) got (available - shadow_spent) MINUS the tier-3 reserve, where
        # the reserve is a fraction of the ORIGINAL available bank, not of the post-tier-1 budget.
        post_tier1 = max(0, api.tokens_left - shadow_spent)
        tier3_reserve = int(api.tokens_left * ch.TIER3_RESERVE_FRACTION)
        expected_tier2_budget = max(0, post_tier1 - tier3_reserve)
        self.assertEqual(mscan.call_args[0][1], expected_tier2_budget)
        if expect_bt_cap is None:
            mbacktest.assert_not_called()
        else:
            self.assertEqual(mbacktest.call_args.kwargs["token_cap"], expect_bt_cap)
        return r

    def test_full_waterfall_with_remainder_for_backtest(self):
        # available=60, tier3_reserve=int(60*0.35)=21, post_tier1=50, tier2_budget=max(0,50-21)=29
        # -- but tier 3's OWN cap is still based on scan's REAL measured spend (20), not the
        # tier2_budget it was given: post_tier1(50) - scan_spent(20) = 30.
        r = self._run(FakeApi(tokens_left=60), shadow_spent=10, scan_spent=20, expect_bt_cap=30)
        self.assertEqual(r["tokens_spent_total"], 10 + 20 + 0)

    def test_shadow_consumes_everything_backtest_skipped(self):
        self._run(FakeApi(tokens_left=60), shadow_spent=60, scan_spent=0, expect_bt_cap=None)

    def test_scan_consumes_remainder_backtest_skipped(self):
        self._run(FakeApi(tokens_left=60), shadow_spent=10, scan_spent=50, expect_bt_cap=None)

    def test_reserve_actually_protects_tier3_when_scan_would_have_taken_everything(self):
        """The scenario that motivated this fix: tier 2's REAL measured spend equals its full
        given budget (it would gladly take the whole remainder if allowed to) -- proves the
        reserve is what leaves tier 3 a non-zero cap, not luck."""
        available = 60
        tier3_reserve = int(available * ch.TIER3_RESERVE_FRACTION)  # 21
        post_tier1 = available  # no shadow spend
        tier2_budget = max(0, post_tier1 - tier3_reserve)  # 60-21=39
        r = self._run(FakeApi(tokens_left=available), shadow_spent=0, scan_spent=tier2_budget,
                     expect_bt_cap=post_tier1 - tier2_budget)  # 21 left for tier 3
        self.assertGreater(post_tier1 - tier2_budget, 0)

    def test_tier1_cap_is_bounded_not_the_whole_bank(self):
        """Review fix (2026-07-08, live incident): tier 1 used to be handed the ENTIRE available
        bank as its token_cap -- due_shadow_checkpoints()'s own 400-error bug (fixed the same
        day) had silently zeroed tier 1's real work on every run, masking that it was never
        actually bounded. Once real work resumes, an uncapped tier 1 could drain a whole run's
        budget on a single large backlog (up to 500 overdue rows), reproducing the exact
        "one tier eats everything" failure tier 2 used to cause."""
        api = FakeApi(tokens_left=60)
        with mock.patch.object(ch.config, "have_keepa", return_value=True), \
             mock.patch.object(db, "start_run", return_value=1), \
             mock.patch.object(db, "finish_run"), \
             mock.patch.object(ch.datalake, "set_run_context"), \
             mock.patch.object(ch.datalake, "reset_stats"), \
             mock.patch.object(ch.datalake, "flush", return_value={}), \
             mock.patch.object(ch.datalake, "digest_line", return_value=""), \
             mock.patch.object(ch.shadow_outcomes, "run_rechecks",
                               return_value={"status": "ok", "tokens_spent": 0}) as mrecheck, \
             mock.patch.object(ch, "_corpus_acceleration_status",
                               return_value={"active": False, "pending_asins": 0}), \
             mock.patch.object(ch, "_tier1_reserve_fraction",
                               return_value=ch.TIER1_RESERVE_FRACTION), \
             mock.patch.object(ch, "hint_led_scan",
                               return_value={"status": "ok", "tokens_spent": 0,
                                            "candidates": 0, "leads_logged": 0, "survivors": 0}), \
             mock.patch.object(ch.backtest, "run_backtest", return_value={"status": "ok", "tokens_spent": 0}):
            ch.run_hourly_collect(api=api)
        self.assertLess(mrecheck.call_args.kwargs["token_cap"], api.tokens_left)
        self.assertEqual(mrecheck.call_args.kwargs["token_cap"], int(60 * ch.TIER1_RESERVE_FRACTION))


class Tier1ReserveFractionTest(unittest.TestCase):
    """Keepa throughput plan Action C (2026-07-11, Mehmet-approved): learning.sampling.
    tier1ReserveFraction is a reversible brain override of the 0.25 code default, same
    convention as corpusAcceleration."""

    def test_uses_brain_value_when_present_and_valid(self):
        with mock.patch.object(ch.backtest, "sampling_config",
                               return_value={"tier1ReserveFraction": 0.15}):
            self.assertEqual(ch._tier1_reserve_fraction(), 0.15)

    def test_falls_back_to_constant_when_key_absent(self):
        with mock.patch.object(ch.backtest, "sampling_config", return_value={}):
            self.assertEqual(ch._tier1_reserve_fraction(), ch.TIER1_RESERVE_FRACTION)

    def test_falls_back_to_constant_when_value_out_of_range(self):
        with mock.patch.object(ch.backtest, "sampling_config",
                               return_value={"tier1ReserveFraction": 1.5}):
            self.assertEqual(ch._tier1_reserve_fraction(), ch.TIER1_RESERVE_FRACTION)

    def test_falls_back_to_constant_when_brain_read_fails(self):
        with mock.patch.object(ch.backtest, "sampling_config", side_effect=RuntimeError("boom")):
            self.assertEqual(ch._tier1_reserve_fraction(), ch.TIER1_RESERVE_FRACTION)


class CorpusAccelerationTest(unittest.TestCase):
    """Backlog acceleration is brain-controlled, preserves Tier 1, and spends no Tier 2 tokens."""

    def _run(self, *, pending, acceleration_config, shadow_spent=5, scan_spent=7):
        api = FakeApi(tokens_left=60)
        scan_result = {"status": "ok", "tokens_spent": scan_spent, "candidates": 1,
                       "leads_logged": 1, "survivors": 0}
        with mock.patch.object(ch.config, "have_keepa", return_value=True), \
             mock.patch.object(db, "start_run", return_value=1), \
             mock.patch.object(db, "finish_run"), \
             mock.patch.object(ch.datalake, "set_run_context"), \
             mock.patch.object(ch.datalake, "reset_stats"), \
             mock.patch.object(ch.datalake, "flush", return_value={}), \
             mock.patch.object(ch.datalake, "digest_line", return_value=""), \
             mock.patch.object(ch.shadow_outcomes, "run_rechecks",
                               return_value={"status": "ok", "tokens_spent": shadow_spent}) as mrecheck, \
             mock.patch.object(ch.backtest, "sampling_config",
                               return_value={"corpusAcceleration": acceleration_config}), \
             mock.patch.object(ch.backtest, "pending_backlog_count", return_value=pending), \
             mock.patch.object(ch, "hint_led_scan", return_value=scan_result) as mscan, \
             mock.patch.object(ch.backtest, "run_backtest",
                               return_value={"status": "ok", "tokens_spent": 0}) as mbacktest, \
             mock.patch.object(ch, "_deadline_exceeded", return_value=False):
            result = ch.run_hourly_collect(api=api)
        return result, mrecheck, mscan, mbacktest

    def test_pending_backlog_skips_tier2_after_preserving_tier1(self):
        result, mrecheck, mscan, mbacktest = self._run(
            pending=7, acceleration_config={})  # absent keys resolve to the documented safe defaults

        mrecheck.assert_called_once()
        self.assertEqual(mrecheck.call_args.kwargs["token_cap"], 15)
        mscan.assert_not_called()
        # 60 available - 5 actually spent by Tier 1; Tier 2 spent zero, so all 55 reach Tier 3.
        self.assertEqual(mbacktest.call_args.kwargs["token_cap"], 55)
        self.assertEqual(result["backtest_pending_before"], 7)
        self.assertTrue(result["corpus_acceleration"]["active"])
        self.assertEqual(result["corpus_acceleration"]["tier2_action"], "skip")
        self.assertEqual(result["corpus_acceleration"]["config"], {
            "enabled": True, "skipTier2WhilePending": True, "minPendingAsins": 1,
        })
        self.assertIn("7 pending backtest ASINs", result["scan"]["reason"])

    def test_brain_switch_reversibly_retains_tier2(self):
        result, _, mscan, mbacktest = self._run(
            pending=7,
            acceleration_config={"enabled": False, "skipTier2WhilePending": True,
                                 "minPendingAsins": 1},
        )

        mscan.assert_called_once()
        # Post-Tier-1 budget 55 - original-bank reserve 21 = Tier 2 cap 34.
        self.assertEqual(mscan.call_args[0][1], 34)
        self.assertEqual(mbacktest.call_args.kwargs["token_cap"], 48)
        self.assertFalse(result["corpus_acceleration"]["active"])
        self.assertIn("disabled by brain config", result["corpus_acceleration"]["reason"])

    def test_backlog_below_configured_threshold_retains_tier2(self):
        with mock.patch.object(ch.backtest, "sampling_config", return_value={
                 "corpusAcceleration": {"enabled": True, "skipTier2WhilePending": True,
                                        "minPendingAsins": 3}}), \
             mock.patch.object(ch.backtest, "pending_backlog_count", return_value=2):
            status = ch._corpus_acceleration_status()
        self.assertFalse(status["active"])
        self.assertEqual(status["pending_asins"], 2)
        self.assertIn("2 < 3", status["reason"])

    def test_unknown_backlog_retains_tier2_and_reports_unknown(self):
        with mock.patch.object(ch.backtest, "sampling_config", return_value={}), \
             mock.patch.object(ch.backtest, "pending_backlog_count",
                               side_effect=RuntimeError("state unavailable")):
            status = ch._corpus_acceleration_status()
        self.assertFalse(status["active"])
        self.assertIsNone(status["pending_asins"])
        self.assertEqual(status["tier2_action"], "run")
        self.assertIn("unavailable", status["reason"])


class AttachSignalFeaturesTest(unittest.TestCase):
    """Session 55 — free signal-type features attached onto already-enriched products before
    scoring/logging, so they flow into feature_snapshot like every other pre-decision field."""

    def test_attaches_calendar_and_trend_fields(self):
        products = [{"asin": "A1", "brand": "Lego", "category": "toys", "price": 20.0}]
        with mock.patch("signals.calendar.calendar_features",
                       return_value={"day_of_week": 2, "is_bts_window": False}), \
             mock.patch("signals.trends.trends_features",
                       return_value={"interest_now_vs_90d_avg": 1.5, "slope_4wk": 0.2,
                                    "seasonal_z": 0.1, "spike_flag": False, "stale": False}):
            out = ch._attach_signal_features(products)
        self.assertEqual(out[0]["day_of_week"], 2)
        self.assertEqual(out[0]["brand_trend_ratio"], 1.5)
        self.assertEqual(out[0]["category_trend_ratio"], 1.5)
        self.assertFalse(out[0]["brand_trend_stale"])

    def test_reuses_cached_trend_lookup_for_shared_terms(self):
        """Two products sharing the SAME brand must trigger only ONE trends_features call for
        that brand — a per-run cache, not an N+1 Supabase read per product."""
        products = [{"asin": "A1", "brand": "Lego", "category": "toys"},
                   {"asin": "A2", "brand": "Lego", "category": "kitchen"}]
        with mock.patch("signals.calendar.calendar_features", return_value={}), \
             mock.patch("signals.trends.trends_features", return_value={}) as mtrend:
            ch._attach_signal_features(products)
        brand_calls = [c for c in mtrend.call_args_list if c.args[0] == "Lego"]
        self.assertEqual(len(brand_calls), 1)

    def test_never_raises_when_signals_modules_unavailable(self):
        products = [{"asin": "A1", "brand": "Lego", "category": "toys"}]
        with mock.patch.dict(sys.modules, {"signals.calendar": None, "signals.trends": None,
                                          "signals.ebay": None}):
            out = ch._attach_signal_features(products)
        self.assertEqual(out[0]["asin"], "A1")  # degraded gracefully, original data intact

    def test_ebay_skipped_when_not_enabled(self):
        products = [{"asin": "A1", "upc": "012345678905", "price": 20.0}]
        with mock.patch("signals.calendar.calendar_features", return_value={}), \
             mock.patch("signals.trends.trends_features", return_value={}), \
             mock.patch("signals.ebay.enabled", return_value=False):
            out = ch._attach_signal_features(products)
        self.assertNotIn("ebay_active_listing_count", out[0])

    def test_bulk_prefetches_all_distinct_terms_in_one_call(self):
        """Review fix (2026-07-06): the root-cause fix for the hourly collector hanging past its
        10-minute job timeout — one signals.trends.prefetch_series() call up front for every
        distinct brand/category term in the whole batch, instead of each trends_features() call
        falling through to its own live db.trends_series_for() read."""
        products = [{"asin": "A1", "brand": "Lego", "category": "toys"},
                   {"asin": "A2", "brand": "Yeti", "category": "kitchen"},
                   {"asin": "A3", "brand": "Lego", "category": "toys"}]  # repeats both terms
        with mock.patch("signals.calendar.calendar_features", return_value={}), \
             mock.patch("signals.trends.prefetch_series", return_value={}) as mprefetch, \
             mock.patch("signals.trends.trends_features", return_value={}) as mtrend:
            ch._attach_signal_features(products)
        mprefetch.assert_called_once()
        (called_terms,), _ = mprefetch.call_args
        self.assertEqual(sorted(called_terms), ["Lego", "Yeti", "kitchen", "toys"])
        # still only ONE trends_features call per distinct term (feature computation, not I/O)
        self.assertEqual(mtrend.call_count, 4)

    def test_bulk_prefetch_failure_degrades_to_empty_cache_never_raises(self):
        products = [{"asin": "A1", "brand": "Lego", "category": "toys"}]
        with mock.patch("signals.calendar.calendar_features", return_value={}), \
             mock.patch("signals.trends.prefetch_series", side_effect=RuntimeError("supabase down")), \
             mock.patch("signals.trends.trends_features", return_value={}):
            out = ch._attach_signal_features(products)
        self.assertEqual(out[0]["asin"], "A1")  # degraded gracefully, no crash


class SafetyDeadlineTest(unittest.TestCase):
    """Review fix (2026-07-06): a defense-in-depth wall-clock budget. Root cause of the hourly
    collector hanging past keepa-collect.yml's 10-minute job timeout was the Trends N+1 (fixed
    above) -- this is the safety net in case a different slow path appears later: a run past the
    deadline skips its remaining tiers so the function returns normally and finish_run() still
    records a real status, instead of getting force-killed with the Supabase row stuck at
    status='running' forever."""

    def _run(self, deadline_exceeded):
        api = FakeApi(tokens_left=60)
        with mock.patch.object(ch.config, "have_keepa", return_value=True), \
             mock.patch.object(db, "start_run", return_value=1), \
             mock.patch.object(db, "finish_run") as mfinish, \
             mock.patch.object(ch.datalake, "set_run_context"), \
             mock.patch.object(ch.datalake, "reset_stats"), \
             mock.patch.object(ch.datalake, "flush", return_value={}), \
             mock.patch.object(ch.datalake, "digest_line", return_value=""), \
             mock.patch.object(ch.shadow_outcomes, "run_rechecks",
                               return_value={"status": "ok", "tokens_spent": 0}), \
             mock.patch.object(ch, "_corpus_acceleration_status",
                               return_value={"active": False, "pending_asins": 0}), \
             mock.patch.object(ch, "hint_led_scan") as mscan, \
             mock.patch.object(ch.backtest, "run_backtest") as mbacktest, \
             mock.patch.object(ch, "_deadline_exceeded", return_value=deadline_exceeded):
            r = ch.run_hourly_collect(api=api)
        return r, mscan, mbacktest, mfinish

    def test_tiers_2_and_3_skipped_once_the_deadline_is_reached(self):
        r, mscan, mbacktest, mfinish = self._run(deadline_exceeded=True)
        mscan.assert_not_called()
        mbacktest.assert_not_called()
        self.assertEqual(r["scan"]["reason"], "wall-clock safety deadline reached")
        self.assertEqual(r["backtest"]["reason"], "wall-clock safety deadline reached")
        # the function still returned normally -- finish_run() recorded a real status, the run
        # never gets stuck at status='running' forever
        mfinish.assert_called_once()
        self.assertEqual(mfinish.call_args[0][1], "success")

    def test_tiers_run_normally_when_within_the_deadline(self):
        mscan_return = {"status": "ok", "tokens_spent": 0, "candidates": 0, "leads_logged": 0,
                        "survivors": 0}
        api = FakeApi(tokens_left=60)
        with mock.patch.object(ch.config, "have_keepa", return_value=True), \
             mock.patch.object(db, "start_run", return_value=1), \
             mock.patch.object(db, "finish_run") as mfinish, \
             mock.patch.object(ch.datalake, "set_run_context"), \
             mock.patch.object(ch.datalake, "reset_stats"), \
             mock.patch.object(ch.datalake, "flush", return_value={}), \
             mock.patch.object(ch.datalake, "digest_line", return_value=""), \
             mock.patch.object(ch.shadow_outcomes, "run_rechecks",
                               return_value={"status": "ok", "tokens_spent": 0}), \
             mock.patch.object(ch, "_corpus_acceleration_status",
                               return_value={"active": False, "pending_asins": 0}), \
             mock.patch.object(ch, "hint_led_scan", return_value=mscan_return) as mscan, \
             mock.patch.object(ch.backtest, "run_backtest",
                               return_value={"status": "ok", "tokens_spent": 0}) as mbacktest, \
             mock.patch.object(ch, "_deadline_exceeded", return_value=False):
            ch.run_hourly_collect(api=api)
        mscan.assert_called_once()
        mbacktest.assert_called_once()
        mfinish.assert_called_once()


class FinishRunTierBreakdownTest(unittest.TestCase):
    """Review fix (2026-07-09, migration 013): the per-tier token split and the backtest tier's
    rows/ASINs-sampled counts used to exist ONLY in this run's printed JSON summary, discarded
    the moment the GitHub Actions runner tore down. finish_run() now persists them so the
    control-center's training/collection charts have real history to read."""

    def test_tier_and_backtest_fields_reach_finish_run(self):
        api = FakeApi(tokens_left=60)
        with mock.patch.object(ch.config, "have_keepa", return_value=True), \
             mock.patch.object(db, "start_run", return_value=1), \
             mock.patch.object(db, "finish_run") as mfinish, \
             mock.patch.object(ch.datalake, "set_run_context"), \
             mock.patch.object(ch.datalake, "reset_stats"), \
             mock.patch.object(ch.datalake, "flush", return_value={}), \
             mock.patch.object(ch.datalake, "digest_line", return_value=""), \
             mock.patch.object(ch.shadow_outcomes, "run_rechecks",
                               return_value={"status": "ok", "tokens_spent": 3}), \
             mock.patch.object(ch, "_corpus_acceleration_status",
                               return_value={"active": False, "pending_asins": 0}), \
             mock.patch.object(ch, "hint_led_scan",
                               return_value={"status": "ok", "tokens_spent": 13, "candidates": 1,
                                            "leads_logged": 1, "survivors": 0}), \
             mock.patch.object(ch.backtest, "run_backtest",
                               return_value={"status": "ok", "tokens_spent": 20,
                                            "rows_written": 9, "asins_sampled": 300}), \
             mock.patch.object(ch, "_deadline_exceeded", return_value=False):
            ch.run_hourly_collect(api=api)
        mfinish.assert_called_once()
        kwargs = mfinish.call_args.kwargs
        self.assertEqual(kwargs["tier1_tokens"], 3)
        self.assertEqual(kwargs["tier2_tokens"], 13)
        self.assertEqual(kwargs["tier3_tokens"], 20)
        self.assertEqual(kwargs["backtest_rows_written"], 9)
        self.assertEqual(kwargs["backtest_asins_sampled"], 300)


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

    def test_small_budget_never_forces_one_candidate_into_tier3_reserve(self):
        """A 14-token bank gives Tier 2 only 10 after Tier 3's 4-token reserve. The old
        max(1, ...) still bought one 4-token enrichment after the 10-token finder, consuming all
        14. The scan must now make no Keepa call when its own 10-token cap cannot cover both."""
        api = FakeApi(tokens_left=14)
        with mock.patch.object(ch.discovery_hints, "hinted_brand_seeds", return_value=["Lego"]), \
             mock.patch.object(keepa_client, "find_candidates") as mfind, \
             mock.patch.object(keepa_client, "enrich") as menrich:
            result = ch.hint_led_scan(api, token_budget=10)
        mfind.assert_not_called()
        menrich.assert_not_called()
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["tokens_spent"], 0)
        self.assertIn("finder plus one candidate", result["reason"])

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

    def test_survivors_are_ranked_and_ranking_model_reported(self):
        """ML audit fix (2026-07-09, doctrine §5 — BLOCKER): the hourly path never called
        _rank_winners, so the trained ranker had NO reader on the only production scanning
        path — no shadow ordering existed and a promotion would have changed nothing here.
        hint_led_scan must now rank survivors through pipeline._rank_winners and report which
        model ordered the queue."""
        api = FakeApi()
        with mock.patch.object(ch.discovery_hints, "hinted_brand_seeds", return_value=["Lego"]),              mock.patch.object(keepa_client, "find_candidates", return_value=["A1"]),              mock.patch.object(keepa_client, "enrich", return_value=[{"asin": "A1", "price": 20}]),              mock.patch.object(ch.model_mod, "load_model", return_value=None),              mock.patch.object(ch.pipeline, "_evaluate",
                               return_value=[{"asin": "A1", "price": 20, "blended_score": 80}]),              mock.patch.object(ch.pipeline, "_rank_winners",
                               side_effect=lambda w: (w, "rule")) as mrank,              mock.patch.object(ch.scoring, "oa_hard_reject", return_value=None),              mock.patch.object(db, "log_lead", return_value=101),              mock.patch.object(db, "upsert_keepa_snapshot"),              mock.patch.object(ch.predictions, "record_predictions_for"),              mock.patch.object(ch.shadow_outcomes, "enqueue_survivors"):
            r = ch.hint_led_scan(api, 100, run_id="r1")
        mrank.assert_called_once()
        self.assertEqual(r["ranking_model"], "rule")

    def test_limit_reserves_for_the_finder_search_fallback_cost(self):
        """Review fix (2026-07-08, live incident): `limit` used to be sized ONLY off enrich's
        per-ASIN cost (token_budget // TOKENS_PER_CANDIDATE_ESTIMATE), reserving nothing for
        find_candidates()'s own ~10-30 token search-fallback cost (Product Finder is
        REQUEST_REJECTED on this Pro-plan key, so it ALWAYS falls back to a flat
        SEARCH_TOKENS_PER_TERM/term search first) -- live-confirmed this made tier 2's real
        combined spend structurally exceed its own token_budget every run. With 3 hints and a
        100-token budget, the OLD sizing would give limit=25 (100//4); the fixed sizing must
        reserve 3*SEARCH_TOKENS_PER_TERM=30 first, giving limit=(100-30)//4=17."""
        api = FakeApi()
        with mock.patch.object(ch.discovery_hints, "hinted_brand_seeds",
                               return_value=["Lego", "Fisher-Price", "Melissa"]), \
             mock.patch.object(keepa_client, "find_candidates", return_value=[]) as mfind:
            ch.hint_led_scan(api, 100)
        self.assertEqual(mfind.call_args.kwargs.get("limit"), 17)

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
