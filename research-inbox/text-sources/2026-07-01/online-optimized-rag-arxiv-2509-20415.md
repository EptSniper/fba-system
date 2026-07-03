# Online-Optimized RAG for Tool Use and Function Calling (arXiv:2509.20415)

- **Source:** https://arxiv.org/abs/2509.20415 (fetched via https://arxiv.org/html/2509.20415v1)
- **Authors:** Pan, Wang, et al. (Univ. of Sydney), 2025
- **Fetched:** 2026-07-01
- **Classification:** [practitioner] — research paper (method proposal, not Amazon policy). Directly relevant to the project's "self-learning scout / RAG" goal.

## Distilled takeaways

- **[practitioner]** The paper targets **embedding misalignment** in RAG-driven tool/function selection — when imperfect embedding models or noisy descriptions cause the retriever to fetch the wrong tool/doc and the task fails. This is exactly the failure mode a self-learning scout/RAG faces as the corpus and product mix drift.
- **[practitioner]** **Online-Optimized RAG** adapts retrieval embeddings *at deployment time* from live interactions using **minimal feedback (e.g., task success / failure)** — no labeled dataset and **no change to the underlying LLM**. Maps cleanly onto learning from realized buy/no-buy **outcomes** rather than retraining offline.
- **[practitioner]** Updates are **lightweight online gradient steps with negligible per-query latency**, and the method is plug-and-play: supports single- and multi-hop tool use, **dynamic tool inventories**, and **top-K retrieval with re-ranking**. Useful pattern if the scout's retrievable set changes over time.
- **[practitioner]** Their theory ties performance to **embedding initialization quality** — i.e. start from a decent embedding model; online adaptation compensates for drift but doesn't rescue a bad base. Reinforces "benchmark the base retriever first," consistent with the RAG best-practices paper ingested 2026-06-30.
- **[practitioner]** Caveat before adopting: gains are shown on tool-use / document-retrieval benchmarks (UltraTool, ToolRet, FiQA), not on FBA data. Treat as a candidate pattern to A/B behind retrieval-aware eval + grounding/citation checks (per the project's honesty rules), not a drop-in.
