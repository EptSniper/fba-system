# Claude Code — daily research handoff

**This is the one file Claude Code should read every session.** A scheduled Cowork task
(`fba-daily-research`, ~7 AM daily) discovers new Amazon FBA/OA + system-building material, ingests text
sources, and **queues YouTube videos that it cannot transcribe itself** (the Cowork app can't call the
transcript API — you can). This file is rewritten by that task each run with what's pending and what it found.

Last updated by the scheduled task: 2026-07-04

---

## STANDING DAILY ACTIONS (do these when you open the project)

1. **Pull queued transcripts:** run `python knowledge-rag/fetch_transcripts.py` (reads all
   `research-inbox/queue/*.json` items with `status:"queued"`, writes transcripts to
   `research-inbox/transcripts/`, marks items done).
2. **Ingest new transcripts:** for each new file in `research-inbox/transcripts/` (not under `processed/`),
   follow the `fba-transcript-ingest` skill — distill cited takeaways into
   `research-inbox/research-insights.md`, append a JSON line to `research-inbox/corpus-staging.jsonl`,
   record the item in `research-inbox/research-manifest.json`, then MOVE the file to
   `research-inbox/transcripts/processed/`.
3. **Periodically merge staged → live:** review `corpus-staging.jsonl` + `research-insights.md`, merge the
   reviewed insights into `learning-hub/`, and run the real `knowledge-rag` ingestion/embedding pipeline so
   Ask/scout/control-center actually get smarter. Reviewed merge, never an auto-dump into
   `knowledge-rag/corpus/`.
