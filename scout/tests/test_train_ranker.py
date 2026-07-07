"""
test_train_ranker.py — the daily ranker-training job (train_ranker.py + train-ranker.yml).

Guards the non-negotiables: NO automatic promotion (the script must never write ai-brain.json),
honest refusal below the data floor, correct rank metrics, and the champion/challenger verdict
wording the report/Discord post rely on.
"""
import json
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

    def test_bronze_rows_never_enter_relevance_target(self):
        """Session 55: assembled['bronze_rows'] must have zero influence on train/val — feeding
        the SAME rows in as bronze vs omitted must produce an IDENTICAL champion/challenger."""
        rows = self._rows()
        by_tier = {"backtest": {"total": len(rows), "positive": sum(1 for x in rows if x["label"]),
                                "negative": sum(1 for x in rows if not x["label"])}}
        bronze_rows = [{"asin": "BRONZE1", "label": True, "label_quality": "bronze",
                       "features": rows[0]["features"]}]
        base = {"refused": False, "rows": rows, "by_tier": by_tier, "silver_caveat": "x"}
        r_without = tr.train_and_evaluate(dict(base))
        r_with = tr.train_and_evaluate(dict(base, bronze_rows=bronze_rows))
        self.assertEqual(r_without["challenger"]["auc"], r_with["challenger"]["auc"])
        self.assertEqual(r_without["train_rows"], r_with["train_rows"])
        self.assertEqual(r_without["val_rows"], r_with["val_rows"])
        self.assertIsNone(r_without["bronze_agreement"])  # no bronze_rows supplied -> None
        self.assertIsNotNone(r_with["bronze_agreement"])
        self.assertEqual(r_with["bronze_agreement"]["n"], 1)


class BronzeAgreementTest(unittest.TestCase):
    def test_none_when_no_bronze_rows(self):
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
        import numpy as np
        X = np.array([[1.0], [2.0]])
        clf = LogisticRegression().fit(X, [0, 1])
        scaler = StandardScaler().fit(X)
        self.assertIsNone(tr.bronze_agreement(clf, scaler, []))

    def _row(self, price, profitable):
        return {"label": profitable, "features": {
            "price": price, "weight_lb": 1.0, "sales_rank": 1000, "est_sales": 50, "offers": 5,
            "avg_price_90": price, "avg_offers_90": 5, "avg_sales_rank_90": 1000, "oos_90": 0,
            "amazon_bb_share": 0}}

    def test_agreement_rate_reflects_matches(self):
        import lightgbm as lgb
        # a trivially separable classifier over the real NUMERIC_FEATURES shape: cheap -> profitable
        train_rows = [self._row(15.0, True), self._row(20.0, True),
                     self._row(80.0, False), self._row(90.0, False)]
        Xtr, ytr = tr.build_matrix(train_rows)
        clf = lgb.LGBMClassifier(random_state=42, verbosity=-1, min_child_samples=1,
                                 num_leaves=3).fit(Xtr, ytr)
        bronze_rows = [
            dict(self._row(15.0, True), asin="B1", label_quality="bronze"),
            dict(self._row(95.0, False), asin="B2", label_quality="bronze"),  # operator passed, model agrees
        ]
        result = tr.bronze_agreement(clf, None, bronze_rows)
        self.assertEqual(result["n"], 2)
        self.assertEqual(result["agreement_rate"], 1.0)


class RankingChampionTest(unittest.TestCase):
    """Review fix (2026-07-06): scoring.rankingChampion is the human-only promotion switch —
    every report has always SAID promotion works this way, but nothing ever read it. Must
    default to 'rule' (shadow-only) whenever the brain is missing, unreadable, or holds an
    unrecognized value — never an accidental promotion."""

    def _brain_at(self, content):
        import tempfile
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(content, f)
        f.close()
        return f.name

    def test_defaults_to_rule_when_brain_missing(self):
        with mock.patch.object(tr, "BRAIN_PATH", "/nonexistent/path/ai-brain.json"):
            self.assertEqual(tr.ranking_champion(), "rule")

    def test_reads_challenger_when_explicitly_set(self):
        path = self._brain_at({"scoring": {"rankingChampion": "challenger"}})
        try:
            with mock.patch.object(tr, "BRAIN_PATH", path):
                self.assertEqual(tr.ranking_champion(), "challenger")
        finally:
            os.remove(path)

    def test_unrecognized_value_defaults_to_rule(self):
        path = self._brain_at({"scoring": {"rankingChampion": "some_typo"}})
        try:
            with mock.patch.object(tr, "BRAIN_PATH", path):
                self.assertEqual(tr.ranking_champion(), "rule")
        finally:
            os.remove(path)

    def test_explicit_rule_reads_as_rule(self):
        path = self._brain_at({"scoring": {"rankingChampion": "rule"}})
        try:
            with mock.patch.object(tr, "BRAIN_PATH", path):
                self.assertEqual(tr.ranking_champion(), "rule")
        finally:
            os.remove(path)


