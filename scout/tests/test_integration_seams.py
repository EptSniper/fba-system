"""
test_integration_seams.py — the structural deliverable from the Session 55 review (2026-07-06):
a seam-test suite so a producer/consumer drift like the ones this session found and fixed can
never again survive undetected just because each side had its own tests in isolation.

Every review finding this session's items 1-5 fixed shared one shape: function A (the producer)
and function B (the consumer) each had passing unit tests, yet A silently broke a contract B
depended on — because nothing ever called them back-to-back with real data on both sides. Each
class below is one named seam from that instruction, real components on both sides, mocking
ONLY the outermost network/disk boundary (Supabase reads/writes, model-artifact upload/download)
— never the functions whose interaction is actually under test.

  1. CollectorToBacktestRowsSeamTest — scout/backtest.py's build_rows_for_asin() ->
     scout/labels.py's _from_backtest() -> scout/train_ranker.py's source_breakdown().
  2. BackfillFingerprintSeamTest — scout/signals/trends_backfill.py's backfill_row_features() ->
     scout/labels.py's _from_backtest() -> scout/train_ranker.py's training_set_fingerprint().
  3. TrainUploadConsumerQueueSeamTest — scout/train_ranker.py's train_and_evaluate() ->
     save_artifacts() -> load_challenger() -> challenger_score() -> scout/pipeline.py's
     _rank_winners().
  4. PromotionKeyBehaviorSeamTest — a real ai-brain.json-shaped file's
     scoring.rankingChampion key -> train_ranker.ranking_champion() -> pipeline._rank_winners().

Auto-discovered by run_all_tests.py (a bare `python -m pytest scout/tests -q`) — no separate
registration needed.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtest as bt  # noqa: E402
import db  # noqa: E402
import labels  # noqa: E402
import pipeline  # noqa: E402
import train_ranker as tr  # noqa: E402
from signals import trends_backfill  # noqa: E402

BASE = dt.date(2026, 1, 1).toordinal()


def _constant_history(days=200, price=20.0, offers=5, rank=15000):
    """Same fixture shape as test_backtest.py's — a daily, constant, in-stock history."""
    price_s = [(BASE + d, price) for d in range(days)]
    offers_s = [(BASE + d, float(offers)) for d in range(days)]
    rank_s = [(BASE + d, float(rank)) for d in range(days)]
    return {"price": price_s, "offers": offers_s, "sales_rank": rank_s, "amazon": []}


# ---------------------------------------------------------------------------
# Seam 1: collector -> backtest_rows
# ---------------------------------------------------------------------------
class CollectorToBacktestRowsSeamTest(unittest.TestCase):
    """Regression target: labels.py's _from_backtest() was silently dropping
    sample_source/category/ip_risk on read, even though build_rows_for_asin() always writes
    them — every backtest row would have rendered as sample_source='n/a' in
    train_ranker.source_breakdown()'s onpolicy/explore/dealfeed report section forever, and
    neither function's own isolated tests could ever have caught it."""

    def test_sample_source_survives_producer_to_consumer(self):
        hist = _constant_history(days=200, price=30.0)
        static = {"brand": "Acme", "category": "toys", "weight_lb": 1.0}
        produced = bt.build_rows_for_asin("B0SEAM01", hist, static, sample_source="dealfeed")
        self.assertTrue(produced, "fixture produced no backtest rows — widen the history window")
        for r in produced:
            self.assertEqual(r["sample_source"], "dealfeed")
            self.assertEqual(r["category"], "toys")
            self.assertIn("ip_risk", r)

        # Mock ONLY the network boundary: pretend these rows already round-tripped through
        # Supabase (upsert_backtest_rows -> all_backtest_rows) unchanged.
        with mock.patch.object(db, "all_backtest_rows", return_value=produced):
            consumed = labels._from_backtest()

        self.assertEqual(len(consumed), len(produced))
        for r in consumed:
            self.assertEqual(r["sample_source"], "dealfeed")  # the exact field the bug dropped
            self.assertEqual(r["category"], "toys")
            self.assertIn("ip_risk", r)

        breakdown = tr.source_breakdown(consumed, [0.5] * len(consumed))
        self.assertIn("dealfeed", breakdown)
        self.assertNotIn("n/a", breakdown)  # pre-fix: every row would land here instead


