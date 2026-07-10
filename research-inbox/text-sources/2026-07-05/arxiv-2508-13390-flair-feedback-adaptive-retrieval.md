# FLAIR: Feedback Learning for Adaptive Information Retrieval (arXiv 2508.13390)

- **URL:** https://arxiv.org/abs/2508.13390 (fetched via https://arxiv.org/pdf/2508.13390)
- **Date fetched:** 2026-07-05
- **Authors:** Zhang (CMU) + Microsoft team (Wang, Zhu, Deng, Cilimdzic, Krishnan, Lu, Demarne, Sahoo, Lin)
- **Type:** [practitioner] — industry paper; deployed in Microsoft Copilot DECO serving thousands of users
- **Topic:** build_the_system

## Content (condensed)

FLAIR is a **lightweight feedback-learning framework that adapts a copilot's retrieval strategy using
domain-expert feedback** — i.e., a concrete recipe for the "self-learning RAG" goal of this project.

### Architecture (two stages)
- **Offline phase:** collect *indicators* from (1) explicit user feedback and (2) questions
  synthesized from the documentation itself; store indicators in a decentralized way (per-document,
  not one big model).
- **Online phase:** a **two-track ranking mechanism** combines raw embedding-similarity scores with
  the collected feedback indicators at query time. The loop iterates, so retrieval keeps improving
  for both previously seen AND unseen queries.

### Reported results
Significant retrieval-quality gains over state-of-the-art baselines on seen and unseen queries in
real-world evaluation; integrated into Copilot DECO at Microsoft — evidence the pattern scales
operationally, not just in benchmarks.

### Why relevant to this project
- Maps directly onto the planned outcome-feedback loop: operator buy/no-buy decisions and Ask
  thumbs-up/down are exactly the "domain-specific expert feedback" FLAIR consumes.
- The synthetic-questions trick (generate Q's from corpus docs offline) is cheap to replicate for the
  knowledge-rag corpus to bootstrap indicators before real usage data exists.
- Two-track ranking (similarity + feedback indicators) is an incremental, low-risk upgrade path for
  match_chunks — it augments rather than replaces vector search, aligning with the project's
  hard-gate/honesty rules (raw similarity remains inspectable).