class LoadChallengerTest(unittest.TestCase):
    """The LIVE consumer of the cloud-trained ranker artifact — the review's core finding was
    that nothing in the codebase ever read this. Every failure mode must degrade to None
    (shadow/rule fallback), never raise."""

    def setUp(self):
        tr.reset_challenger_cache()

    def tearDown(self):
        tr.reset_challenger_cache()

    def test_none_when_not_promoted(self):
        with mock.patch.object(tr, "ranking_champion", return_value="rule"):
            self.assertIsNone(tr.load_challenger())

    def test_loads_local_artifact_when_promoted(self):
        import tempfile, shutil, joblib
        tmpdir = tempfile.mkdtemp()
        try:
            model_dir = os.path.join(tmpdir, "current")
            os.makedirs(model_dir)
            joblib.dump({"model": "fake_model", "scaler": "fake_scaler", "features": []},
                       os.path.join(model_dir, "model.joblib"))
            with mock.patch.object(tr, "ranking_champion", return_value="challenger"), \
                 mock.patch.object(tr, "MODELS_DIR", tmpdir):
                loaded = tr.load_challenger()
            self.assertEqual(loaded["model"], "fake_model")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_falls_back_to_fetch_when_local_missing(self):
        import tempfile, shutil
        tmpdir = tempfile.mkdtemp()
        try:
            with mock.patch.object(tr, "ranking_champion", return_value="challenger"), \
                 mock.patch.object(tr, "MODELS_DIR", tmpdir), \
                 mock.patch.object(tr, "fetch_current_model", return_value=None) as mock_fetch:
                loaded = tr.load_challenger()
            self.assertIsNone(loaded)
            mock_fetch.assert_called_once()  # attempted a live download when nothing local
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_unexpected_shape_degrades_to_none(self):
        import tempfile, shutil, joblib
        tmpdir = tempfile.mkdtemp()
        try:
            model_dir = os.path.join(tmpdir, "current")
            os.makedirs(model_dir)
            joblib.dump("not_a_dict_at_all", os.path.join(model_dir, "model.joblib"))
            with mock.patch.object(tr, "ranking_champion", return_value="challenger"), \
                 mock.patch.object(tr, "MODELS_DIR", tmpdir):
                loaded = tr.load_challenger()
            self.assertIsNone(loaded)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_cached_after_first_call(self):
        with mock.patch.object(tr, "ranking_champion", return_value="rule") as mock_rc:
            tr.load_challenger()
            tr.load_challenger()
        self.assertEqual(mock_rc.call_count, 1)

    def test_force_bypasses_cache(self):
        with mock.patch.object(tr, "ranking_champion", return_value="rule") as mock_rc:
            tr.load_challenger()
            tr.load_challenger(force=True)
        self.assertEqual(mock_rc.call_count, 2)


class ChallengerScoreTest(unittest.TestCase):
    def test_none_champion_returns_none(self):
        self.assertIsNone(tr.challenger_score(None, {"price": 20.0}))

    def test_computes_a_probability_from_a_real_fitted_model(self):
        import lightgbm as lgb
        train_rows = [
            {"label": True, "features": {"price": 15.0}},
            {"label": True, "features": {"price": 18.0}},
            {"label": False, "features": {"price": 85.0}},
            {"label": False, "features": {"price": 90.0}},
        ]
        Xtr, ytr = tr.build_matrix(train_rows)
        clf = lgb.LGBMClassifier(random_state=42, verbosity=-1, min_child_samples=1,
                                 num_leaves=3).fit(Xtr, ytr)
        champion = {"model": clf, "scaler": None, "features": list(tr.NUMERIC_FEATURES)}
        proba = tr.challenger_score(champion, {"price": 16.0})
        self.assertIsInstance(proba, float)
        self.assertGreater(proba, 0.5)  # cheap, matches the "profitable" training cluster

    def test_scoring_failure_degrades_to_none(self):
        champion = {"model": None, "scaler": None, "features": []}  # will raise on .transform
        self.assertIsNone(tr.challenger_score(champion, {"price": 20.0}))


