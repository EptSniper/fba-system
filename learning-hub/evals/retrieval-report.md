# Retrieval eval — recall@5 + MRR (DATA_ENGINE_PLAN.md V1)

**Pairs:** 41 (learning-hub/evals/retrieval/pairs.jsonl). Metrics are at the retrieved-chunk level: a pair is a hit if any of the top-5 chunks belongs to an expected document; MRR uses the first such chunk's rank.

## Overall

| System | recall@5 | MRR |
|---|---|---|
| BM25 | 0.561 | 0.338 |
| bge (local) | 0.683 | 0.527 |
| bge (supabase) | 0.683 | 0.527 |

## Per-category recall@5

| Category | BM25 | bge (local) | bge (supabase) |
|---|---|---|---|
| AI system | 0.50 (n=8) | 0.75 (n=8) | 0.75 (n=8) |
| Compliance | 0.83 (n=6) | 1.00 (n=6) | 1.00 (n=6) |
| Fundamentals | 0.20 (n=5) | 0.60 (n=5) | 0.60 (n=5) |
| Keepa | 0.75 (n=4) | 0.50 (n=4) | 0.50 (n=4) |
| Operations | 0.40 (n=5) | 0.80 (n=5) | 0.80 (n=5) |
| Research | 1.00 (n=3) | 1.00 (n=3) | 1.00 (n=3) |
| SellerAmp | 0.67 (n=3) | 0.33 (n=3) | 0.33 (n=3) |
| Sourcing methods | 0.67 (n=3) | 0.33 (n=3) | 0.33 (n=3) |
| Sourcing rules | 0.25 (n=4) | 0.50 (n=4) | 0.50 (n=4) |

## Honest read

⚠ BM25 beats bge in: Keepa (BM25 0.75 > bge 0.50); SellerAmp (BM25 0.67 > bge 0.33); Sourcing methods (BM25 0.67 > bge 0.33). Per the corpus's own RAG research (rag-chunking-strategies-databricks, rag-best-practices), the FIRST suspect is CHUNKING (chunks too small/large or split mid-idea), not the model.

_Regenerate: `python knowledge-rag/eval_retrieval.py`._