# Claude Code — daily research handoff

**This is the one file Claude Code should read every session.** A scheduled Cowork task
(`fba-daily-research`, ~7 AM daily) discovers new Amazon FBA/OA + system-building material, ingests text
sources, and **queues YouTube videos that it cannot transcribe itself** (the Cowork app can't call the
transcript API — you can). This file is rewritten by that task each run with what's pending and what it found.

Last updated by the scheduled task: 2026-07-12

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

- **YouTube videos still `queued` across all `queue/*.json`: 0. Unprocessed transcripts: 0.** The
  "‼️ 3 unprocessed transcripts" the scheduled task flagged above (its own snapshot, taken mid-OneDrive-
  sync — see its note about `queue/2026-07-10.json` appearing truncated during that run) have all been
  pulled, distilled, and filed by Claude Code on 2026-07-12 — see the 2026-07-12 Claude Code entry in
  `research-insights.md` and the matching `research-manifest.json` status flips:
  - `a4A9YGu71Eg` → `transcript-processed` (one new tactic staged: catchall-email-domain coupon reuse).
  - `6sUYXwY7RNw`, `MWyq0J18-sM` → `skipped-thin` (reviewed, confirmed duplicative of already-staged
    SellerAmp/storefront-stalking/leaf-sourcing material — not staged, per the manifest `note` field on
    each). This is also the answer to the scheduled task's tasked-out question re: `6sUYXwY7RNw` (SellerAmp
    QVS thresholds — none beyond what's already staged) and `MWyq0J18-sM` (beginner-method overlap —
    confirmed a 101 rehash, dropped as instructed).
  - Also resolved: the `-Rv5hejVnVs` "no transcript file present" warning above was stale — that video
    was pulled + ingested by Claude Code on 2026-07-12 *before* this scheduled run's snapshot; its
    transcript is in `transcripts/processed/`, `queue/2026-07-10.json` parses fine (`status: "done"`),
    and its manifest entry already reads `transcript-processed`.
  - All 4 transcript files now sit in `research-inbox/transcripts/processed/`; only `README.md` remains
    in the root.

**Re-fetch in a real browser (fetch-failed/pending from the sandbox — new this run + carried forward):**
- **NEW:** https://sellercentral.amazon.com/help/hub/reference/external/G201411300 — *2026 US Referral and
  FBA fee changes summary* (authoritative [policy] behind the Jan-15/16 overhaul + $0.78/$2.40 storage rates
  + 181/456-day aged tiers that the Digital Applied mythbust cites). JS shell only in sandbox — confirm exact
  per-tier fulfillment numbers.
- **NEW:** https://arxiv.org/abs/2511.04502 — *RAGalyst: Automated Human-Aligned Agentic Evaluation for
  Domain-Specific RAG*. On-thread with our RAG-eval line (2504.14891, RAGVA 2502.14930) + Ask honesty.
- **NEW:** https://arxiv.org/abs/2604.18509 — *MASS-RAG: Multi-Agent Synthesis RAG*. On the agentic-RAG
  design thread for scout/knowledge-rag (SoK 2603.07379, Doctor-RAG 2604.00865).
- https://sellercentral.amazon.com/help/hub/reference/external/G200213130 — *FBA inventory reimbursement
  policy* (authoritative doc behind cost-based reimbursement + ~60d claim windows; carried from 07-10).
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
  (authoritative [policy] behind the FNSKU-mandate claim — highest-value Seller Central re-fetch).
- Still-open Seller Central JS-shell fails: G201100890 (FBA inventory requirements), G200140860 (FBA
  product restrictions); plus n8nlab.io n8n product-research guide, lushbinary RAG production guide.
- **Verify against Seller Central / IRS (surfaced as search snippets, NOT fetched):**
  **DD+7 — funds held 7 days after delivery starting Mar 12 2026** (cash-flow + cash-basis month distortion);
  **1099-K threshold reverting to $20,000 AND 200 transactions for TY2026**;
  **stickerless commingling ends for shipments on/after Mar 31 2026** (FNSKU-label every unit);
  **retail receipts no longer valid for ungating — wholesale invoices / Letters of Authorization required.**

