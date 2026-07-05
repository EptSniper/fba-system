"""
test_shadow_outcomes.py — the shadow-outcome tracker (DATA_ENGINE_PLAN.md V1).

Covers the plan's required surface: enqueue row-building + dedupe key, would_have_profited math
at the ORIGINAL landed cost, the weekly recheck (token cap + deferral + label writing), the
honest disabled no-ops, and labels.py's gold/silver tier separation.
"""
import os
import sys
import datetime as dt
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import shadow_outcomes as so  # noqa: E402
import labels  # noqa: E402
import db  # noqa: E402
import scoring  # noqa: E402


FIXED_NOW = dt.datetime(2026, 7, 5, 12, 0, 0, tzinfo=dt.timezone.utc)


class EnqueueRowsTest(unittest.TestCase):
    def test_two_checkpoints_with_frozen_snapshot(self):
        survivor = {"asin": "B01", "price": 30.0, "offers": 4, "sales_rank": 12000,
                    "weight_lb": 1.2, "category": "toys", "brand": "Lego"}
        rows = so.build_enqueue_rows(survivor, run_id=99, now=FIXED_NOW)
        self.assertEqual(len(rows), 2)
        days = sorted(r["checkpoint_day"] for r in rows)
        self.assertEqual(days, [30, 60])
        r30 = next(r for r in rows if r["checkpoint_day"] == 30)
        # landed cost is the ORIGINAL simulated buy-in, frozen here
        self.assertEqual(r30["landed_cost"], scoring.assumed_landed_cost(30.0))
        self.assertEqual(r30["price_then"], 30.0)
        self.assertEqual(r30["candidate_run_id"], 99)
        # due_at = enqueued_at + checkpoint_day days
        self.assertEqual(r30["due_at"], (FIXED_NOW + dt.timedelta(days=30)).isoformat())
        # features snapshot is pre-decision-only (leakage-safe) — no verdict/score leaks in
        self.assertIn("brand", r30["features_snapshot"])
        self.assertNotIn("verdict", r30["features_snapshot"])
        self.assertNotIn("blended_score", r30["features_snapshot"])

    def test_no_asin_no_rows(self):
        self.assertEqual(so.build_enqueue_rows({"price": 10}, run_id=1, now=FIXED_NOW), [])


class ComputeLabelTest(unittest.TestCase):
    def test_would_have_profited_at_original_cost(self):
        row = {"landed_cost": 0.01, "weight_lb": 1.0, "category": None}
        out = so.compute_label(row, {"price": 40.0, "offers": 3, "sales_rank": 8000})
        self.assertTrue(out["would_have_profited"])   # net proceeds >> 0.01 cost
        self.assertEqual(out["status"], "done")
        self.assertEqual(out["price_now"], 40.0)

    def test_would_not_have_profited_at_high_cost(self):
        row = {"landed_cost": 1000.0, "weight_lb": 1.0, "category": None}
        out = so.compute_label(row, {"price": 40.0, "offers": 3, "sales_rank": 8000})
        self.assertFalse(out["would_have_profited"])  # cost dwarfs any proceeds

    def test_missing_price_yields_error_status(self):
        row = {"landed_cost": 5.0, "weight_lb": 1.0, "category": None}
        out = so.compute_label(row, {"price": None})
        self.assertIsNone(out["would_have_profited"])
        self.assertEqual(out["status"], "error")


class EnqueueSurvivorsTest(unittest.TestCase):
    def test_noop_when_supabase_disabled(self):
        with mock.patch.object(db, "enabled", return_value=False):
            self.assertEqual(so.enqueue_survivors([{"asin": "B01", "price": 10}], run_id=1), 0)

    def test_enqueues_each_survivor(self):
        sent = []
        with mock.patch.object(db, "enabled", return_value=True), \
             mock.patch.object(db, "enqueue_shadow_outcomes",
                               side_effect=lambda rows: (sent.extend(rows), len(rows))[1]):
            n = so.enqueue_survivors(
                [{"asin": "B01", "price": 10}, {"asin": "B02", "price": 20}, {"price": None}],
                run_id=7, now=FIXED_NOW)
        self.assertEqual(n, 2)             # 2 valid ASINs (the no-asin one skipped)
        self.assertEqual(len(sent), 4)     # 2 checkpoints each, ONE batched write

    def test_enqueue_reports_zero_when_write_fails(self):
        # honesty guard: a failed bulk write must NOT report phantom silver labels
        with mock.patch.object(db, "enabled", return_value=True), \
             mock.patch.object(db, "enqueue_shadow_outcomes", return_value=0):
            n = so.enqueue_survivors([{"asin": "B01", "price": 10}], run_id=7, now=FIXED_NOW)
        self.assertEqual(n, 0)


