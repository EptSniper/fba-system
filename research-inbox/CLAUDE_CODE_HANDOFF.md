# Claude Code — daily research handoff

**This is the one file Claude Code should read every session.** A scheduled Cowork task
(`fba-daily-research`, ~7 AM daily) discovers new Amazon FBA/OA + system-building material, ingests text
sources, and **queues YouTube videos that it cannot transcribe itself** (the Cowork app can't call the
transcript API — you can). This file is rewritten by that task each run with what's pending and what it found.

Last updated by the scheduled task: 2026-07-10

---

## STANDING DAILY ACTIONS (do these when you open the project)

1. **Pull queued transcripts:** run `python knowledge-rag/fetch_transcripts.py` — it reads all
   `research-inbox/queue/*.json` items with `status:"queued"`, calls youtube-transcript.io with the key in
   `knowledge-rag/.env`, writes transcripts to `research-inbox/transcripts/`, and marks items `done`.
2. **Ingest new transcripts:** for each new `.txt`/`.md` in `research-inbox/transcripts/` (not under
   `processed/`), follow the `fba-transcript-ingest` skill — distill cited takeaways into
   `research-inbox/research-insights.md`, append a JSON line to `research-inbox/corpus-staging.jsonl`,
   update `research-inbox/research-manifest.json` (status → `transcript-processed`), then MOVE the file to
   `research-inbox/transcripts/processed/`.
3. **Periodically merge reviewed staged insights** into `learning-hub/` and run the real `knowledge-rag`
   ingestion/embedding pipeline so Ask/scout/control-center get smarter. This is a REVIEWED merge, not an
   auto-dump — read the staged entries first, keep [policy]/[practitioner] labels and citations.
4. **Use the skills:** consult `SKILLS_INDEX.md` before any task and use the matching `fba-` skill
   (fba-transcript-ingest for ingestion, fba-brain-updater if a finding should change a buying threshold,
   etc.).
5. **Post the Discord update** after finishing the above: send a short summary via the webhook URL stored
   as `RESEARCH_DISCORD_WEBHOOK_URL` in `knowledge-rag/.env` (read the env var directly; NEVER print or
   paste the URL value anywhere, including here). Summarize: new items found by today's scheduled run,
   transcripts fetched/ingested since the last update, and current local-corpus vs live-Supabase
   document/chunk counts if they differ. Use the batched-digest pattern.
6. **Never** print/commit `knowledge-rag/.env` or any key; cite sources; no auto-buy.

## PENDING NOW

- **YouTube videos still `queued` across all `queue/*.json`: 1.** Pull with:
  `python knowledge-rag/fetch_transcripts.py`

  | videoId | title | queue file |
  | --- | --- | --- |
  | -Rv5hejVnVs | The FASTEST Way Find Online Arbitrage Products for Amazon FBA (2026) | queue/2026-07-10.json |

  After pulling, ingest the resulting transcript (STANDING ACTION 2) and flip the manifest item
  `queued → transcript-processed`.
  (The three 2026-07-09-queued videos — Tcd4jAkOi6Q, FRK7JY7_EJY, ctwXY3Vwy8o — were already pulled +
  ingested by Claude Code earlier on 2026-07-10; see the 2026-07-10 Claude Code entry in research-insights.md.)

- **Unprocessed files in `research-inbox/transcripts/` (root): 0.** Only `README.md` remains; everything
  else is in `processed/`.

**Re-fetch in a real browser (fetch-failed/pending from the sandbox — new this run + carried forward):**
- **NEW:** https://sellercentral.amazon.com/help/hub/reference/external/G200213130 — *FBA inventory
  reimbursement policy* (authoritative [policy] doc behind the cost-based reimbursement + ~60d claim
  windows summarized this run from SPS Commerce). JS shell only in sandbox — confirm exact windows +
  IDR-portal mechanics.
- **NEW:** https://arxiv.org/abs/2603.07379 — *SoK: Agentic RAG — Taxonomy, Architectures, Evaluation,
  Research Directions*. Systematization survey; on-thread for scout/knowledge-rag agentic design.