## WHAT'S BEEN FOUND

### Today (2026-07-12) — 10 new items; 3 transcripts pulled (by a concurrent fetch) but NOT yet ingested
- **[policy] Amazon FBA Fees, Mid-2026: The Real Cost Math** (Digital Applied, Jul 6). Fee mythbust: the
  **only genuine Jul 1 2026 change is Canada prep/labelling ending** (sequel to US Jan 1). The viral
  **"$0.87/cu ft + 180-day storage overhaul on Jul 1" is false** — real standard storage is **$0.78/cu ft
  (Jan–Sep), $2.40 (Oct–Dec)** and the **181-day aged tier is the pre-existing baseline**. Real H2 driver =
  **January's Jan-15/16 overhaul** (avg +$0.08/unit; new **$0.60/unit consolidated inbound-defect fee**;
  aged 366+ min doubled to $0.30 + **new 456+ tier**; low-inventory fee now **FNSKU-level**) + **April's
  3.5% fuel surcharge** — a % of the raised fee, so **apply it LAST** in landed-cost math. **Q4 triple-stack**
  (base + $1.88 utilization + aged) can hit **$11.18/cu ft/mo**; the **271–300-day aged cliff is $5.45/cu ft
  (11×)**, snapshotted on the 15th, FIFO network-wide. (`text-sources/2026-07-12/amazon-fba-fees-mid-2026-digitalapplied.md`)
- **[policy] Featured Offer Overhaul: Rank-Only Buy Box Rules** (Digital Applied, Jul 10, on Amazon's Jul 6
  Seller Forums post). Amazon **removes the standalone seller-performance eligibility gate** for the Featured
  Offer; **chargebacks, ODR (<1% ceiling), VOC complaints become weighted inputs in one rank-only score**
  alongside price/free-shipping/delivery. "Structure changed, criteria didn't" — a weak account now
  **competes and loses** rather than being excluded. **Phased: EU/UK reported Jul 20, global by EOY 2026, US
  unannounced; no action, auto-included; weights undisclosed.** Knock-on nobody covers: **without the Featured
  Offer, Sponsored Products/Brands/Display serve ZERO impressions** ("regardless of campaign status"),
  eligibility is **SKU-specific**. On the OA "can-it-profit"/Buy-Box axis; **no ai-brain change**, but low
  ODR/chargebacks now move Buy Box rank continuously. (`text-sources/2026-07-12/amazon-featured-offer-rank-only-buybox-digitalapplied.md`)
- **[practitioner] FBA Cash Flow Management: Inventory Is Where the Cash Gets Quiet** (The FBA Guys, n≈8,503
  valuations). Inventory ties up cash **before** the sale and **growth widens the gap**; inventory-to-sales
  climbs as **turn speed falls** (few weeks 10.6% → months 24.7% → year+ 75.8%) and as **sales decline**.
  Reorder test: **"if this order goes wrong, what else has to wait?"**; credit lines bridge timing but hide
  weak margin if abused; minimum system = a **13-week cash forecast**. For a tiny OA bankroll,
  **inventory-to-sales + turn speed are the cash-survival signals** — the discipline behind the ai-brain
  ≤20%-per-ASIN / 3-month / 3–5-unit rules. (`text-sources/2026-07-12/amazon-fba-cash-flow-management-thefbaguys.md`)
- **[practitioner] Amazon Fee Increases 2026: How to Protect Profit** (Seller Labs). The **+$0.08/unit** hike
  comes **out of profit, not sale price** (~5% of take-home at a 10% margin), compounding across SKUs.
  Measure via **Fee Preview CSV**; trim SKUs under a **~20% profit buffer**; shrink packaging ~0.2" to drop a
  size tier (N/A for OA on existing listings); **file FBA reimbursement claims monthly** (ties to cost-based
  reimbursement, 07-10). (`text-sources/2026-07-12/amazon-fee-increase-2026-protect-profit-sellerlabs.md`)
