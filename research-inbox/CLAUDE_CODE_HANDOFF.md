# Claude Code — daily research handoff

**This is the one file Claude Code should read every session.** A scheduled Cowork task
(`fba-daily-research`, ~7 AM daily) discovers new Amazon FBA/OA + system-building material, ingests text
sources, and **queues YouTube videos that it cannot transcribe itself** (the Cowork app can't call the
transcript API — you can). This file is rewritten by that task each run with what's pending and what it found.

Last updated by the scheduled task: 2026-07-09

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

- **YouTube videos still `queued` across all `queue/*.json`: 3.** Pull them with:
  `python knowledge-rag/fetch_transcripts.py`

  | videoId | title | queue file |
  | --- | --- | --- |
  | Tcd4jAkOi6Q | Online Arbitrage Just Got Easier - NEW Sourcing Method | queue/2026-07-09.json |
  | FRK7JY7_EJY | How to Find Profitable Amazon Products FAST in 2026 (Reverse Sourcing) | queue/2026-07-09.json |
  | ctwXY3Vwy8o | How To Use Keepa for Amazon FBA (New Feature Tutorial) | queue/2026-07-09.json |

  After pulling, ingest the resulting transcripts (STANDING ACTION 2) and flip each manifest item
  `queued → transcript-processed`.

- **Unprocessed files in `research-inbox/transcripts/` (root): 0.** Only `README.md` remains; everything
  else is in `processed/`.

**Re-fetch in a real browser (fetch-failed/pending from the sandbox — carried forward + new):**
- **NEW:** https://arxiv.org/abs/2604.14572 — *Don't Retrieve, Navigate: Distilling Enterprise Knowledge
  into Navigable Agent Skills for QA and RAG*. Skills-as-knowledge — directly on-thread with our fba-*
  skills design. Snippet only; distill after fetch.
- **NEW:** https://arxiv.org/abs/2603.04549 — *Adaptive Memory Admission Control for LLM Agents*. When to
  admit a fact into long-term memory; pairs with AtomMem 2606.19847 for ai-brain/corpus durable-fact
  retention. Snippet only.
- **NEW:** https://danubedata.ro/blog/pgvector-rag-managed-postgres-2026 — pgvector production build guide
  (on our exact Supabase/pgvector stack). WebFetch returned binary/garbage; needs a real browser.
- https://arxiv.org/abs/2605.12061 — *SAGE: A Self-Evolving Agentic Graph-Memory Engine* (carried).
- https://arxiv.org/abs/2606.19847 — *AtomMem: Memory System for LLM Agents via Atomic Facts* (carried).
- https://arxiv.org/abs/2604.07595 — *ROZA Graphs: Self-Improving Near-Deterministic RAG* (carried).
- https://arxiv.org/abs/2602.05152 — *RAG without Forgetting* (continual key memory); pairs with FLAIR.
- https://sellercentral.amazon.com/gp/help/external/G200141500 — Product packaging requirements
  (authoritative [policy] doc behind the FNSKU-mandate claim — highest-value re-fetch).
- Still-open Seller Central JS-shell fails: G201100890 (FBA inventory requirements), G200140860 (FBA
  product restrictions); plus n8nlab.io n8n product-research guide, lushbinary RAG production guide.
- **Verify against Seller Central / IRS (surfaced as search snippets, NOT fetched):**
  **DD+7 — funds held 7 days after delivery starting Mar 12 2026** (cash-flow + cash-basis month distortion);
  **1099-K threshold reverting to $20,000 AND 200 transactions for TY2026**;
  **stickerless commingling ends for shipments on/after Mar 31 2026** (FNSKU-label every unit);
  **retail receipts no longer valid for ungating — wholesale invoices / Letters of Authorization required.**

## WHAT'S BEEN FOUND

### Today (2026-07-09) — 8 new items, 0 transcripts ingested
- **[practitioner] Amazon Seller Accounting & Bookkeeping (2026 Guide)** (Plugbooks, vendor blog) —
  bookkeeping fundamentals for OA. **Sales ≠ Deposits → reconcile the Amazon settlement report every ~2
  weeks** (match gross sales, subtract fees, adjust refunds, verify deposit) = the single most important
  step; separate business bank/card; **FIFO COGS + per-unit landed-cost tracking** (reinforces honest-COGS
  after the Nov-2025 reimbursement-at-cost change); categorize fees separately (referral/FBA/storage/PPC);
  cash basis under ~$1M / accrual over ~$1M; income tax still owed despite marketplace-facilitator sales tax.
  Flagged UNVERIFIED search snippets (not on page): DD+7 and 1099-K $20k/200 (see verify list).
  (`text-sources/2026-07-09/plugbooks-amazon-seller-accounting-2026.md`)
