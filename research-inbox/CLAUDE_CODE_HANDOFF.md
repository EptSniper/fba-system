# Claude Code — daily research handoff

**This is the one file Claude Code should read every session.** A scheduled Cowork task
(`fba-daily-research`, ~7 AM daily) discovers new Amazon FBA/OA + system-building material, ingests text
sources, and **queues YouTube videos that it cannot transcribe itself** (the Cowork app can't call the
transcript API — you can). This file is rewritten by that task each run with what's pending and what it found.

Last updated by the scheduled task: 2026-07-13

---

## STANDING DAILY ACTIONS (do these when you open the project)

1. **Pull queued transcripts:** run `python knowledge-rag/fetch_transcripts.py` — it reads all
   `research-inbox/queue/*.json` items with `status:"queued"`, calls youtube-transcript.io with the key in
   `knowledge-rag/.env`, writes transcripts to `research-inbox/transcripts/`, and marks items `done`.
   *(Nothing is queued right now — see PENDING — but run it anyway; it's a no-op if empty and catches
   anything a later run adds.)*
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

- **YouTube videos still `queued` across all `queue/*.json`: 0.**
- **Unprocessed transcripts in `research-inbox/transcripts/`: 0** (29 in `processed/`; only `README.md`
  remains in the root). The pipeline is fully caught up — Steps 1–2 are no-ops this session until new
  material is queued.

**Re-fetch in a real browser (fetch-failed/pending from the sandbox — new this run + carried forward):**
- **NEW (2026-07-13):** https://robertclark-cpa.com/amazon-fba-tax-guide-from-1099-k-to-sales-tax-nexus/ —
  CPA-authored *1099-K to sales-tax nexus* guide. WebFetch got only a "Javascript is required" redirect
  shell. The nexus half is already covered by the two staged 07-13 tax pieces (Eightx, The FBA Guys); fetch
  mainly to confirm the **1099-K threshold reverting to $20,000 / 200 txns for TY2026**.
- **NEW (2026-07-13):** https://arxiv.org/abs/2604.20572 — *Ask Only When Needed: Proactive Retrieval from
  Memory and Skills for Experience-Driven Lifelong Agents*. On-thread with skills-as-knowledge + "don't
  retrieve when already gated/known".
- **NEW (2026-07-13):** https://arxiv.org/abs/2512.20237 — *MemR³: Memory Retrieval via Reflective Reasoning
  for LLM Agents*. Corpus/ai-brain retrieval.
- **NEW (2026-07-13):** https://arxiv.org/abs/2603.15658 — *Did You Check the Right Pocket? Cost-Sensitive
  Store Routing for Memory-Augmented Agents*. Memory-admission line (AtomMem 2606.19847, Adaptive Admission
  2603.04549).
- https://sellercentral.amazon.com/help/hub/reference/external/G201411300 — *2026 US Referral and FBA fee
  changes summary* (authoritative [policy] behind the Jan-15/16 overhaul + $0.78/$2.40 storage rates +
  181/456-day aged tiers; carried from 07-12). JS shell only in sandbox.
- https://arxiv.org/abs/2511.04502 — *RAGalyst: Automated Human-Aligned Agentic Evaluation for Domain-Specific
  RAG* (RAG-eval line; carried from 07-12).
- https://arxiv.org/abs/2604.18509 — *MASS-RAG: Multi-Agent Synthesis RAG* (agentic-RAG design; carried 07-12).
- https://sellercentral.amazon.com/help/hub/reference/external/G200213130 — *FBA inventory reimbursement
  policy* (cost-based reimbursement + ~60d claim windows; carried from 07-10).
- https://arxiv.org/abs/2603.07379 — *SoK: Agentic RAG* survey (carried from 07-10).
- https://arxiv.org/abs/2606.04435 — *CHARM: Cascading Hallucination in Agentic RAG* (carried).
- https://arxiv.org/abs/2604.00865 — *Doctor-RAG: Failure-Aware Repair for Agentic RAG* (carried).
- https://arxiv.org/abs/2604.14572 — *Don't Retrieve, Navigate* (skills-as-knowledge; carried).
- https://arxiv.org/abs/2603.04549 — *Adaptive Memory Admission Control for LLM Agents* (carried).
- https://arxiv.org/abs/2605.12061 — *SAGE: Self-Evolving Agentic Graph-Memory Engine* (carried).
- https://arxiv.org/abs/2606.19847 — *AtomMem: Memory via Atomic Facts* (carried).
- https://arxiv.org/abs/2604.07595 — *ROZA Graphs: Self-Improving Near-Deterministic RAG* (carried).
- https://arxiv.org/abs/2602.05152 — *RAG without Forgetting* (continual key memory; carried).
- https://danubedata.ro/blog/pgvector-rag-managed-postgres-2026 — pgvector production build guide on our
  exact Supabase/pgvector stack (WebFetch returned binary/garbage; carried from 07-09).
