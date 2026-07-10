# Hybrid Search for RAG: Vector + Keyword + Reranking Guide 2026

- **Source:** https://www.buildmvpfast.com/blog/hybrid-search-rag-vector-keyword-reranking-2026
- **Author/date:** Umapathy A / BuildMVPFast, published & updated 2026-03-28
- **Fetched:** 2026-07-07
- **Topic:** build_the_system
- **Classification:** [practitioner] (engineering blog; benchmarks cited from Weaviate/BEIR)

## Why it matters for this project
`knowledge-rag` runs on Supabase/Postgres + pgvector. This is a concrete, Postgres-native upgrade path
(pgvector + ParadeDB `pg_search` BM25 + RRF + cross-encoder rerank) if Ask/scout retrieval quality needs a
lift. Staged, not implemented.

## Key takeaways
1. **Keyword blindness of pure vector search.** Vector search captures meaning but fails on exact-match
   tokens — error codes (`ERR_SSL_PROTOCOL_ERROR`), SKUs (`WX-4200`), acronyms (`GAN`), names, code
   identifiers. One team saw ~35% of support queries contain an exact identifier vector search missed.
2. **BM25 is still essential.** 30-year-old term-frequency/IDF algorithm; fast, interpretable, crushing on
   exact terms. `BM25(D,Q)=Σ IDF(q)·[TF(q,D)(k1+1)]/[TF(q,D)+k1(1-b+b·|D|/avgdl)]`, k1≈1.2, b≈0.75.
3. **Merge with Reciprocal Rank Fusion (RRF).** `RRF(d)=Σ 1/(k+rank(d))`, k≈60. Rank-based, so it avoids the
   fragile job of normalizing BM25 vs cosine scores. Native in Elasticsearch/OpenSearch/Azure AI Search.
   Weighted alternative `H=(1-α)·keyword+α·vector` (α=0.7/0.3 common) needs score normalization first.
4. **Reranking is the layer most teams skip.** Cross-encoder scores (query, doc) pairs; too slow for full
   corpus, so retrieve broad (top 20-50) then rerank to top 5-10. Weaviate/BEIR: Success@1 0.43→0.52,
   Recall@5 0.70→0.81, nDCG@10 0.61→0.70; BRIGHT Biology nDCG@10 0.13→0.40.
5. **Postgres-native hybrid:** pgvector (dense) + ParadeDB `pg_search` (BM25), merged manually with RRF —
   stay in Postgres, no second datastore. (Weaviate is the fastest managed path if not on Postgres.)
6. **Reranker options (Agentset.ai leaderboard, early 2026):** ZeroEntropy zerank-2 (ELO 1638, 265ms,
   $0.025/1M), Cohere Rerank 4 Pro (1629, 614ms, $0.050), Voyage 2.5, self-hosted Qwen3-8B / BGE-v2-M3;
   `ms-marco-MiniLM-L-6-v2` runs <50ms on CPU free for prototypes.
7. **Full pipeline:** Query → [expansion?] → BM25 top20 + vector top20 → RRF merge top30 → rerank top5-10 →
   LLM. Added latency ~200-400ms; per-query cost ~$0.001-0.005 managed, ~0 self-hosted.
8. **Production gotchas:** normalize scores before weighted blending; uniform ~500-token chunks kill BM25
   length normalization (enrich chunks with section/parent titles); adjust weights by query intent
   (keyword for identifiers, vector for NL questions); rerank 20-50 candidates (not 5, not 200).