# ---------------------------------------------------------------------------
# Seam 2: backfill -> feature content -> fingerprint change
# ---------------------------------------------------------------------------
class BackfillFingerprintSeamTest(unittest.TestCase):
    """Regression target: training_set_fingerprint() originally hashed only row IDENTITY
    (asin/source/label/label_quality/date) — never feature content. trends_backfill.py's
    backfill_row_features() patches features_snapshot IN PLACE on that SAME identity, so the
    old fingerprint would have stayed byte-identical across a backfill and the every-6h
    skip-if-unchanged guard would have suppressed every retrain after it, forever."""

    def test_backfill_changes_the_fingerprint_after_a_real_relabel_readback(self):
        as_of = dt.date(2026, 3, 1)
        # 12 weeks of a real, non-flat brand series, entirely closed before as_of (leakage-safe
        # per trends.trends_features' own boundary).
        brand_series = [(as_of - dt.timedelta(weeks=w), 40.0 + w) for w in range(12, 0, -1)]

        raw_row_before = {
            "asin": "B0SEAM02", "simulation_date": as_of.isoformat(), "would_have_profited": True,
            # ML rigor directive (2026-07-13): labels.py's _from_backtest() now derives the label
            # at READ time from est_profit/landed_cost (backtest.consistent_label()) instead of
            # trusting the stored would_have_profited column directly -- these two fields (clearly
            # a real, positive case: roi=10/15=0.667, well past both the $3 and 30% bars) are what
            # actually drive the label now; would_have_profited above is kept only as the OLD
            # stored value this row would have carried, to prove the read-time recompute doesn't
            # even look at it.
            "est_profit": 10.0, "landed_cost": 15.0,
            "sample_source": "onpolicy", "category": "toys", "ip_risk": False,
            "features_snapshot": {"asin": "B0SEAM02", "price": 25.0, "brand": "Acme", "category": "toys"},
        }

        def _fingerprint_for(raw_row):
            with mock.patch.object(db, "all_backtest_rows", return_value=[raw_row]):
                consumed = labels._from_backtest()
            return tr.training_set_fingerprint({"rows": consumed})

        fp_before = _fingerprint_for(raw_row_before)

        raw_row_after = trends_backfill.backfill_row_features(
            raw_row_before, brand_series=brand_series, category_series=[])
        self.assertIsNotNone(raw_row_after)
        self.assertEqual(raw_row_after["asin"], raw_row_before["asin"])
        self.assertEqual(raw_row_after["simulation_date"], raw_row_before["simulation_date"])
        self.assertNotEqual(raw_row_after["features_snapshot"], raw_row_before["features_snapshot"])

        fp_after = _fingerprint_for(raw_row_after)

        self.assertEqual(fp_before["row_count"], fp_after["row_count"])       # identity unchanged
        self.assertNotEqual(fp_before["content_hash"], fp_after["content_hash"])  # content changed


