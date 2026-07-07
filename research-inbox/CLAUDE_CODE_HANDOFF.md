# Claude Code — daily research handoff

**This is the one file Claude Code should read every session.** A scheduled Cowork task
(`fba-daily-research`, ~7 AM daily) discovers new Amazon FBA/OA + system-building material, ingests text
sources, and **queues YouTube videos that it cannot transcribe itself** (the Cowork app can't call the
transcript API — you can). This file is rewritten by that task each run with what's pending and what it found.

Last updated by the scheduled task: 2026-07-06

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

**Updated 2026-07-07 by Claude Code — the 8-item queue below has been worked through:**

| videoId | Title | Result |
|---|---|---|
| rdltezXxIrk | Keepa product finder tutorial 2026 \| Amazon FBA | ✅ ingested |
| jeqFx9ZiOhg | How to Use Amazon FBA Profit Calculator \| Every Fee Every Cost Explained | ✅ ingested |
| hxk1JS4EsU4 | Beginners Guide To Amazon FBA Online Arbitrage in 2026 (Free Course) | ✅ ingested |
| D3FhvdMVLl8 | Storefront Stalking is NOT a Profitable Sourcing Method | ✅ ingested |
| ljlERpMrcBk | Live Online Arbitrage Sourcing: Storefront Stalking Tutorial | ✅ ingested |
| 9QGs4hfKrhY | (queued as "SellerAmp Setup Tutorial" but fetched content was byte-identical to hxk1JS4EsU4) | duplicate — saved, not re-ingested |
| X6JjPUZd4xw | Sourcing Overlooked Listings Using Keepa Product Finder | genuinely no caption track (empty `tracks[]`) — left queued, re-check periodically |
| TBFh9vFBq7k | Online Arbitrage Sourcing Using Keepa (ADVANCED TACTICS) — STUCK: LOGIN_REQUIRED at the API, needs manual re-check | still stuck, unchanged |

Pull command: `python knowledge-rag/fetch_transcripts.py`

**Unprocessed files in `research-inbox/transcripts/`:** 0 (only the stuck `TBFh9vFBq7k__RAW.json`,
the empty-captions `X6JjPUZd4xw__RAW.json`, and `README.md` remain at the root; everything actually
ingested — plus the duplicate `9QGs4hfKrhY` — is in `processed/`).

**Re-fetch in a real browser (fetch-failed from the sandbox):**
- https://sellercentral.amazon.com/gp/help/external/G200141500 — Product packaging requirements. Third
  Seller Central JS-shell failure (after G200140860, G201100890). This is the authoritative [policy] doc
  for the 2026 prep changes AND the unverified FNSKU-mandate claim below — highest-value re-fetch.
- https://arxiv.org/abs/2602.05152 — RAG without Forgetting (continual key memory); pairs with FLAIR.
- Still open from earlier runs: G201100890 (FBA inventory requirements), G200140860 (FBA product
  restrictions), n8nlab.io n8n product-research guide.

## WHAT'S BEEN FOUND

### Today (2026-07-06) — 8 new items
- **Snapl: 2026 FBA prep requirements** [practitioner] — Amazon ended US prep/labeling services Jan 1,
  2026; FCs no longer fix errors at check-in, so prep quality is now part of the buy decision. Failure
  modes: competing barcodes, missing suffocation warnings, bundles not physically one unit, carton labels
  on seams. **⚠ VERIFY:** search snippets claim a Mar 31, 2026 FNSKU mandate for non-Brand-Registry
  resellers (manufacturer barcodes no longer accepted, defect fees $0.32–$5.72/unit) — NOT confirmed in a
  fetched source; check G200141500 before treating as [policy] or touching ai-brain.json.
  (text-sources/2026-07-06/snapl-fba-prep-requirements-2026.md)
- **QuickBooks: Amazon seller tax 2026** [practitioner] — 1099-K threshold back to $20k AND 200
  transactions for the 2026 tax year; FBA placement creates physical nexus in ~44 states; some states want
  zero-dollar returns even when Amazon remits; resale certificates avoid sales tax on OA inventory buys
  (direct COGS cut). (text-sources/2026-07-06/quickbooks-amazon-seller-tax-2026.md)
- **SellerApp: IP-complaint playbook** [practitioner] — suppress-first mechanics; check Account Health
  daily and treat silently-inactive ASINs as possible IP flags; zero-tolerance brands (Nike, Apple,
  Disney, LEGO, OtterBox, Funko, Beats, Hasbro); valid → remove/retraction/POA/keep docs 180d,
  invalid → notice-dispute@amazon.com; DMCA counter-notice is copyright-only with a 10–14-day legal
  clock. (text-sources/2026-07-06/sellerapp-amazon-ip-complaints.md)
- **arXiv 2602.23716 ProductResearch (Alibaba)** [practitioner] — e-commerce deep research needs web +
  structured-catalog fusion (independent confirmation of the scout_pro thesis); a Supervisor state machine
  verifies every plan/tool-call/report step; RACE 31.78→45.40, product coverage >3×. Liftable now:
  step-level verification for scout reports/Ask, rubric-per-query eval.
  (text-sources/2026-07-06/arxiv-2602-23716-productresearch-ecommerce-agents.md)
- **2 videos queued** — X6JjPUZd4xw (overlooked-listings KPF sourcing), 9QGs4hfKrhY (SAS
  profiles/settings/panels configuration — feeds fba-selleramp-analyst).

### Rolling summary — most useful recent takeaways
- **Self-learning-RAG recipe:** FLAIR (arXiv 2508.13390, Microsoft, deployed in Copilot) — two-track
  ranking blending vector similarity with feedback-learned indicators; synthetic questions bootstrap it
  before real thumbs exist. Pair with RAGVA (2502.14930): 8 production-RAG challenges → continuous
  validation over spec-based testing. ProductResearch (07-06) adds the supervisor-verification pattern.
- **Buy discipline:** EntreResource (07-05) — strict order: scan → eligibility → red flags →
  fees/history → quantity LAST; always subtract a return allowance ("sellable margin, not spreadsheet
  margin"). Aura (07-05) — 3-month inventory rule, ≤20% capital per ASIN, margin stacking 40%→68% ROI.
- **Keepa/SAS reading:** SAS Charts panel = licensed Keepa data inside every lookup — rank history
  sanity-checks the sales estimate, price history separates normal price from spike (07-05). BSR is a
  filter, not a decision.
- **Fees/policy watch:** 2026 referral/FBA fee update + Apr 17 3.5% fuel surcharge (06-30/07-03); prep now
  fully seller-owned (07-06); the FNSKU-mandate claim is the biggest open [policy] question.
- Full detail: `research-inbox/research-insights.md` (per-topic, dated) and `research-inbox/digests/`
  (per-day).
