# A Hybrid Retrieval and Reranking Framework for Evidence-Grounded Retrieval-Augmented Generation (arXiv 2605.01664)

- **URL:** https://arxiv.org/abs/2605.01664 (HTML: https://arxiv.org/html/2605.01664v1)
- **Fetched:** 2026-07-04 (HTML version read in part; abstract + evaluation design distilled)
- **Type:** [practitioner] — research paper (biomedical document QA case study)
- **Topic:** build_the_system

## Distilled content

**Pipeline:** citation-aware RAG for biomedical/healthcare document QA on AWS managed services — Amazon Bedrock Knowledge Bases for ingestion/parsing/chunking, Titan Text Embeddings V2, OpenSearch Serverless index, **hybrid retrieval → Cohere reranking** to prioritize evidence before generation.

**The reusable part — the grounding-evaluation design (relevant to Ask):**
- A **separate LLM judge** (distinct from the generator) verifies whether each generated claim is supported by the retrieved evidence — generator answers, judge only verifies; separation reduces evaluation bias.
- **Claim-level binary support decisions** with structured output: supported yes/no + which source(s) + brief explanation → enables claim-level, query-level, and overall grounding-accuracy metrics.
- **Conservative rubric:** the judge is forbidden outside knowledge; vague, indirect, incomplete, or partially-relevant evidence = UNSUPPORTED. Avoids overestimating grounding.
- Every intermediate output (retrieved chunks, reranked chunks, answers, claim judgments, per-query accuracy) stored as structured CSVs for inspection/reproducibility.

**Result:** 100% overall grounding accuracy, 25 of 25 queries — a very small eval set; the number is not the takeaway, the **auditable claim-level grounding harness** is. It matches this project's honest-citation guardrail and could back a "grounding check" behind Ask's answers.
