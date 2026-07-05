# Scaling Retrieval Augmented Generation with RAG Fusion: Lessons from an Industry Deployment (arXiv 2603.02153)

- **URL:** https://arxiv.org/abs/2603.02153
- **Published:** 2026-03-02 (Medrano, Verma, Chhabra — Dell Technologies)
- **Fetched:** 2026-07-04 — NOTE: arXiv PDF returned no machine-readable text this run; findings staged from the abstract/listing + search snippets. Read the PDF before acting on details.
- **Type:** [practitioner] — industry research paper (production deployment evidence)
- **Topic:** build_the_system

## Distilled content

**Question:** do the popular retrieval-fusion techniques — multi-query retrieval (rewriting the user query into variants) and reciprocal rank fusion (RRF) — actually improve production RAG?

**Finding (production system, Dell):** fusion DOES increase raw recall, but the gains are **largely neutralized after reranking and truncation**. Fusion variants failed to outperform single-query baselines on KB-level Top-k accuracy — Hit@10 *decreased* from 0.51 to 0.48 in several configurations.

**Cost:** fusion adds real latency overhead (query rewriting round-trip + larger candidate sets to score) without corresponding downstream gains.

**Implication for knowledge-rag:** if a reranker is (or will be) in the chain, single-query retrieval + rerank may dominate multi-query + RRF on both quality and latency. Do NOT add multi-query fusion by default; A/B it behind the retrieval-aware eval harness (see staged arXiv 2504.14891) before adopting. Pairs with the staged 2407.01219 advice: benchmark every added pipeline step against latency.