class VectorizeOneConsistencyTest(unittest.TestCase):
    def test_matches_build_matrix_row_for_row(self):
        """vectorize_one is the SAME construction build_matrix uses per row — verified directly
        so the two can never silently drift (the whole point of factoring it out). NaN != NaN
        under ==, so this compares element-wise treating NaN positions as equal to each other."""
        import numpy as np
        rows = [{"features": {"price": 20.0, "days_to_prime_day": 5}, "label": True}]
        X, _ = tr.build_matrix(rows)
        vec = tr.vectorize_one(rows[0]["features"])
        self.assertTrue(np.array_equal(X[0], vec, equal_nan=True))

    def test_missing_features_impute_to_nan_not_zero(self):
        """Review fix (2026-07-06): a genuinely missing value must be NaN, not a fabricated
        0.0 that collides with a real, meaningful zero (see vectorize_one's docstring)."""
        import math
        vec = tr.vectorize_one(None)
        self.assertTrue(all(math.isnan(v) for v in vec))

    def test_present_value_is_not_nan(self):
        vec = tr.vectorize_one({"price": 20.0})
        price_idx = tr.NUMERIC_FEATURES.index("price")
        self.assertEqual(vec[price_idx], 20.0)

    def test_boolean_false_is_zero_not_nan(self):
        """False is a real, present value (e.g. is_bts_window=False means 'confirmed NOT in the
        back-to-school window') — it must convert to 0.0, never be treated as missing."""
        import math
        vec = tr.vectorize_one({"is_bts_window": False})
        idx = tr.NUMERIC_FEATURES.index("is_bts_window")
        self.assertEqual(vec[idx], 0.0)
        self.assertFalse(math.isnan(vec[idx]))


class NewSignalImportanceTest(unittest.TestCase):
    def test_reports_only_new_signal_features(self):
        import lightgbm as lgb
        rows = [
            {"label": True, "features": {"price": 15.0, "days_to_prime_day": 5, "is_bts_window": True}},
            {"label": True, "features": {"price": 18.0, "days_to_prime_day": 3, "is_bts_window": True}},
            {"label": False, "features": {"price": 85.0, "days_to_prime_day": 100, "is_bts_window": False}},
            {"label": False, "features": {"price": 90.0, "days_to_prime_day": 120, "is_bts_window": False}},
        ]
        Xtr, ytr = tr.build_matrix(rows)
        clf = lgb.LGBMClassifier(random_state=42, verbosity=-1, min_child_samples=1,
                                 num_leaves=3).fit(Xtr, ytr)
        importance = tr.new_signal_importance(clf)
        self.assertEqual(set(importance.keys()), set(tr.NEW_SIGNAL_FEATURES))
        self.assertNotIn("price", importance)  # an ORIGINAL feature, not a new signal

    def test_prefers_feature_importances_over_coef(self):
        """LightGBM exposes feature_importances_, not coef_ — new_signal_importance must use it
        when present rather than falling through to the (absent) linear-model path."""
        class FakeLgbModel:
            feature_importances_ = [1.0] * len(tr.NUMERIC_FEATURES)
        importance = tr.new_signal_importance(FakeLgbModel())
        self.assertEqual(set(importance.keys()), set(tr.NEW_SIGNAL_FEATURES))
        # normalized to a share of the total — uniform importances all read equal
        self.assertTrue(all(v == importance[list(importance)[0]] for v in importance.values()))

    def test_falls_back_to_coef_for_a_linear_model(self):
        """Backward compatibility: an OLDER saved artifact might still be a linear model with
        only .coef_ — must not silently return {} just because feature_importances_ is absent."""
        from sklearn.linear_model import LogisticRegression
        rows = [
            {"label": True, "features": {"price": 15.0}}, {"label": True, "features": {"price": 18.0}},
            {"label": False, "features": {"price": 85.0}}, {"label": False, "features": {"price": 90.0}},
        ]
        # a linear model can't take NaN — use only the one populated feature for this fixture
        import numpy as np
        Xtr = np.nan_to_num(tr.build_matrix(rows)[0])
        ytr = tr.build_matrix(rows)[1]
        clf = LogisticRegression().fit(Xtr, ytr)
        importance = tr.new_signal_importance(clf)
        self.assertEqual(set(importance.keys()), set(tr.NEW_SIGNAL_FEATURES))

    def test_empty_for_model_without_coef(self):
        class NoCoefModel:
            pass
        self.assertEqual(tr.new_signal_importance(NoCoefModel()), {})


