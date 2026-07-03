# Retrieval-Augmented Generation: A Comprehensive Survey of Architectures, Enhancements, and Robustness Frontiers (arXiv 2506.00054)

- **Source URL:** https://arxiv.org/abs/2506.00054
- **Author:** Chaitanya Sharma
- **Submitted:** 2025-05-28 (cs.IR / cs.CL)
- **Fetched:** 2026-06-30 (abstract page)
- **Classification:** [practitioner] — survey of research; evidence, not Amazon policy
- **Topic:** build_the_system

## Distilled takeaways

1. **[practitioner]** RAG fixes parametric-memory weaknesses (factual inconsistency, domain inflexibility) but
   introduces its own failure modes: **retrieval quality, grounding fidelity, pipeline efficiency, and
   robustness to noisy/adversarial inputs.** These map onto the project's stated leakage/honesty risks for
   `Ask`. (arxiv.org/abs/2506.00054)
2. **[practitioner]** Architectures cluster into **retriever-centric, generator-centric, hybrid, and
   robustness-oriented** designs. Enhancements span retrieval optimization, **context filtering**, decoding
   control, and efficiency — a checklist for evaluating the current `knowledge-rag` design.
3. **[practitioner]** Recurring trade-offs to design around: **retrieval precision vs generation flexibility,
   efficiency vs faithfulness, modularity vs coordination.** Worth stating explicitly when choosing settings
   so the control-center doesn't optimize one at the silent expense of another.
4. **[practitioner]** Prioritize **retrieval-aware evaluation and robustness testing** (not just end-answer
   accuracy) — argues for grounding/citation checks in `Ask`, consistent with the "honest empty states" rule.
5. **Open directions noted:** adaptive retrieval, real-time retrieval integration, multi-hop structured
   reasoning, privacy-preserving retrieval — candidate roadmap items for `fba-innovator` to weigh later.
