"""
test_train_ranker.py — the daily ranker-training job (train_ranker.py + train-ranker.yml).

Guards the non-negotiables: NO automatic promotion (the script must never write ai-brain.json),
honest refusal below the data floor, correct rank metrics, and the champion/challenger verdict
wording the report/Discord post rely on.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import train_ranker as tr  # noqa: E402


class NoPromotionGuardTest(unittest.TestCase):
    def test_never_writes_the_brain(self):
        """Promotion is human-only: the training job must have NO write path to ai-brain.json —
        it may not even mention opening it. A source-level guard (same spirit as the analyst's
        AST guard): any write-mode open near an ai-brain reference fails this test."""
        src_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "train_ranker.py")
        with open(src_path, encoding="utf-8") as f:
            src = f.read()
        for line in src.splitlines():
            if "ai-brain.json" in line and "open(" in line:
                self.fail(f"train_ranker.py touches ai-brain.json with open(): {line.strip()}")
        self.assertNotIn('json.dump(brain', src)


class RankMetricsTest(unittest.TestCase):
    def test_auc_and_winners(self):
        scores = [0.9, 0.8, 0.2, 0.1]
        y = [1, 1, 0, 0]
        m = tr.rank_metrics(scores, y, top_n=2)
        self.assertEqual(m["auc"], 1.0)
        self.assertEqual(m["winners_in_top"], 2)

    def test_none_scores_rank_last(self):
        m = tr.rank_metrics([None, 0.5], [0, 1], top_n=1)
        self.assertEqual(m["winners_in_top"], 1)  # the scored winner outranks the None

    def test_single_class_auc_is_none(self):
        m = tr.rank_metrics([0.5, 0.6], [1, 1], top_n=2)
        self.assertIsNone(m["auc"])


class VerdictTest(unittest.TestCase):
    def test_challenger_must_beat_margin(self):
        champ = {"auc": 0.60}
        self.assertIn("LOSES", tr.verdict_line(champ, {"auc": 0.61}))       # inside margin
        win = tr.verdict_line(champ, {"auc": 0.70})
        self.assertIn("CHALLENGER WINS", win)
        self.assertIn("human approval", win)                                # never auto-promotes
        self.assertIn("INCONCLUSIVE", tr.verdict_line({"auc": None}, {"auc": 0.9}))


class TrainAndEvaluateTest(unittest.TestCase):
    def _rows(self, n_asins=20, windows=3):
        rows = []
        for i in range(n_asins):
            # separable synthetic signal: cheap+fast products profit
            profitable = i % 2 == 0
            for w in range(windows):
                rows.append({
                    "asin": f"A{i:03d}",
                    "label": profitable,
                    "label_quality": "backtest",
                    "features": {"price": 20 if profitable else 80, "est_sales": 30 if profitable else 2,
                                 "offers": 5, "sales_rank": 10000, "weight_lb": 1.0,
                                 "avg_price_90": 20 if profitable else 80, "avg_offers_90": 5,
                                 "avg_sales_rank_90": 10000, "oos_90": 0, "amazon_bb_share": 0,
                                 "category": "toys"},
                })
        return rows

    def test_refusal_passthrough(self):
        r = tr.train_and_evaluate({"refused": True, "reason": "too few rows", "rows": [], "by_tier": {}})
        self.assertTrue(r["refused"])
        self.assertIn("too few", r["reason"])
        block = tr.render_report(r)
        self.assertIn("REFUSED", block)

    def test_full_cycle_on_synthetic_rows(self):
        rows = self._rows()
        r = tr.train_and_evaluate({"refused": False, "rows": rows, "by_tier": {"backtest": {
            "total": len(rows), "positive": sum(1 for x in rows if x["label"]),
            "negative": sum(1 for x in rows if not x["label"])}}, "silver_caveat": "shadow caveat"})
        self.assertFalse(r["refused"])
        self.assertIsNotNone(r["challenger"]["auc"])
        self.assertGreater(r["challenger"]["auc"], 0.9)  # separable signal must be learned
        self.assertIn("VERDICT", r["verdict"])
        block = tr.render_report(r)
        self.assertIn("HUMAN-ONLY", block)
        self.assertIn("backtest", block)

    def test_split_is_by_asin(self):
        # windows of one ASIN never straddle train/val (delegated to backtest.split_by_asin,
        # asserted here at the integration level)
        rows = self._rows(n_asins=30, windows=4)
        import backtest
        train, val = backtest.split_by_asin(rows, val_fraction=0.3)
        self.assertFalse({r["asin"] for r in train} & {r["asin"] for r in val})


class TrainingSetFingerprintTest(unittest.TestCase):
    """Session 55: the skip-if-unchanged cadence guard. The fingerprint must be stable across
    row REORDERING (Supabase pagination order isn't guaranteed) and must change whenever a row
    is added or an existing row's content changes (a re-simulated backtest window flipping its
    label) — a plain row-count comparison would miss the latter."""

    def _row(self, asin="B001", label=True, quality="backtest", sim="2026-01-01"):
        return {"asin": asin, "source": "backtest", "label": label, "label_quality": quality,
                "simulation_date": sim}

    def test_same_rows_same_fingerprint_regardless_of_order(self):
        rows = [self._row("B001"), self._row("B002"), self._row("B003")]
        fp1 = tr.training_set_fingerprint({"rows": rows})
        fp2 = tr.training_set_fingerprint({"rows": list(reversed(rows))})
        self.assertEqual(fp1, fp2)

    def test_new_row_changes_fingerprint(self):
        base = [self._row("B001"), self._row("B002")]
        fp1 = tr.training_set_fingerprint({"rows": base})
        fp2 = tr.training_set_fingerprint({"rows": base + [self._row("B003")]})
        self.assertNotEqual(fp1, fp2)
        self.assertEqual(fp2["row_count"], fp1["row_count"] + 1)

    def test_relabeled_row_changes_fingerprint_at_same_row_count(self):
        """A re-simulated backtest window can flip would_have_profited without adding a row —
        row_count alone would miss this; the content hash must not."""
        fp1 = tr.training_set_fingerprint({"rows": [self._row("B001", label=True)]})
        fp2 = tr.training_set_fingerprint({"rows": [self._row("B001", label=False)]})
        self.assertEqual(fp1["row_count"], fp2["row_count"])
        self.assertNotEqual(fp1["content_hash"], fp2["content_hash"])

    def test_empty_rows_is_stable(self):
        fp1 = tr.training_set_fingerprint({"rows": []})
        fp2 = tr.training_set_fingerprint({})
        self.assertEqual(fp1, fp2)
        self.assertEqual(fp1["row_count"], 0)


class FingerprintStorageTest(unittest.TestCase):
    """fetch_last_fingerprint/upload_fingerprint — mocked network only, same pattern as
    test_raw_inbox.py. Both must degrade to an honest no-op, never raise, when Supabase env or
    the network is unavailable."""

    def test_fetch_returns_none_without_supabase_env(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SUPABASE_URL", None)
            os.environ.pop("SUPABASE_SERVICE_KEY", None)
            self.assertIsNone(tr.fetch_last_fingerprint())

    def test_fetch_returns_none_on_404_first_ever_run(self):
        resp = mock.Mock(status_code=404)
        with mock.patch.dict(os.environ, {"SUPABASE_URL": "https://x.supabase.co",
                                          "SUPABASE_SERVICE_KEY": "k"}), \
             mock.patch("requests.get", return_value=resp):
            self.assertIsNone(tr.fetch_last_fingerprint())

    def test_fetch_returns_stored_json_on_200(self):
        resp = mock.Mock(status_code=200)
        resp.json.return_value = {"row_count": 42, "content_hash": "abc"}
        with mock.patch.dict(os.environ, {"SUPABASE_URL": "https://x.supabase.co",
                                          "SUPABASE_SERVICE_KEY": "k"}), \
             mock.patch("requests.get", return_value=resp):
            self.assertEqual(tr.fetch_last_fingerprint(), {"row_count": 42, "content_hash": "abc"})

    def test_fetch_never_raises_on_network_error(self):
        with mock.patch.dict(os.environ, {"SUPABASE_URL": "https://x.supabase.co",
                                          "SUPABASE_SERVICE_KEY": "k"}), \
             mock.patch("requests.get", side_effect=RuntimeError("network down")):
            self.assertIsNone(tr.fetch_last_fingerprint())

    def test_upload_returns_false_without_supabase_env(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SUPABASE_URL", None)
            os.environ.pop("SUPABASE_SERVICE_KEY", None)
            self.assertFalse(tr.upload_fingerprint({"row_count": 1, "content_hash": "x"}))

    def test_upload_posts_fingerprint_json(self):
        posted = []

        def fake_post(url, headers=None, json=None, data=None, timeout=None):
            posted.append({"url": url, "data": data})
            resp = mock.Mock(status_code=200)
            resp.raise_for_status = lambda: None
            resp.text = ""
            return resp

        with mock.patch.dict(os.environ, {"SUPABASE_URL": "https://x.supabase.co",
                                          "SUPABASE_SERVICE_KEY": "k"}), \
             mock.patch("requests.post", side_effect=fake_post):
            ok = tr.upload_fingerprint({"row_count": 7, "content_hash": "deadbeef"})
        self.assertTrue(ok)
        upload_call = posted[-1]
        self.assertIn("ranker/current/fingerprint.json", upload_call["url"])
        import json as _json
        self.assertEqual(_json.loads(upload_call["data"]), {"row_count": 7, "content_hash": "deadbeef"})

    def test_upload_never_raises_on_network_error(self):
        with mock.patch.dict(os.environ, {"SUPABASE_URL": "https://x.supabase.co",
                                          "SUPABASE_SERVICE_KEY": "k"}), \
             mock.patch("requests.post", side_effect=RuntimeError("network down")):
            self.assertFalse(tr.upload_fingerprint({"row_count": 1, "content_hash": "x"}))


if __name__ == "__main__":
    unittest.main()
