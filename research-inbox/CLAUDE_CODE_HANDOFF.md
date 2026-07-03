# Claude Code — daily research handoff

**This is the one file Claude Code should read every session.** A scheduled Cowork task
(`fba-daily-research`, ~7 AM daily) discovers new Amazon FBA/OA + system-building material, ingests text
sources, and **queues YouTube videos that it cannot transcribe itself** (the Cowork app can't call the
transcript API — you can). This file is rewritten by that task each run with what's pending and what it found.

_Last updated by the scheduled task: 2026-07-02._

---

## STANDING DAILY ACTIONS (do these when you open the project)

1. **Pull queued transcripts.** If the "PENDING" section below lists queued videos, run:
   ```
   python knowledge-rag/fetch_transcripts.py
   ```
   It reads `research-inbox/queue/*.json`, calls youtube-transcript.io with the key in
   `knowledge-rag/.env`, and writes transcripts into `research-inbox/transcripts/`. (If a video saves a
   `<id>__RAW.json` instead of a `.txt`, the API response shape differs — tell Mehmet or fix the parser.)
2. **Ingest new transcripts.** For each new file in `research-inbox/transcripts/` (not in `processed/`),
   follow `amazon-fba-oa/skills/fba-transcript-ingest/SKILL.md`: distill cited, actionable takeaways into
   `research-inbox/research-insights.md` (mark **[policy]** vs **[practitioner]**), append a line to
   `research-inbox/corpus-staging.jsonl`, record it in `research-inbox/research-manifest.json`, then move the
   file to `research-inbox/transcripts/processed/`.
3. **Feed the AI / get smarter.** Periodically (when staged material has accumulated and been eyeballed),
   merge reviewed insights into the maintained knowledge in `learning-hub/` and run the real `knowledge-rag`
   ingestion/embedding so `Ask`, the scout, and the control-center benefit. This is the "upload into memory +
   feed the AI" step — keep it a reviewed merge, not an automatic dump (honesty rule). **25 staged entries**
   now sit in `corpus-staging.jsonl` — a review-and-merge pass is getting worthwhile.
4. **Consult `SKILLS_INDEX.md`** before non-trivial work and use the matching `fba-*` skill for whatever
   you're doing — e.g. `fba-brain-updater` if today's findings should change a threshold in `ai-brain.json`.
5. **Post the Discord update.** After finishing the above, POST a short update using the webhook URL stored
   as `RESEARCH_DISCORD_WEBHOOK_URL` in `knowledge-rag/.env` (read the env var directly when posting — never
   print/paste the URL value anywhere, including this file). Summarize: how many new items today's scheduled
   run found (this run: **9** — 2 videos queued + 7 text sources staged), how many transcripts were
   fetched/ingested since the last update, and the current local-corpus vs live-Supabase document/chunk
   counts if they differ.
6. **Never** commit or print `knowledge-rag/.env` or any key. Cite sources. Don't auto-buy anything.

Full context for how these systems connect: `CLAUDE_CODE_GUIDE.md` (§3 "how the skills feed the systems").

---

## PENDING NOW

**Queued YouTube videos: both 2026-07-02 videos fetched + ingested (Claude Code, 2026-07-02 evening).**
IBXT2txZtJE (ungating guide) and rHCB-vSCWcI (SellerAmp SAS tutorial) were pulled, distilled into both
`research-inbox/research-insights.md` and `learning-hub/transcripts/insights.md`, moved to
`transcripts/processed/`, and copied into `learning-hub/transcripts/`. The real pipeline was run too —
`ingest.py` + `upload_to_supabase.py` — so they're chunked, embedded (local, $0), and LIVE in Supabase
(corpus grew 97→99 docs, 1,316→1,340 chunks; verified via a real Ask query). Only the known-stuck video
remains:

| videoId | title | queue file | status |
|---|---|---|---|
| TBFh9vFBq7k | Online Arbitrage Sourcing Using Keepa (ADVANCED TACTICS) | queue/2026-06-30.json | **stuck — LOGIN_REQUIRED at the API (documented 2026-07-01); needs manual re-fetch/re-check, not a parser bug** |

**Transcripts awaiting ingest: 0** — `research-inbox/transcripts/` holds only `README.md`, the
non-recoverable `TBFh9vFBq7k__RAW.json`, and `processed/` (all fetched transcripts move there once ingested).