- https://sellercentral.amazon.com/gp/help/external/G200141500 — Product packaging requirements
  (authoritative [policy] behind the FNSKU-mandate claim; carried).
- Still-open Seller Central JS-shell fails: G201100890 (FBA inventory requirements), G200140860 (FBA
  product restrictions); plus n8nlab.io n8n product-research guide, lushbinary RAG production guide.
- **Verify against Seller Central / IRS (surfaced as search snippets, NOT fetched):**
  **DD+7 — funds held 7 days after delivery starting ~Mar 12 2026** (re-surfaced 07-13 by The Hustle Tax;
  cash-flow + cash-basis month distortion);
  **1099-K threshold reverting to $20,000 AND 200 transactions for TY2026** (re-surfaced 07-13);
  **stickerless commingling ends for shipments on/after Mar 31 2026** (FNSKU-label every unit);
  **retail receipts no longer valid for ungating — wholesale invoices / Letters of Authorization required.**

## WHAT'S BEEN FOUND

### Today (2026-07-13) — 7 new items; 3 text staged, 4 fetch-pending; 0 transcripts (pipeline caught up)
Weighted deliberately toward the **under-represented finances bucket** to counter the corpus's OA-sourcing/
Keepa/SellerAmp skew (ML no-bias rule).
- **[practitioner] Amazon FBA Tax Planning 2026: Multi-State Nexus** (Eightx, CFO-authored). FBA inventory
  creates **physical sales-tax nexus in every state Amazon stores a unit** — no minimum threshold, you don't
  pick the warehouse, retroactively assessable; **register before inventory arrives** and run the **Inventory
  Event Detail report** to see where stock sits. Marketplace-facilitator collection (all **45** sales-tax
  states; AK/DE/MT/NH/OR have none) covers **only facilitated marketplace sales tax** — NOT non-marketplace
  sales (Shopify/site/wholesale), local/city taxes (AZ/CA/CO), **income tax** (apportioned by sales factor;
  CA most aggressive — $800/yr LLC fee for any FBA presence), **property tax on inventory** (assessed often
  **Jan 1** — timing is a lever), or **zero-dollar returns**. **LLC→S-Corp at ~$50–100K net profit** saves
  ~$9K/yr SE tax (reasonable salary 40–60% of profit, rest distribution); **file Form 2553 by Mar 15**.
  Highest-value deduction fix: **break out settlement reports** (referral/FBA/storage/ads separately).
  (`text-sources/2026-07-13/amazon-fba-tax-planning-multistate-nexus.md`)
- **[practitioner] FBA Sales Tax Nexus Explained: The Part Amazon Doesn't Handle** (The FBA Guys, n=8,416
  valuations). Separate **"Amazon collected on the order"** from **"have we checked registration / filing /
  income-tax / franchise-tax / documentation obligations"** — facilitator is one mechanism, not a tax
  department. Factual first pass = 3 exports (marketplace tax collected; revenue by ship-to state Amazon +
  non-Amazon; non-Amazon revenue by state). **Don't over-register** ("everywhere to be safe" creates a
  zero-return filing calendar). Tax-returns-present submissions averaged **2.67x vs 2.10x** valuation
  multiple (documentation/maturity signal). (`text-sources/2026-07-13/fba-sales-tax-nexus-the-part-amazon-doesnt-handle.md`)
- **[practitioner] FBA Bookkeeping 2026: A2X vs Link My Books (Deposit Trap)** (The Hustle Tax). Seller
  Central "Sales" ≠ bank deposit (Amazon nets ads/refunds/storage/reserves) so **cash-basis hides margin** →
  use **accrual** via a connector tool. **A2X** (summary journal entries, per-channel, GAAP purists) vs
  **Link My Books** (cheaper all-channel, auto-COGS, DIY) vs **Webgility** (order-level + inventory sync,
  enterprise). All support a **per-SKU cost price → auto-COGS**. Flags **DD+7** (funds held 7d after delivery,
  ~Mar 12 2026 — verify vs Amazon). (`text-sources/2026-07-13/fba-bookkeeping-a2x-vs-linkmybooks-deposit-trap.md`)
