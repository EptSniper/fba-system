# Retrieval Augmented Generation Evaluation in the Era of Large Language Models: A Comprehensive Survey (arXiv 2504.14891)

- **URL:** https://arxiv.org/abs/2504.14891
- **Fetched:** 2026-07-02 (submitted 2025-04-21; Gan, Yu, Zhang, Liu, Yan, Huang, Tong, Hu — 18 pp, cs.CL, CC BY 4.0)
- **Type:** [practitioner] — peer-style research survey (preprint)
- **Topic:** build_the_system (RAG evaluation)

## Abstract (verbatim)

Recent advancements in Retrieval-Augmented Generation (RAG) have revolutionized natural language
processing by integrating Large Language Models (LLMs) with external information retrieval, enabling
accurate, up-to-date, and verifiable text generation across diverse applications. However, evaluating RAG
systems presents unique challenges due to their hybrid architecture that combines retrieval and generation
components, as well as their dependence on dynamic knowledge sources in the LLM era. In response, this
paper provides a comprehensive survey of RAG evaluation methods and frameworks, systematically reviewing
traditional and emerging evaluation approaches, for system performance, factual accuracy, safety, and
computational efficiency in the LLM era. We also compile and categorize the RAG-specific datasets and
evaluation frameworks, conducting a meta-analysis of evaluation practices in high-impact RAG research. To
the best of our knowledge, this work represents the most comprehensive survey for RAG evaluation, bridging
traditional and LLM-driven methods, and serves as a critical resource for advancing RAG development.

## Why staged

The knowledge-rag `Ask` pipeline currently has no formal evaluation harness. This survey is the reference
catalog for choosing one: it separates **retrieval-component metrics** from **generation/grounding
metrics** (the exact split the project's guardrails demand — retrieval-aware evaluation + citation checks,
not just answer accuracy), and catalogs RAG-specific datasets/frameworks (e.g. ARES-style automated
evaluation) worth borrowing from when building a small eval set over the FBA corpus. Full PDF:
https://arxiv.org/pdf/2504.14891 — read before implementing an eval harness.