class RunRechecksTest(unittest.TestCase):
    def test_disabled_without_supabase(self):
        with mock.patch.object(db, "enabled", return_value=False):
            r = so.run_rechecks()
        self.assertEqual(r["status"], "disabled")

    def test_disabled_without_keepa(self):
        with mock.patch.object(db, "enabled", return_value=True), \
             mock.patch.object(so.config, "have_keepa", return_value=False):
            r = so.run_rechecks()
        self.assertEqual(r["status"], "disabled")

    def test_recheck_respects_token_cap_and_labels(self):
        due = [
            {"id": 1, "asin": "B01", "landed_cost": 0.01, "weight_lb": 1.0, "category": None},
            {"id": 2, "asin": "B02", "landed_cost": 1000.0, "weight_lb": 1.0, "category": None},
        ]
        completed = {}

        def fake_enrich(batch, api=None):
            return [{"asin": a, "price": 40.0, "offers": 3, "sales_rank": 8000} for a in batch]

        with mock.patch.object(db, "enabled", return_value=True), \
             mock.patch.object(so.config, "have_keepa", return_value=True), \
             mock.patch.object(db, "due_shadow_checkpoints", return_value=due), \
             mock.patch.object(db, "complete_shadow_checkpoint",
                               side_effect=lambda rid, f: completed.__setitem__(rid, f)):
            r = so.run_rechecks(api=object(), token_cap=1, enrich_fn=fake_enrich)

        # cap=1 -> only the first unique ASIN priced this run; the second deferred to next week
        self.assertEqual(r["tokens_spent"], 1)
        self.assertEqual(r["deferred_asins"], 1)
        self.assertEqual(r["checked"], 1)
        self.assertIn(1, completed)
        self.assertNotIn(2, completed)
        self.assertTrue(completed[1]["would_have_profited"])


class LabelsTierTest(unittest.TestCase):
    def test_shadow_rows_are_silver(self):
        shadow = [{
            "asin": "B01", "would_have_profited": True, "checkpoint_day": 30,
            "features_snapshot": {"price": 20, "brand": "Lego", "verdict": "review"},  # verdict must be filtered out
        }]
        with mock.patch.object(db, "all_shadow_outcomes", return_value=shadow):
            rows = labels._from_shadow()
        self.assertEqual(rows[0]["label_quality"], "silver")
        self.assertTrue(rows[0]["label"])
        self.assertIn("price", rows[0]["features"])
        self.assertNotIn("verdict", rows[0]["features"])  # leakage guard at read time

    def test_assemble_separates_tiers(self):
        gold = [{"asin": "G1", "source": "supabase", "features": {"price": 10}, "label": True, "label_quality": "gold"},
                {"asin": "G2", "source": "supabase", "features": {"price": 12}, "label": False, "label_quality": "gold"}]
        silver = [{"asin": "S1", "source": "shadow", "features": {"price": 20}, "label": True, "label_quality": "silver"}]
        with mock.patch.object(labels, "_from_supabase", return_value=gold), \
             mock.patch.object(labels, "_from_local_ledger", return_value=[]), \
             mock.patch.object(labels, "_from_shadow", return_value=silver):
            res = labels.assemble_training_rows()
        self.assertEqual(res["by_tier"]["gold"]["total"], 2)
        self.assertEqual(res["by_tier"]["silver"]["total"], 1)
        self.assertEqual(res["silver_count"], 1)
        self.assertIn("execution", res["silver_caveat"])

    def test_gold_only_slice_excludes_silver(self):
        gold = [{"asin": "G1", "source": "supabase", "features": {"price": 10}, "label": True, "label_quality": "gold"}]
        with mock.patch.object(labels, "_from_supabase", return_value=gold), \
             mock.patch.object(labels, "_from_local_ledger", return_value=[]), \
             mock.patch.object(labels, "_from_shadow", return_value=[{"features": {"price": 1}, "label": True, "label_quality": "silver"}]):
            res = labels.assemble_training_rows(include_silver=False)
        self.assertNotIn("silver", res["by_tier"])
        self.assertEqual(res["trainable_count"], 1)


if __name__ == "__main__":
    unittest.main()
