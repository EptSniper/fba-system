# Enhancing Retrieval-Augmented Generation: A Study of Best Practices (arXiv 2501.07391)

- **URL:** https://arxiv.org/abs/2501.07391
- **Date fetched:** 2026-07-03 (submitted 2025-01-13; Li, Stenzel, Eickhoff, Bahrainian — cs.CL/cs.AI)
- **Class:** [practitioner/research] — peer-style empirical study; abstract-level capture, read the PDF before implementing.

## Abstract (verbatim)

Retrieval-Augmented Generation (RAG) systems have recently shown remarkable advancements by integrating retrieval mechanisms into language models, enhancing their ability to produce more accurate and contextually relevant responses. However, the influence of various components and configurations within RAG systems remains underexplored. A comprehensive understanding of these elements is essential for tailoring RAG systems to complex retrieval tasks and ensuring optimal performance across diverse applications. In this paper, we develop several advanced RAG system designs that incorporate query expansion, various novel retrieval strategies, and a novel Contrastive In-Context Learning RAG. Our study systematically investigates key factors, including language model size, prompt design, document chunk size, knowledge base size, retrieval stride, query expansion techniques, Contrastive In-Context Learning knowledge bases, multilingual knowledge bases, and Focus Mode retrieving relevant context at sentence-level. Through extensive experimentation, we provide a detailed analysis of how these factors influence response quality. Our findings offer actionable insights for developing RAG systems, striking a balance between contextual richness and retrieval-generation efficiency, thereby paving the way for more adaptable and high-performing RAG frameworks in diverse real-world scenarios. Our code and implementation details are publicly available.

## Why staged

Systematic ablation of the exact knobs `knowledge-rag` exposes (chunk size, KB size, prompt design, query expansion, sentence-level "Focus Mode" retrieval) — complements the already-staged chunking guide (Databricks), best-practices search (2407.01219), eval survey (2504.14891), and online-optimized retrieval (2509.20415). PDF: https://arxiv.org/pdf/2501.07391
