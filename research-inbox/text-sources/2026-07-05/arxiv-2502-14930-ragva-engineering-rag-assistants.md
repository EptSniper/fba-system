# RAGVA: Engineering Retrieval Augmented Generation-based Virtual Assistants in Practice (arXiv 2502.14930)

- **URL:** https://arxiv.org/abs/2502.14930 (fetched via https://arxiv.org/pdf/2502.14930)
- **Date fetched:** 2026-07-05 (preprint dated Feb 2025, submitted to Journal of Systems and Software)
- **Authors:** Yang, Fu, Tantithamthavorn, Arora, Vandenhurk, Chua (Monash / U. Melbourne / Transurban)
- **Type:** [practitioner] — industry experience report (Transurban engineering team + focus group of 9)
- **Topic:** build_the_system

## Content (condensed)

Experience report on replacing a rule-based virtual assistant with a RAG-based one (RAGVA) at
Transurban (world's largest toll-road operator). Contributions: a step-by-step guide for building a
conversational RAG application, an engineering framework covering implementation → testing, and
**eight challenges + 22 research questions** from a multi-day practitioner focus group.

### Why relevant to this project
The knowledge-rag + control-center "Ask" feature *is* a small RAGVA. The eight challenges map almost
one-to-one onto this project's risk register.

### The eight engineering challenges (focus-group findings)
1. **Multi-modal data engineering** — scoping use cases and document requirements; handling
   large-scale, mixed-format source data.
2. **Adaptive security guardrails** — protecting sensitive input/output around the LLM.
3. **Managing/operating the latest LLMs** — post-deployment maintenance; model churn is a
   maintenance burden (LLM component swaps behave unpredictably).
4. **Balancing relevancy vs conciseness** of generated responses — fine-grained verbosity tuning is
   a real hyperparameter search, not a one-off prompt tweak.
5. **Automated testing for RAG systems** — generating test inputs AND a test oracle/benchmark is an
   open problem; continuous validation replaces the traditional spec-based test plan.
6. **Comprehensive, systematic evaluation metrics** — beyond spot checks: hallucination,
   faithfulness, contextual precision/recall, knowledge retention.
7. **Analysing + incorporating human feedback for continuous improvement at scale** — which usage
   interaction data to collect for analytics; how to close the loop from user feedback to retrieval
   and prompt improvements.
8. **Responsible AI for RAG systems** — RAI frameworks specific to RAG (bias, toxicity, provenance).

Key stance: unlike traditional software, RAG apps have nondeterministic components, so behavior can't
be fully specified up front — they need **continuous validation and adaptive development strategies**.