- **3 YouTube found + queued, then auto-pulled during the run** (now unprocessed transcripts — see PENDING):
  a4A9YGu71Eg (winning product examples), 6sUYXwY7RNw (SellerAmp QVS), MWyq0J18-sM (best beginner method).
- **3 fetch-pending** (see re-fetch list): Seller Central G201411300 + arXiv 2511.04502, 2604.18509.
- **Skipped:** rJvyH94ydDc / QVkuql9NDY0 (near-certain duplicate 101/beginner content already ingested);
  Keepa Product Finder text guides (Keepa-skew discipline per the ML no-bias rule).

### Rolling summary — most useful recent takeaways
- **Fees/policy watch (biggest open [policy] items):** the "July 2026 FBA overhaul" is mostly a myth — the
  **only real Jul 1 change is Canada prep ending** (US ended Jan 1); the cost that actually moves H2 P&L is
  the **Jan-15/16 fee overhaul + April 3.5% fuel surcharge**, and the **Q4 storage triple-stack** (up to
  ~$11/cu ft on an over-stocked, aged unit). Storage base is **$0.78/cu ft (not $0.87)**. Separately, the
  **Featured Offer (Buy Box) is going rank-only** — account health (ODR/chargebacks/VOC) now scores
  continuously and **gates your Sponsored-ad impressions** SKU-by-SKU (EU/UK Jul 20, US by EOY 2026).
- **Reimbursement is cost-based, not retail:** lost/damaged FBA inventory is reimbursed on **sourcing cost**
  (eff. Mar 31 2025), ~60-day manual claim windows, MCF caps, returnless resolutions don't restock. Makes
  **per-unit landed cost + supplier invoices on file** the literal reimbursement basis (SPS 07-10; reinforced
  by the cash-flow + fee-protect finds this run — file claims monthly, keep COGS current).
- **Cash discipline (new this run):** profit ≠ cash; inventory-to-sales and turn speed are the survival
  metrics; run a **13-week cash forecast** and pass every reorder through "what does this prevent?" before
  "can I afford it?". Matches ai-brain (≤20% capital/ASIN, 3-month rule, start 3–5 units).
- **Buy discipline:** strict order scan → eligibility → red flags → fees/history → quantity LAST; subtract a
  5–10% return allowance ("sellable margin, not spreadsheet margin"); personal **30% min ROI** matches
  `ai-brain.json` `minRoi:0.3`.
- **Keepa/SAS reading:** size buy cost off the **lowest price in the last 3 months**, not an Amazon-OOS spike;
  monthly-sold gold line is a **customer-count range**, not units; rank-drops ≠ units; Keepa Pro tracking
  doubles as a sourcing tool. (Since Feb 23 2026 Keepa's **New price data includes shipping**; older excludes
  it — factor into landed-cost.)
- **Self-learning-RAG recipe:** FLAIR (2508.13390) two-track ranking + RAGVA (2502.14930) continuous
  validation + ProductResearch (2602.23716) step-level verification; concrete mechanics from BuildMVPFast
  07-07 (hybrid vector + BM25 + RRF k≈60 + cross-encoder rerank on pgvector + ParadeDB). Growing agentic/
  eval/memory thread pending real-browser re-fetch: SoK 2603.07379, CHARM 2606.04435, Doctor-RAG 2604.00865,
  **RAGalyst 2511.04502 (eval)**, **MASS-RAG 2604.18509**, ROZA 2604.07595, SAGE 2605.12061, AtomMem
  2606.19847, 2604.14572, 2603.04549, 2602.05152.
- Full detail: `research-inbox/research-insights.md` (per-topic, dated) and `research-inbox/digests/`
  (per-day).
