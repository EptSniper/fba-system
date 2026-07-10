# ProductResearch: Training E-Commerce Deep Research Agents via Multi-Agent Synthetic Trajectory Distillation (arXiv 2602.23716)

- **URL:** https://arxiv.org/abs/2602.23716 (fetched via https://arxiv.org/html/2602.23716v1)
- **Date fetched:** 2026-07-06 (v1 dated Feb 27, 2026)
- **Authors:** Wang, Xiao, Zhao, Luo, Zeng — Alibaba International Digital Commerce Group
- **Type:** [practitioner] — industry research paper
- **Topic:** build_the_system

## Content (condensed)

Problem: the "Deep Research" paradigm (long-horizon search + synthesis) does NOT transfer cleanly to
e-commerce — complex shopping inquiries need open-web knowledge PLUS structured product-catalog querying,
claims grounded in verified product attributes, and synthesis of heterogeneous evidence (expert reviews,
user feedback, specs). Deep-research models tuned for web search lack robustness for broader tool use.

Framework — three agents:
1. **User Agent** — from real behavioral histories, infers a persona, a complex research query, AND a
   query-adaptive evaluation rubric (weights over comprehensiveness / depth / instruction-following /
   readability). Rubric-per-query, not one global metric.
2. **Research Agent** — ReAct loop with a Plan → Toolcall → Report schema over a dual toolset: open web +
   internal product catalog.
3. **Supervisor Agent** — a three-stage state machine doing STEP-LEVEL verification of every plan, tool
   call, and report section; detects hallucination, logic drift, and insufficient evidence coverage and
   sends targeted corrective feedback (iterative loop until approved).

Approved trajectories go through "reflective internalization": multi-agent supervisory interactions are
distilled into coherent single-role training examples so corrective signals survive into plain SFT data.

Results: fine-tuning a compact MoE (Qwen3-30B-A3B) on the synthetic trajectories lifts overall RACE score
31.78 → 45.40 and effective product coverage 3.58 → 12.45 (>3×), approaching frontier proprietary
deep-research systems.

## Why it matters for this project

- Direct evidence for the scout_pro thesis: product research quality comes from BLENDING web evidence with
  structured catalog data (our Keepa/SP-API side), not from web search alone.
- The Supervisor state machine (verify plan → verify tool call → verify report, with targeted feedback) is
  a cheap, implementable pattern for the scout's lead reports and for Ask answer QA — verification at each
  step instead of one end-of-pipeline check.
- Rubric-per-query generation is a concrete idea for evaluating Ask answers (matches the RAG-evaluation
  survey 2504.14891 already staged).
