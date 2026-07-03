import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("knowledge_ask", ROOT / "ask.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def row(text, citation, similarity=0.65, category="Fundamentals"):
    return {
        "id": citation,
        "chunk_text": text,
        "citation": citation,
        "category": category,
        "similarity": similarity,
    }


class AnsweringTests(unittest.TestCase):
    def test_rerank_prefers_structured_playbook_over_raw_transcript(self):
        rows = [
            row("Offer count rising is a warning because competition is increasing.",
                "learning-hub/transcripts/raw-video.txt", 0.70, "Transcripts"),
            row("Rising offer count is an instant-reject red flag because price compression is likely.",
                "learning-hub/playbooks/sourcing-playbook.md", 0.67, "Arbitrage decision rules"),
        ]
        ranked = MODULE.rerank(rows, "Why is rising offer count a red flag?", limit=2)
        self.assertIn("playbooks/", ranked[0]["citation"])

    def test_rerank_deduplicates_identical_chunks(self):
        duplicate = row("Stable price and falling offer count are healthier signals for an OA deal.",
                        "learning-hub/playbooks/a.md")
        ranked = MODULE.rerank([duplicate, dict(duplicate)], "What are healthy deal signals?", limit=6)
        self.assertEqual(len(ranked), 1)

    def test_synthesis_returns_concise_cited_points(self):
        rows = MODULE.rerank([
            row("Use the 90-day and one-year Keepa views together. Rising offers while price falls is a price-war warning.",
                "learning-hub/playbooks/sourcing-playbook.md", 0.76),
            row("Confirm the lowest historical price still leaves enough margin after every fee and landed cost.",
                "learning-hub/ai-system/product-research-template.md", 0.72),
        ], "How should I read Keepa before buying?", limit=6)
        answer = MODULE.synthesize("How should I read Keepa before buying?", rows)
        self.assertTrue(answer["points"])
        self.assertTrue(all(point["citation"] for point in answer["points"]))
        self.assertLessEqual(len(answer["points"]), 4)
        self.assertEqual(answer["method"], "zero-cost extractive synthesis")

    def test_policy_question_gets_account_specific_caveat(self):
        rows = MODULE.rerank([
            row("Eligibility is account-specific and must be checked for the exact ASIN and condition.",
                "learning-hub/playbooks/ungating-playbook.md", 0.73),
        ], "Am I eligible and allowed to sell this gated ASIN?", limit=6)
        answer = MODULE.synthesize("Am I eligible and allowed to sell this gated ASIN?", rows)
        self.assertIn("Seller Central", answer["caveat"])

    def test_common_buy_question_uses_current_maintained_rules(self):
        answer = MODULE.synthesize("What makes an OA product safe and profitable?", [])
        combined = " ".join(point["text"] for point in answer["points"])
        self.assertIn("30% ROI", combined)
        self.assertIn("$3 profit", combined)
        self.assertIn("account eligibility", combined)
        self.assertEqual(answer["evidence_strength"], "strong")


if __name__ == "__main__":
    unittest.main()
