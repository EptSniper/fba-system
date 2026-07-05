"""
test_eval_retrieval.py — the retrieval eval's pure logic (DATA_ENGINE_PLAN.md V1).

Tests the metric functions, doc-id extraction, the BM25 baseline on a tiny fixture, and the
per-category aggregation — none of which need fastembed, a model download, or Supabase. The
heavy bge/Supabase paths are integration-only (exercised by running eval_retrieval.py itself).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import eval_retrieval as er  # noqa: E402


class MetricsTest(unittest.TestCase):
    def test_recall_at_k(self):
        ranked = ["doc_a", "doc_b", "doc_c", "doc_d", "doc_e"]
        self.assertEqual(er.recall_at_k(ranked, ["doc_c"], 5), 1.0)
        self.assertEqual(er.recall_at_k(ranked, ["doc_c"], 2), 0.0)  # doc_c is at rank 3
        self.assertEqual(er.recall_at_k(ranked, ["doc_zzz"], 5), 0.0)
        self.assertEqual(er.recall_at_k(ranked, ["doc_zzz", "doc_b"], 5), 1.0)  # any-match

    def test_reciprocal_rank(self):
        ranked = ["doc_a", "doc_b", "doc_c"]
        self.assertEqual(er.reciprocal_rank(ranked, ["doc_a"]), 1.0)
        self.assertAlmostEqual(er.reciprocal_rank(ranked, ["doc_b"]), 0.5)
        self.assertAlmostEqual(er.reciprocal_rank(ranked, ["doc_c"]), 1.0 / 3)
        self.assertEqual(er.reciprocal_rank(ranked, ["nope"]), 0.0)

    def test_doc_id_of(self):
        self.assertEqual(er.doc_id_of({"document_id": "doc_x"}), "doc_x")
        self.assertEqual(er.doc_id_of({"id": "doc_y::7"}), "doc_y")  # parse from chunk id
        self.assertEqual(er.doc_id_of({"id": "doc_z"}), "doc_z")
        self.assertIsNone(er.doc_id_of({}))

    def test_tokenize(self):
        self.assertEqual(er.tokenize("Keepa BSR, 90-day!"), ["keepa", "bsr", "90", "day"])


class BM25FixtureTest(unittest.TestCase):
    def setUp(self):
        self.chunks = [
            {"id": "doc_keepa::0", "document_id": "doc_keepa",
             "chunk_text": "Read the Keepa chart: 90-day price history, sales rank drops, offer count."},
            {"id": "doc_ungate::0", "document_id": "doc_ungate",
             "chunk_text": "To get ungated, submit invoices from an approved distributor in Seller Central."},
            {"id": "doc_fees::0", "document_id": "doc_fees",
             "chunk_text": "Amazon referral fees vary by category; FBA fulfillment fees depend on size and weight."},
        ]
        self.bm25 = er.build_bm25(self.chunks)

    def test_bm25_ranks_relevant_doc_first(self):
        ranked = er.bm25_rank(self.bm25, self.chunks, "how do I read a keepa chart", k=3)
        self.assertEqual(ranked[0], "doc_keepa")
        ranked2 = er.bm25_rank(self.bm25, self.chunks, "how to get ungated with invoices", k=3)
        self.assertEqual(ranked2[0], "doc_ungate")

    def test_evaluate_aggregates_per_category(self):
        pairs = [
            {"id": "q1", "question": "read the keepa chart", "expected_doc_ids": ["doc_keepa"], "category": "Keepa"},
            {"id": "q2", "question": "ungating invoices seller central", "expected_doc_ids": ["doc_ungate"], "category": "Compliance"},
        ]
        res = er.evaluate(pairs, lambda q, k: er.bm25_rank(self.bm25, self.chunks, q, k), k=3)
        self.assertEqual(res["n"], 2)
        self.assertEqual(res["recall_at_k"], 1.0)
        self.assertIn("Keepa", res["per_category"])
        self.assertIn("Compliance", res["per_category"])
        self.assertEqual(res["per_category"]["Keepa"]["n"], 1)


class ReportRenderTest(unittest.TestCase):
    def test_report_flags_bm25_beating_bge(self):
        results = {
            "bge (local)": {"recall_at_k": 0.5, "mrr": 0.4, "n": 2,
                            "per_category": {"Keepa": {"recall": 0.2, "rr": 0.2, "n": 1}}},
            "BM25": {"recall_at_k": 0.8, "mrr": 0.7, "n": 2,
                     "per_category": {"Keepa": {"recall": 0.9, "rr": 0.8, "n": 1}}},
        }
        md = er.render_report(5, results, {}, 2)
        self.assertIn("CHUNKING", md)  # honest chunking flag fires when BM25 wins
        self.assertIn("recall@5", md)

    def test_report_notes_unavailable_systems(self):
        results = {"BM25": {"recall_at_k": 0.8, "mrr": 0.7, "n": 1, "per_category": {}}}
        md = er.render_report(5, results, {"bge (supabase)": "not reachable here"}, 1)
        self.assertIn("bge (supabase)", md)
        self.assertIn("not reachable here", md)


class PairsFileTest(unittest.TestCase):
    def test_pairs_file_is_valid_and_substantial(self):
        pairs = er.load_jsonl(er.PAIRS)
        self.assertGreaterEqual(len(pairs), 40)  # plan: ~40 pairs
        for p in pairs:
            self.assertIn("question", p)
            self.assertTrue(p.get("expected_doc_ids"))
            self.assertTrue(all(d.startswith("doc_") for d in p["expected_doc_ids"]))
            self.assertIn("why", p)  # each pair cites why that doc is the answer


if __name__ == "__main__":
    unittest.main()