class SourceBreakdownTest(unittest.TestCase):
    def test_groups_by_sample_source(self):
        val = [
            {"label": True, "sample_source": "onpolicy"},
            {"label": False, "sample_source": "onpolicy"},
            {"label": True, "sample_source": "dealfeed"},
            {"label": False, "sample_source": "dealfeed"},
        ]
        proba = [0.9, 0.1, 0.8, 0.2]
        out = tr.source_breakdown(val, proba)
        self.assertEqual(set(out.keys()), {"onpolicy", "dealfeed"})
        self.assertEqual(out["onpolicy"]["n"], 2)
        self.assertEqual(out["onpolicy"]["auc"], 1.0)

    def test_missing_sample_source_grouped_as_na(self):
        val = [{"label": True}, {"label": False}]
        out = tr.source_breakdown(val, [0.7, 0.3])
        self.assertEqual(set(out.keys()), {"n/a"})

    def test_single_class_slice_reports_count_only_no_fabricated_auc(self):
        val = [{"label": True, "sample_source": "explore"}, {"label": True, "sample_source": "explore"}]
        out = tr.source_breakdown(val, [0.6, 0.7])
        self.assertEqual(out["explore"]["n"], 2)
        self.assertIsNone(out["explore"]["auc"])


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

    def test_feature_value_change_at_same_identity_busts_fingerprint(self):
        """Review fix (2026-07-06): scout/signals/trends_backfill.py patches features_snapshot
        IN PLACE on the SAME (asin, simulation_date, label) natural key — the original
        identity-only fingerprint was blind to this. A row whose feature VALUES change (same
        identity) must now produce a different fingerprint."""
        row_before = dict(self._row("B001"), features={"price": 20.0, "brand_trend_ratio": None})
        row_after = dict(self._row("B001"), features={"price": 20.0, "brand_trend_ratio": 2.5})
        fp1 = tr.training_set_fingerprint({"rows": [row_before]})
        fp2 = tr.training_set_fingerprint({"rows": [row_after]})
        self.assertEqual(fp1["row_count"], fp2["row_count"])
        self.assertNotEqual(fp1["content_hash"], fp2["content_hash"])

    def test_schema_version_changes_when_numeric_features_change(self):
        """Review fix: a code-side change to NUMERIC_FEATURES (e.g. this session's 10->25
        expansion) must bust the fingerprint even when the underlying rows are byte-identical —
        the model's INPUT SCHEMA changed, which is exactly the kind of change the skip guard
        must not silently ignore."""
        rows = [self._row("B001")]
        fp1 = tr.training_set_fingerprint({"rows": rows})
        with mock.patch.object(tr, "NUMERIC_FEATURES", tr.NUMERIC_FEATURES + ("a_brand_new_feature",)):
            fp2 = tr.training_set_fingerprint({"rows": rows})
        self.assertNotEqual(fp1["schema_version"], fp2["schema_version"])
        self.assertNotEqual(fp1, fp2)

    def test_bronze_count_reflected_and_bumps_fingerprint(self):
        """New operator buy/pass decisions (bronze rows) must also change the fingerprint, even
        though they never enter `rows`/the relevance target — otherwise a week of fresh operator
        decisions leaves bronze_agreement frozen at its last value forever."""
        base = {"rows": [self._row("B001")], "bronze_rows": []}
        with_bronze = {"rows": [self._row("B001")],
                      "bronze_rows": [{"asin": "B002", "label": True, "features": {}}]}
        fp1 = tr.training_set_fingerprint(base)
        fp2 = tr.training_set_fingerprint(with_bronze)
        self.assertEqual(fp1["bronze_count"], 0)
        self.assertEqual(fp2["bronze_count"], 1)
        self.assertNotEqual(fp1, fp2)

    def test_sample_bounded_for_large_corpora(self):
        """A ~50k-row corpus must not hash every row's full feature dict — only a bounded,
        deterministic sample. Just confirms it completes quickly and is still order-stable."""
        import time
        big = [self._row(f"B{i:06d}", sim=f"2026-01-{(i % 28) + 1:02d}") for i in range(20000)]
        for r in big:
            r["features"] = {"price": float(i) for i in range(5)}
        t0 = time.time()
        fp1 = tr.training_set_fingerprint({"rows": big})
        fp2 = tr.training_set_fingerprint({"rows": list(reversed(big))})
        elapsed = time.time() - t0
        self.assertEqual(fp1, fp2)
        self.assertLess(elapsed, 5.0)  # generous ceiling — this must stay "cheap"


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