- **NEW:** https://arxiv.org/abs/2606.04435 — *CHARM: Cascading Hallucination in Agentic RAG*. Detection +
  mitigation; relevant to Ask honesty / no-fabrication guardrail.
- **NEW:** https://arxiv.org/abs/2604.00865 — *Doctor-RAG: Failure-Aware Repair for Agentic RAG*. Pairs
  with the self-improving-RAG line (FLAIR 2508.13390, ROZA 2604.07595).
- https://arxiv.org/abs/2604.14572 — *Don't Retrieve, Navigate: Distilling Enterprise Knowledge into
  Navigable Agent Skills* (skills-as-knowledge; carried from 07-09).
- https://arxiv.org/abs/2603.04549 — *Adaptive Memory Admission Control for LLM Agents* (carried).
- https://arxiv.org/abs/2605.12061 — *SAGE: Self-Evolving Agentic Graph-Memory Engine* (carried).
- https://arxiv.org/abs/2606.19847 — *AtomMem: Memory via Atomic Facts* (carried).
- https://arxiv.org/abs/2604.07595 — *ROZA Graphs: Self-Improving Near-Deterministic RAG* (carried).
- https://arxiv.org/abs/2602.05152 — *RAG without Forgetting* (continual key memory; carried).
- https://danubedata.ro/blog/pgvector-rag-managed-postgres-2026 — pgvector production build guide on our
  exact Supabase/pgvector stack (WebFetch returned binary/garbage; carried from 07-09).
- https://sellercentral.amazon.com/gp/help/external/G200141500 — Product packaging requirements
  (authoritative [policy] doc behind the FNSKU-mandate claim — highest-value Seller Central re-fetch).
- Still-open Seller Central JS-shell fails: G201100890 (FBA inventory requirements), G200140860 (FBA
  product restrictions); plus n8nlab.io n8n product-research guide, lushbinary RAG production guide.
- **Verify against Seller Central / IRS (surfaced as search snippets, NOT fetched):**
  **DD+7 — funds held 7 days after delivery starting Mar 12 2026** (cash-flow + cash-basis month distortion);
  **1099-K threshold reverting to $20,000 AND 200 transactions for TY2026**;
  **stickerless commingling ends for shipments on/after Mar 31 2026** (FNSKU-label every unit);
  **retail receipts no longer valid for ungating — wholesale invoices / Letters of Authorization required.**

## WHAT'S BEEN FOUND

### Today (2026-07-10) — 8 new items, 0 transcripts ingested by the scheduled run
- **[policy] Key Amazon Reimbursement Policy Details, Changes & Updates** (SPS Commerce, updated Jun 15
  2026). The material one for OA unit economics: Amazon's **cost-based reimbursement model (eff. Mar 31
  2025)** pays lost/damaged FBA inventory on your **manufacturing/sourcing cost, not selling price** — so
  **per-unit landed cost is now the reimbursement basis** (submit via the IDR portal, Seller Central
  G66ZLS453YSE2Y4R, or Amazon lowballs the estimate; shipping/labeling/packaging excluded). Also: **claim
  windows cut to ~60 days** (FC-ops 60d; FBA customer returns US 60–120d; removals 15–75d); **lost/damaged/
  customer-return claims now automatic**, but **removals + mishandled returns stay manual**; **MCF caps**
  (UK £250, EU €275, CA $400, AU $450, MX $5000, unchanged 2026); **returnless resolutions do NOT restock**
  (seller eats refund + product). → Tighten returns/loss auditing to the 60-day window; keep COGS current.
  (`text-sources/2026-07-10/amazon-reimbursement-policy-sps.md`)
- **[practitioner/policy-cited] FBA New Selection Program (2026) launches July 30** (Nova Analytics,
  reporting a Jun 18 2026 Seller Central announcement; Ecomcrew-corroborated). Bigger inbound-placement
  credit, **90d free storage on first 100 units** of a qualifying parent ASIN, **reduced referral on first
  $25k/new branded ASIN for 365 days**; existing enrollees auto-migrate. **Flagged: private-label /
  Brand-Registry lever, NOT a pure-OA tactic** on existing listings — recorded for fee/market awareness
  only, no ai-brain change. (`text-sources/2026-07-10/fba-new-selection-program-2026-nova.md`)