4. **Use the skills:** consult `SKILLS_INDEX.md` before any non-trivial action and use the matching `fba-*`
   skill (`fba-transcript-ingest` for ingestion; `fba-brain-updater` if a finding should change a buying
   threshold in `ai-brain.json` — today's gated-brands tracker below is exactly such a review candidate).
5. **Post the Discord update:** after finishing the above, POST a short update using the webhook URL stored
   as `RESEARCH_DISCORD_WEBHOOK_URL` in `knowledge-rag/.env` (read the env var directly; NEVER print, paste,
   or commit the URL value anywhere, including this file). Summarize: how many new items today's scheduled
   run found, how many transcripts were fetched/ingested since the last update, and current local-corpus vs
   live-Supabase document/chunk counts if they differ. Default to the batched-digest pattern.
6. **Hygiene:** never print or commit `knowledge-rag/.env` or any key; cite sources in anything you write;
   no auto-buy or money movement, ever.

## PENDING NOW (recomputed 2026-07-04 from the real queue files)

| videoId | Title | Queued in |
|---|---|---|
| `TBFh9vFBq7k` | Online Arbitrage Sourcing Using Keepa (ADVANCED TACTICS) | 2026-06-30.json — **stuck**: API returns LOGIN_REQUIRED / PLAYABILITY_STATUS_NOK (raw response saved as `transcripts/TBFh9vFBq7k__RAW.json`); needs a manual re-check of the source video, not another blind pull |
| `rdltezXxIrk` | Keepa product finder tutorial 2026 \| Amazon FBA | 2026-07-04.json |
| `jeqFx9ZiOhg` | How to Use Amazon FBA Profit Calculator \| Every Fee Every Cost Explained 2026 (AMZ Prep) | 2026-07-04.json |

Pull command:

```
python knowledge-rag/fetch_transcripts.py
```

Unprocessed files in `research-inbox/transcripts/`: **0 ingestible** (only `TBFh9vFBq7k__RAW.json`, which
contains no transcript text, plus the folder README). All previously fetched transcripts are in `processed/`.

## WHAT'S BEEN FOUND

### Today (2026-07-04) — 9 new items (full detail: `digests/2026-07-04.md`)

**Queued videos (2):** rdltezXxIrk (Keepa Product Finder tutorial, Oct 2025 — a second practitioner's PF
recipes next to the just-ingested Parameter Method transcript) and jeqFx9ZiOhg (AMZ Prep, Apr 2026 — every
2026 fee explained; cross-checks fba-deal-calculator).

**Text sources ingested + staged (7):**
- **Ecom Circles 2026 OA guide** — realistic net margins 10–20%; 40% gross-margin floor with full COGS
  (3PL prep $0.50–$2/unit, 2–5% inspection loss); 2026 rule changes to verify officially (commingling ends
  Mar 31, Amazon's own prep ended Jan 1, retail receipts no longer ungate). [practitioner]
- **B2B Supplier Hub reverse-sourcing workflow (Jun 2026)** — reverse sourcing's top use is a 2–3-supplier
  bench for existing winners; 2026 chain-of-custody enforcement means authorization, not availability, is
  the gate. Wholesale-tier; filed for later maturity. [practitioner]
- **Stealth Seller storefront screen** — stalk mixed-category storefronts <~1,000 products with irregular
  small batches and no Amazon on-listing; skip single-brand giants (wholesale). Concrete scout_pro
  storefront-scoring filter. [practitioner]
- **The Selling Guys 750+ gated/restricted-brand tracker (updated Jul 1 2026)** — tiered risk list (legal
  action → C&D → gated); Nike/Lego(US)/Fitbit/Under Armour gated; Apple/Bose/Ninja/Razer/Makita legal tier.
  **Review candidate for the ai-brain avoid/caution lists via fba-brain-updater — do not auto-import.**
  [practitioner]
- **Eightx Xero/A2X guide** — the Xero implementation of "never book the net deposit": per-fee-type chart
  of accounts, A2X ≥$50K/mo vs Link My Books below, 5-business-day settlement reconciliation cadence,
  reserves as an Amazon Receivables asset. [practitioner]
- **arXiv 2603.02153 (Dell, production)** — multi-query + RRF fusion gains are neutralized after reranking
  (Hit@10 0.51→0.48, added latency): don't add fusion to knowledge-rag by default; A/B behind the eval
  harness. PDF had no machine-readable text this run — read it before design decisions. [practitioner]
- **arXiv 2605.01664** — claim-level LLM-judge grounding harness (separate judge model, no outside
  knowledge, partial evidence = unsupported, CSV audit trail at every stage): the design to copy for an Ask
  grounding check; its "100%" result is a 25-query eval — ignore the number, keep the design. [practitioner]

### Rolling summary — most useful recent takeaways (details: `research-insights.md` + `digests/`)

- **Keepa reading discipline** (XdUGuD4ouKI, Cflrv_y9lSA — ingested 2026-07-04): parent-category BSR only;
  offer-count spikes (1→43 sellers in ~2 weeks) precede price crashes; "Keepa cliffs" (32→4 sellers) = active
  IP enforcement, stronger evidence than an ipalert lookup; price off 1+ years of history, never the spot.
- **2026 fee map** (Seller Snap + AMZ Prep + Eightx, staged 07-01→07-03): Apr-17 ~3.5% fuel surcharge on FBA
  fulfillment; low-inventory fee now FNSKU-level (most small-OA SKUs exempt — check before deep replens);
  returns-processing fee above category thresholds; aged-inventory surcharge from ~181 days.
- **Ungating playbook** (IBXT2txZtJE + Seller Labs + today's Ecom Circles): bulk auto-ungate scans first
  (50–100 brands clear free on a new account); invoice-gated → ~10 units from the brand or a major retailer,
  addresses matching the seller account; retail receipts no longer work in 2026; resubmission is a volume
  game; paid ungating services just repeat this.
- **Sourcing as a database, not a hunt** (FBA Lead List, 07-03): save every analyzed ASIN including non-buys
  and rescan the lead bank — leads mature in 2–6 months; validates the `leads` + outcomes design.
- **Cash-flow clock** (Nova, 07-02): DD+7 disbursement since Mar 12 2026; reserve 3–12% of trailing revenue,
  velocity-linked; Monday 4-number routine (disbursement vs forecast, reserve WoW, days-of-inventory, 28-day
  CM/SKU).
- **RAG build guidance** (2504.14891 eval survey; 2501.07391 knob ablation; 2509.20415 online embedding
  adaptation; 2510.11483 perturbation-based confidence; + today's 2603.02153 fusion counter-evidence and
  2605.01664 grounding harness): measure every retrieval change behind a retrieval-aware eval with
  claim-level grounding checks; single-query + rerank may beat multi-query fusion; flag low-confidence Ask
  answers instead of sounding uniformly sure.