class MainFingerprintOnFailedUploadTest(unittest.TestCase):
    """Review fix (2026-07-06): a real training run whose artifact upload fails must NOT store
    the fingerprint — doing so would freeze the skip guard believing this data was already
    trained on, while ranker/current/ actually stays stale or missing."""

    def test_fingerprint_not_stored_when_all_uploads_fail(self):
        with mock.patch.object(tr, "build_dataset", return_value={"rows": []}), \
             mock.patch.object(tr, "train_and_evaluate", return_value={
                 "refused": False, "model": object(), "scaler": object(), "features": [],
                 "train_rows": 1, "val_rows": 1, "train_asins": 1, "val_asins": 1, "by_tier": {},
                 "champion": {"auc": None, "winners_in_top": 0, "top_n": 0},
                 "challenger": {"auc": None, "winners_in_top": 0, "top_n": 0},
                 "verdict": "x", "silver_caveat": "", "bronze_agreement": None,
                 "bronze_caveat": "", "by_source": {}, "new_signal_importance": {}}), \
             mock.patch.object(tr, "render_report", return_value="block"), \
             mock.patch.object(tr, "append_report"), \
             mock.patch.object(tr, "fetch_last_fingerprint", return_value=None), \
             mock.patch.object(tr, "save_artifacts", return_value=["model.joblib", "metrics.json"]), \
             mock.patch.object(tr, "upload_to_storage", return_value=0), \
             mock.patch.object(tr, "upload_fingerprint", return_value=True) as mock_upload_fp, \
             mock.patch.object(tr, "post_summary", return_value=True):
            rc = tr.main([])
        self.assertEqual(rc, 0)
        mock_upload_fp.assert_not_called()

    def test_fingerprint_stored_when_upload_succeeds(self):
        with mock.patch.object(tr, "build_dataset", return_value={"rows": []}), \
             mock.patch.object(tr, "train_and_evaluate", return_value={
                 "refused": False, "model": object(), "scaler": object(), "features": [],
                 "train_rows": 1, "val_rows": 1, "train_asins": 1, "val_asins": 1, "by_tier": {},
                 "champion": {"auc": None, "winners_in_top": 0, "top_n": 0},
                 "challenger": {"auc": None, "winners_in_top": 0, "top_n": 0},
                 "verdict": "x", "silver_caveat": "", "bronze_agreement": None,
                 "bronze_caveat": "", "by_source": {}, "new_signal_importance": {}}), \
             mock.patch.object(tr, "render_report", return_value="block"), \
             mock.patch.object(tr, "append_report"), \
             mock.patch.object(tr, "fetch_last_fingerprint", return_value=None), \
             mock.patch.object(tr, "save_artifacts", return_value=["model.joblib", "metrics.json"]), \
             mock.patch.object(tr, "upload_to_storage", return_value=2), \
             mock.patch.object(tr, "upload_fingerprint", return_value=True) as mock_upload_fp, \
             mock.patch.object(tr, "post_summary", return_value=True):
            rc = tr.main([])
        self.assertEqual(rc, 0)
        mock_upload_fp.assert_called_once()

    def test_fingerprint_stored_on_honest_refusal(self):
        """A refusal has no artifacts to upload — storing the fingerprint is still correct so a
        repeated identical refusal also skips next time."""
        with mock.patch.object(tr, "build_dataset", return_value={"rows": []}), \
             mock.patch.object(tr, "train_and_evaluate",
                               return_value={"refused": True, "reason": "not enough data", "by_tier": {}}), \
             mock.patch.object(tr, "render_report", return_value="block"), \
             mock.patch.object(tr, "append_report"), \
             mock.patch.object(tr, "fetch_last_fingerprint", return_value=None), \
             mock.patch.object(tr, "upload_fingerprint", return_value=True) as mock_upload_fp, \
             mock.patch.object(tr, "post_summary", return_value=True):
            rc = tr.main([])
        self.assertEqual(rc, 0)
        mock_upload_fp.assert_called_once()


if __name__ == "__main__":
    unittest.main()