- **[practitioner] Amazon Arbitrage: The Complete Guide for 2026** (ScoutClaw, vendor blog) — a clean
  standard primer that **corroborates the project's existing gates** (≥30% ROI after fees = ai-brain
  `minRoi:0.3`; BSR<100k and climbing-BSR=fading-demand; start 3–5 units then scale; 5–10% returns buffer;
  ASIN variation traps; brand/IP risk). Useful contrast: the vendor's own tool advertises a looser **15%+
  margin** deal bar vs the 30% ROI editorial advice. No ai-brain change — confirmation, not new signal.
  (`text-sources/2026-07-09/scoutclaw-amazon-arbitrage-guide-2026.md`)
- **3 YouTube queued** (see PENDING table): Tcd4jAkOi6Q, FRK7JY7_EJY, ctwXY3Vwy8o.
- **2 arXiv fetch-pending + 1 fetch-failed** (see re-fetch list): 2604.14572, 2603.04549, DanubeData pgvector.

### Rolling summary — most useful recent takeaways
- **Self-learning-RAG recipe:** FLAIR (arXiv 2508.13390, deployed in Copilot) — two-track ranking blending
  vector similarity with feedback-learned indicators; synthetic questions bootstrap before real thumbs.
  Pair with RAGVA (2502.14930, continuous validation) + ProductResearch (2602.23716, step-level supervisor
  verification). **BuildMVPFast (07-07) supplies the concrete retrieval mechanics** (hybrid vector + BM25 +
  RRF k≈60 + cross-encoder rerank top 20-50→5-10 on pgvector + ParadeDB `pg_search`). **Memory/skills thread
  now growing:** ROZA 2604.07595, SAGE 2605.12061, AtomMem 2606.19847, plus NEW 2604.14572 (skills-as-
  knowledge) and 2603.04549 (memory admission control) — all pending real-browser re-fetch.
- **Buy discipline:** strict order scan → eligibility → red flags → fees/history → quantity LAST; subtract a
  return allowance (5–10%; "sellable margin, not spreadsheet margin"); 3-month inventory rule, ≤20% capital
  per ASIN; personal **30% min ROI** recurs across sources (now also ScoutClaw) and matches `ai-brain.json`
  `minRoi:0.3`; **start 3–5 units** before scaling.
- **Keepa/SAS reading:** size buy cost off the **lowest price in the last 3 months**, not an Amazon-OOS
  spike; monthly-sold gold line is a **customer-count range**, not units, and only ~3.5M of 1B+ ASINs get
  it; rank-drops ≠ units; buy-box is regionally directional. Keepa Pro **tracking doubles as a sourcing
  tool** (offer-count / sales-rank threshold alerts). SAS Offers Panel + Charts Panel + Notes/Tags cover the
  same competition-read + lead-DB workflow. (NOTE: since Feb 23 2026 Keepa's **New price data includes
  shipping**; older data excludes it — factor into landed-cost reads.)
- **Finances/bookkeeping:** Sales ≠ Deposits — reconcile the settlement report every 2 weeks; FIFO COGS +
  landed-cost is mandatory for true profit and for the reimbursement-at-cost regime; keep per-unit landed
  cost + supplier invoices on file (≤60-day claim window). Watch DD+7 (Mar 12 2026) for cash-flow timing.
- **Fees/policy watch (biggest open [policy] items):** reimbursements now valued at **sourcing cost, not
  retail**; **FBA prep services ended Jan 1 2026**; storage ~6→5 months; 2026 referral/FBA fee update +
  Apr-17 fuel surcharge; unverified: FNSKU mandate (G200141500), Mar-31-2026 commingling end, wholesale-
  invoice-only ungating, DD+7, 1099-K $20k/200.
- Full detail: `research-inbox/research-insights.md` (per-topic, dated) and `research-inbox/digests/`
  (per-day).