- **1 YouTube queued** (see PENDING table): -Rv5hejVnVs.
- **4 fetch-pending** (see re-fetch list): Seller Central G200213130 + arXiv 2603.07379, 2606.04435,
  2604.00865.
- **1 skipped-thin:** cleartheshelf "How to Read a Keepa Chart – 2026 Update" — evergreen Keepa-101 by
  Chris Grant/OA Challenge (already heavily in corpus); not staged, to avoid Keepa/Chris-Grant skew.

### Rolling summary — most useful recent takeaways
- **Reimbursement is now cost-based, not retail (biggest open finance change):** lost/damaged FBA inventory
  is reimbursed on **manufacturing/sourcing cost** (eff. Mar 31 2025), with ~60-day manual claim windows and
  MCF caps. This makes accurate **per-unit landed cost + supplier invoices on file** not just a bookkeeping
  nicety but the literal reimbursement basis (SPS 07-10, reinforcing Nova 07-08 + Plugbooks 07-09). Returnless
  resolutions never restock — weight in thin-margin/high-return categories.
- **Self-learning-RAG recipe:** FLAIR (arXiv 2508.13390, deployed in Copilot) — two-track ranking blending
  vector similarity with feedback-learned indicators; synthetic questions bootstrap before real thumbs.
  Pair with RAGVA (2502.14930, continuous validation) + ProductResearch (2602.23716, step-level supervisor
  verification). **BuildMVPFast (07-07) supplies the concrete retrieval mechanics** (hybrid vector + BM25 +
  RRF k≈60 + cross-encoder rerank top 20-50→5-10 on pgvector + ParadeDB `pg_search`). **Memory/skills/agentic
  thread now growing:** ROZA 2604.07595, SAGE 2605.12061, AtomMem 2606.19847, 2604.14572 (skills-as-
  knowledge), 2603.04549 (memory admission), plus NEW 07-10: SoK Agentic-RAG survey 2603.07379, CHARM
  cascading-hallucination 2606.04435, Doctor-RAG failure-repair 2604.00865 — all pending real-browser re-fetch.
- **Buy discipline:** strict order scan → eligibility → red flags → fees/history → quantity LAST; subtract a
  return allowance (5–10%; "sellable margin, not spreadsheet margin"); 3-month inventory rule, ≤20% capital
  per ASIN; personal **30% min ROI** recurs across sources and matches `ai-brain.json` `minRoi:0.3`;
  **start 3–5 units** before scaling.
- **Keepa/SAS reading:** size buy cost off the **lowest price in the last 3 months**, not an Amazon-OOS
  spike; monthly-sold gold line is a **customer-count range**, not units, and only ~3.5M of 1B+ ASINs get
  it; rank-drops ≠ units; buy-box is regionally directional. Keepa Pro **tracking doubles as a sourcing
  tool** (offer-count / sales-rank threshold alerts). SAS Offers Panel + Charts Panel + Notes/Tags cover the
  same competition-read + lead-DB workflow. (NOTE: since Feb 23 2026 Keepa's **New price data includes
  shipping**; older data excludes it — factor into landed-cost reads.)
- **Fees/policy watch (biggest open [policy] items):** reimbursements now valued at **sourcing cost, not
  retail** (SPS 07-10); **FBA prep services ended Jan 1 2026**; storage ~6→5 months; 2026 referral/FBA fee
  update + Apr-17 fuel surcharge; **FBA New Selection Program (2026) launches Jul 30** (PL-only); unverified:
  FNSKU mandate (G200141500), Mar-31-2026 commingling end, wholesale-invoice-only ungating, DD+7, 1099-K $20k/200.
- Full detail: `research-inbox/research-insights.md` (per-topic, dated) and `research-inbox/digests/`
  (per-day).