**`corpus-staging.jsonl`: 27 lines** (25 as of earlier 2026-07-02 + 2 video entries added this pass). Staged
only — these are mostly TEXT articles/papers from 2026-06-30 through 07-02, a separate backlog from today's
videos. A full reviewed merge into `learning-hub/` + a real ingest/embed pass for that backlog is still
pending and getting more worthwhile as it grows.

**One fetch-failed [policy] source worth grabbing from a real browser:** Amazon Seller Central
"FBA product restrictions" help page (G200140860) — JS-rendered, WebFetch only got the shell. It's the
authoritative doc behind today's meltable/restrictions practitioner posts. If you pull it, ingest per the
usual text-source flow and flip its manifest status from `fetch-failed` to `ingested-staged`.

---

## WHAT'S BEEN FOUND (today first; full cited detail in `research-insights.md` + `digests/`)

**2026-07-02 — 7 new text sources staged:**
- **[practitioner]** **DD+7 cash flow** (novadata.io) — since Mar 12, 2026 disbursements run Delivery
  Date + 7 (+3–5 day bank transfer); reserve = 3–12% of recent revenue and grows with velocity; 5 cash
  leaks; CCC 60–120 days for FBA; a 4-number Monday routine (disbursement vs forecast, reserve WoW,
  days-of-inventory, rolling 28-day contribution margin/SKU).
- **[practitioner]** **Meltable window — active NOW** (sellerassistant.app) — meltables are FBA-inboundable
  only Oct 16–Apr 14; through Oct 15 any chocolate/gummy/wax lead is FBM-only; off-window arrivals get
  disposed at seller cost. (Official page G200140860 pending — see above.)
- **[practitioner]** **Keepa PF hacks** (talloakadvisors.com) — bulk-brand `###` list filter; Buy Box
  90-day-drop% −20…20 stability band; negative keywords; rankless-gem search (skip the rank filter);
  Chris Grant's Corridor method; URL-decode saved bookmarks to learn advanced queries.
- **[practitioner]** **2026 sourcing shifts** (boxem.com) — search-page/multi-pack sourcing (SellerAmp Quick
  View Simplified shows rank/FBA count on results pages); bulk ungate checking while storefront stalking;
  margin is created via coupon/gift-card/rewards stacking + reseller cert + tax-free prep center; check FBM
  for <1 lb items.
- **[practitioner]** **Dashboard patterns 2026** (artofstyleframe.com) — 4–6 KPI cards max; three states per
  component (content-shaped skeletons / honest empty / component-scoped error with retry — never a
  page-blocking modal); 256px sidebar + 64px rail; dense-table specs; override chart default palettes
  (WCAG). Confirms the control-center design system with concrete numbers.
- **[research]** **RAG eval survey** (arXiv 2504.14891) — the catalog to use when building the missing eval
  harness over `Ask`: retrieval-component vs generation/grounding metrics, RAG datasets + automated
  frameworks (ARES-style).
- **[research]** **R2C uncertainty quantification** (arXiv 2510.11483) — confidence via perturbed-retrieval
  answer stability (>5% AUROC gain); cheap calibration probe idea so `Ask` can flag weakly-grounded answers
  instead of sounding uniformly confident. Design input only.

**Rolling summary of the most useful earlier takeaways (2026-06-30 → 07-01):**
- **[policy]** 2026 US FBA fees +~$0.08/unit avg (Jan 15); **[practitioner]** separate ~3.5% fuel surcharge
  from Apr 17 on fulfillment fees; aged-inventory surcharge starts ~181 days; Amazon ended its own FBA prep.
- **[policy]** SP-API **Listings Restrictions API** = the concrete path to automate eligibility checks
  (not wired up); IP enforcement = copyright/trademark/patent via Brand Registry tooling.
- **[practitioner]** Keepa: filters are AND — don't over-constrain; prefer 90-day avg BSR; offer-count
  TREND > level; sharp offer-count cliffs = IP-complaint risk; check break-even price before anything else.
- **[practitioner]** SAS Masterguide: "!" on Estimated Sales = variation-shared figure; alerts mean
  investigate, not auto-skip; BSR is category-relative; model coupon stacking in the Profit Calculator.
- **[practitioner]** Sourcing doctrine across sources: storefront stalking + reverse sourcing first,
  "you make items profitable (discount stacking), you don't find them profitable", persistent lead bank +
  weekly capital allocation, buy the price cycle not clearance.

_The scheduled task refreshes this file every run. If the date above is stale, the task may not have run
(it only runs while the Claude desktop app is open, else on next launch)._
