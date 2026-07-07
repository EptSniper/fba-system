# Claude Code — daily research handoff

**This is the one file Claude Code should read every session.** A scheduled Cowork task
(`fba-daily-research`, ~7 AM daily) discovers new Amazon FBA/OA + system-building material, ingests text
sources, and **queues YouTube videos that it cannot transcribe itself** (the Cowork app can't call the
transcript API — you can). This file is rewritten by that task each run with what's pending and what it found.

Last updated by the scheduled task: 2026-07-07

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

**Updated 2026-07-07 (2nd pass) by Claude Code:** all 4 items from the last check are resolved —
`1kgp13McYLc` and `wwNw5vNAyeM` (freshly queued) ingested; `X6JjPUZd4xw` unexpectedly pulled clean this
time (captions must have been added since the last empty-`tracks[]` check) and is now ingested too.

| videoId | Title | Result |
|---|---|---|
| 1kgp13McYLc | Amazon Online Arbitrage Product Sourcing MASTERCLASS For 2026 | ✅ ingested |
| wwNw5vNAyeM | Keepa Charts: The Ultimate Amazon FBA Tutorial for 2026 | ✅ ingested |
| X6JjPUZd4xw | Sourcing Overlooked Listings Using Keepa Product Finder | ✅ ingested (previously empty captions, now fixed) |
| TBFh9vFBq7k | Online Arbitrage Sourcing Using Keepa (ADVANCED TACTICS) | still **STUCK: LOGIN_REQUIRED**, unchanged |

Pull command: `python knowledge-rag/fetch_transcripts.py`

**Unprocessed files in `research-inbox/transcripts/` (root):** 0 ingestable. Two `*__RAW.json` remain —
`9QGs4hfKrhY__RAW.json` (duplicate of hxk1JS4EsU4, resolved) and `TBFh9vFBq7k__RAW.json` (still
login-required). Everything genuinely ingested is in `processed/`.

**Re-fetch in a real browser (fetch-failed from the sandbox — carried forward + new):**
- **NEW:** https://arxiv.org/abs/2604.07595 — *ROZA Graphs: Self-Improving Near-Deterministic RAG through
  Evidence-Centric Feedback*. On-thread with the self-learning-RAG line (FLAIR 2508.13390). Snippet only.
- https://arxiv.org/abs/2602.05152 — RAG without Forgetting (continual key memory); pairs with FLAIR.
- https://sellercentral.amazon.com/gp/help/external/G200141500 — Product packaging requirements
  (authoritative [policy] doc behind the unverified FNSKU-mandate claim below — highest-value re-fetch).
- Still open Seller Central JS-shell fails: G201100890 (FBA inventory requirements), G200140860 (FBA
  product restrictions); plus n8nlab.io n8n product-research guide.
- Optional new fact to chase if fetching bookkeeping: A2X/finaloop claim **2026 FBA reimbursements are now
  valued at sourcing cost, not sale price** — keep sourcing invoices/landed-cost on file. Verify before
  treating as [policy].

## WHAT'S BEEN FOUND

### Today (2026-07-07) — 5 new items (discovery-only run; nothing ingested by the scheduled task itself)
- **BuildMVPFast: Hybrid Search for RAG** [practitioner] — vector + BM25 merged with **RRF (k≈60)**, then
  **cross-encoder rerank top 20-50 → top 5-10**. Postgres-native and fits our Supabase stack:
  **pgvector (dense) + ParadeDB `pg_search` (BM25)**. Benchmarks (Weaviate/BEIR): hybrid+rerank
  Success@1 0.43→0.52, Recall@5 0.70→0.81, nDCG@10 0.61→0.70. Gotchas: normalize scores before weighted
  blending, enrich uniform chunks with section titles (BM25 length-norm), adjust weights by query intent,
  rerank 20-50 not 5/200. **Concrete `knowledge-rag` retrieval upgrade path — staged, not implemented.**
  (text-sources/2026-07-07/hybrid-search-rag-vector-keyword-reranking.md)
- **OA Challenge: 5 Keepa Power Moves** [practitioner] — named KPF tactic taxonomy (batch storefront
  stalking, FBM inventory, stable-price filter, brand-new <1mo products, reverse-source by brand) + advanced
  moves (lead synthesizer, A2A flips, KPF negative keywords, buy-the-pinch, no-sales-rank filtering).
  Procedures are behind Scribehow/paid playbook — a **map, not a manual**; useful for scout discovery-hint
  ideation. (text-sources/2026-07-07/oachallenge-5-keepa-power-moves.md)
- **2 YouTube queued** (see PENDING): 1kgp13McYLc OA sourcing masterclass; wwNw5vNAyeM Keepa **chart-reading**
  tutorial (complements the Product-Finder-heavy Keepa videos already in the corpus).
- **1 fetch-failed:** arXiv 2604.07595 ROZA Graphs (see re-fetch list).

### Rolling summary — most useful recent takeaways
- **Self-learning-RAG recipe:** FLAIR (arXiv 2508.13390, Microsoft, deployed in Copilot) — two-track ranking
  blending vector similarity with feedback-learned indicators; synthetic questions bootstrap before real
  thumbs exist. Pair with RAGVA (2502.14930): continuous validation over spec-based testing; ProductResearch
  (2602.23716) adds step-level supervisor verification. **BuildMVPFast (today) supplies the concrete
  retrieval mechanics (hybrid + RRF + rerank on pgvector) to build under all of it.** ROZA (2604.07595,
  pending re-fetch) is the next self-improving-RAG paper to read.
- **Buy discipline:** strict order scan → eligibility → red flags → fees/history → quantity LAST; always
  subtract a return allowance ("sellable margin, not spreadsheet margin"); 3-month inventory rule, ≤20%
  capital per ASIN; personal 30% min ROI recurs across sources and matches `ai-brain.json` `minRoi:0.3`.
- **Keepa/SAS reading:** SAS Charts panel = licensed Keepa data — rank history sanity-checks the sales
  estimate, price history separates normal price from spike; size buy cost off the **lowest price in the
  last 3 months**, not an Amazon-OOS spike; a sudden seller-count flatline drop can signal an IP complaint
  vs. a gradual staircase = normal sell-through. BSR is a filter, not a decision.
- **Fees/policy watch:** 2026 referral/FBA fee update + Apr 17 3.5% fuel surcharge; prep now fully
  seller-owned; the FNSKU-mandate claim (G200141500) and the sourcing-cost reimbursement basis are the
  biggest open [policy] questions.
- Full detail: `research-inbox/research-insights.md` (per-topic, dated) and `research-inbox/digests/`
  (per-day).
