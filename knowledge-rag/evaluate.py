"""Run the live, zero-cost answer quality gate against maintained OA expectations."""
import json
from pathlib import Path

from ask import _retrieval_question, rerank, retrieve, synthesize


ROOT = Path(__file__).resolve().parent
CASES = ROOT / "evals" / "questions.json"


def evaluate_case(case):
    rows = retrieve(_retrieval_question(case["question"]), k=12)
    ranked = rerank(rows, case["question"], limit=12)
    answer = synthesize(case["question"], ranked)
    answer_text = " ".join(point["text"] for point in answer["points"]).lower()
    citations = " ".join(point["citation"] for point in answer["points"]).lower()
    missing_terms = [term for term in case["required_terms"] if term.lower() not in answer_text]
    missing_sources = [source for source in case["citation_contains"] if source.lower() not in citations]
    return {
        "id": case["id"],
        "passed": bool(answer["points"]) and not missing_terms and not missing_sources,
        "point_count": len(answer["points"]),
        "evidence_strength": answer["evidence_strength"],
        "missing_terms": missing_terms,
        "missing_sources": missing_sources,
    }


def main():
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    results = [evaluate_case(case) for case in cases]
    passed = sum(result["passed"] for result in results)
    print(json.dumps({"passed": passed, "total": len(results), "results": results}, indent=2, ensure_ascii=False))
    raise SystemExit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