# ---------------------------------------------------------------------------
# Seam 3: train -> upload -> consumer load -> queue order
# ---------------------------------------------------------------------------
class TrainUploadConsumerQueueSeamTest(unittest.TestCase):
    """Regression target: nothing in the codebase ever consumed the cloud-trained ranker
    artifact this whole module exists to produce — training ran every cadence but had no
    reader. Proves a REAL fitted LightGBM model (not a stub) changes REAL queue order end to
    end. Mocks only the network upload/download: the just-saved artifact is placed directly
    where load_challenger() looks for it, exactly as fetch_current_model() would leave it."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="fba-seam-")
        tr.reset_challenger_cache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        tr.reset_challenger_cache()

    @staticmethod
    def _feat(price):
        f = {k: 50.0 for k in tr.NUMERIC_FEATURES}
        f["price"] = price
        return f

    @classmethod
    def _row(cls, asin, price, label):
        return {"asin": asin, "source": "backtest", "label": label, "label_quality": "backtest",
                "simulation_date": "2026-01-01", "sample_source": "onpolicy",
                "features": cls._feat(price)}

    def test_a_real_trained_model_reorders_the_live_queue(self):
        rows = ([self._row(f"POS{i:03d}", 10.0, True) for i in range(30)]
               + [self._row(f"NEG{i:03d}", 200.0, False) for i in range(30)])
        assembled = {"rows": rows, "refused": False, "reason": "ok", "by_tier": {},
                    "bronze_rows": [], "silver_caveat": "", "bronze_caveat": ""}

        result = tr.train_and_evaluate(assembled)  # REAL LightGBM fit
        self.assertFalse(result["refused"])
        self.assertGreater(result["challenger"]["auc"], 0.9)  # fixture actually separates

        saved_paths = tr.save_artifacts(result, self.tmpdir)  # REAL joblib.dump
        self.assertTrue(any(p.endswith("model.joblib") for p in saved_paths))

        current_dir = os.path.join(self.tmpdir, "models_dir", "current")
        os.makedirs(current_dir, exist_ok=True)
        shutil.copy(os.path.join(self.tmpdir, "model.joblib"),
                   os.path.join(current_dir, "model.joblib"))

        with mock.patch.object(tr, "ranking_champion", return_value="challenger"), \
             mock.patch.object(tr, "MODELS_DIR", os.path.join(self.tmpdir, "models_dir")):
            champion = tr.load_challenger()  # REAL joblib.load + shape check
            self.assertIsNotNone(champion)
            self.assertTrue(hasattr(champion["model"], "predict_proba"))

            pos_score = tr.challenger_score(champion, self._feat(10.0))   # REAL predict_proba
            neg_score = tr.challenger_score(champion, self._feat(200.0))
            self.assertGreater(pos_score, 0.9)
            self.assertLess(neg_score, 0.1)

            winners = [
                {"asin": "LOW_TRIAGE_HIGH_CHALLENGER", "triage_score": 1,
                 "challenger_proba": pos_score, "blended_score": 0},
                {"asin": "HIGH_TRIAGE_LOW_CHALLENGER", "triage_score": 99,
                 "challenger_proba": neg_score, "blended_score": 0},
            ]
            ranked, ranking_model = pipeline._rank_winners(winners)  # REAL sort

        self.assertEqual(ranking_model, "challenger")
        self.assertEqual([w["asin"] for w in ranked],
                        ["LOW_TRIAGE_HIGH_CHALLENGER", "HIGH_TRIAGE_LOW_CHALLENGER"])


# ---------------------------------------------------------------------------
# Seam 4: promotion key -> behavior change
# ---------------------------------------------------------------------------
class PromotionKeyBehaviorSeamTest(unittest.TestCase):
    """Regression target: the promotion contract (ai-brain.json's scoring.rankingChampion is
    the ONLY switch, human-set, never touched by training) is exactly what every report has
    always claimed — this proves it, by flipping a REAL file's content (not mocking
    ranking_champion() itself) and confirming pipeline._rank_winners() actually reacts, and
    reverts cleanly when flipped back."""

    def setUp(self):
        tr.reset_challenger_cache()

    def tearDown(self):
        tr.reset_challenger_cache()

    @staticmethod
    def _brain_path(ranking_champion_value):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump({"scoring": {"rankingChampion": ranking_champion_value}}, f)
        f.close()
        return f.name

    @staticmethod
    def _winners():
        return [
            {"asin": "A", "triage_score": 10, "challenger_proba": 0.99, "blended_score": 0},
            {"asin": "B", "triage_score": 90, "challenger_proba": 0.01, "blended_score": 0},
        ]

    def test_flipping_the_brain_key_alone_changes_queue_order(self):
        rule_path = self._brain_path("rule")
        challenger_path = self._brain_path("challenger")
        try:
            with mock.patch.object(tr, "BRAIN_PATH", rule_path):
                ranked_rule, model_rule = pipeline._rank_winners(self._winners())
            with mock.patch.object(tr, "BRAIN_PATH", challenger_path):
                ranked_chall, model_chall = pipeline._rank_winners(self._winners())
            # and back again — the switch is not one-directional/sticky
            with mock.patch.object(tr, "BRAIN_PATH", rule_path):
                ranked_rule_again, model_rule_again = pipeline._rank_winners(self._winners())
        finally:
            os.remove(rule_path)
            os.remove(challenger_path)

        self.assertEqual(model_rule, "rule")
        self.assertEqual([w["asin"] for w in ranked_rule], ["B", "A"])       # triage_score order
        self.assertEqual(model_chall, "challenger")
        self.assertEqual([w["asin"] for w in ranked_chall], ["A", "B"])     # challenger_proba order
        self.assertEqual(model_rule_again, "rule")
        self.assertEqual([w["asin"] for w in ranked_rule_again], ["B", "A"])


if __name__ == "__main__":
    unittest.main()