- **4 fetch-pending/failed** (see re-fetch list, recorded snippet-only, NOT distilled): Robert Clark CPA
  1099-K/nexus (JS shell) + arXiv **2604.20572** (Ask Only When Needed), **2512.20237** (MemR³),
  **2603.15658** (cost-sensitive memory store routing).
- **Skipped to protect corpus balance:** `rJvyH94ydDc` (near-duplicate "Sourcing 101 (2026)" re-upload of the
  already-processed `OUGc0aiT7l4`); already-in-manifest fee/tool blogs; a Spanish-language OA tutorial.

### Rolling summary — most useful recent takeaways
- **Finances/tax (new this run):** FBA inventory = **physical nexus in every warehouse state**; marketplace
  facilitator only handles marketplace *sales* tax — income tax, property tax on inventory (Jan-1 timing),
  local taxes, and all non-Amazon-channel sales are still on you. **Keep a boring, traceable tax file** (what
  Amazon collected, what you filed, what's open) — it also lifts eventual valuation. **Accrual + per-unit
  landed cost as COGS** is the only way the scout's ROI ties to reality; **S-Corp at ~$50–100K net** (Form
  2553 by Mar 15). Watch **DD+7** funds-hold and the **1099-K $20K/200-txn** reversion (both to verify).
- **Fees/policy watch:** the "July 2026 FBA overhaul" is mostly a myth — the only real Jul 1 change is
  **Canada prep ending** (US ended Jan 1); H2 P&L actually moves on the **Jan-15/16 fee overhaul + April 3.5%
  fuel surcharge** and the **Q4 storage triple-stack** (up to ~$11/cu ft on an over-stocked, aged unit).
  Storage base is **$0.78/cu ft (not $0.87)**. Separately, the **Featured Offer (Buy Box) is going rank-only**
  — account health (ODR/chargebacks/VOC) now scores continuously and **gates Sponsored-ad impressions**
  SKU-by-SKU (EU/UK Jul 20, US by EOY 2026).
- **Reimbursement is cost-based, not retail:** lost/damaged FBA inventory reimbursed on **sourcing cost** (eff.
  Mar 31 2025), ~60-day manual claim windows; keep **per-unit landed cost + supplier invoices on file** and
  **file claims monthly**.
- **Cash discipline:** profit ≠ cash; inventory-to-sales and turn speed are survival metrics; run a **13-week
  cash forecast**; pass every reorder through "what does this prevent?". Matches ai-brain (≤20% capital/ASIN,
  3-month rule, start 3–5 units).
- **Buy discipline:** strict order scan → eligibility → red flags → fees/history → quantity LAST; subtract a
  5–10% return allowance; personal **30% min ROI** matches `ai-brain.json` `minRoi:0.3`.
- **Keepa/SAS reading:** size buy cost off the **lowest price in the last 3 months**, not an Amazon-OOS spike;
  monthly-sold gold line is a **customer-count range**, not units; rank-drops ≠ units. (Since Feb 23 2026
  Keepa's **New price data includes shipping**; older excludes it.)
- **Self-learning-RAG recipe:** FLAIR (2508.13390) two-track ranking + RAGVA (2502.14930) continuous
  validation + ProductResearch (2602.23716) step-level verification; concrete mechanics from BuildMVPFast
  07-07 (hybrid vector + BM25 + RRF k≈60 + cross-encoder rerank on pgvector + ParadeDB). Growing agentic/eval/
  memory thread pending real-browser re-fetch: SoK 2603.07379, CHARM 2606.04435, Doctor-RAG 2604.00865,
  RAGalyst 2511.04502, MASS-RAG 2604.18509, ROZA 2604.07595, SAGE 2605.12061, AtomMem 2606.19847, 2604.14572,
  2603.04549, 2602.05152, **plus this run: 2604.20572 (proactive memory/skill retrieval), 2512.20237
  (reflective memory retrieval), 2603.15658 (memory store routing)**.
- Full detail: `research-inbox/research-insights.md` (per-topic, dated) and `research-inbox/digests/`
  (per-day).
