# Research log

Running log of the daily research pipeline. Newest first. Each run appends: date, items found, items
ingested, transcripts processed, and anything skipped (already known). No secrets here.

<!-- The scheduled task appends entries below this line, newest first. -->

## 2026-07-04 (daily run)
- **9 new items** (within cap): **2 YouTube queued** to `queue/2026-07-04.json` (rdltezXxIrk Keepa PF
  tutorial; jeqFx9ZiOhg AMZ Prep every-fee-explained 2026) + **7 text sources** saved to
  `text-sources/2026-07-04/`, distilled into `research-insights.md`, staged in `corpus-staging.jsonl`
  (34 → 41 lines, JSON-validated): Ecom Circles 2026 OA guide, B2B Supplier Hub reverse-sourcing workflow,
  Stealth Seller storefront screen, The Selling Guys 750+ gated-brands tracker (Jul 1 update — flagged as
  fba-brain-updater review candidate), Eightx Xero/A2X setup, arXiv 2603.02153 (RAG-fusion gains neutralized
  by reranking — production counter-evidence), arXiv 2605.01664 (claim-level grounding harness for Ask).
- No transcripts to ingest (only the known-stuck TBFh9vFBq7k RAW). Claude Code had already pulled + ingested
  yesterday's 3 queued videos earlier today. Dups skipped: 3 videos already in learning-hub/transcripts,
  1 near-duplicate video, ~7 previously-ingested URLs. Manifest 42 → 51 items; digest written;
  `CLAUDE_CODE_HANDOFF.md` refreshed (2 videos pending pull).

## 2026-07-03 (daily run)
- **10 new items recorded** (7 usable, within cap): **3 YouTube queued** to `queue/2026-07-03.json`
  (PydYmi56Sso Flips4Miles full 2026 OA course; XdUGuD4ouKI Mar-2026 Keepa beginner-to-expert;
  Cflrv_y9lSA advanced Keepa Parameter Method — covers the gap left by stuck TBFh9vFBq7k) + **4 text
  sources** saved to `text-sources/2026-07-03/`, distilled into `research-insights.md`, staged in
  `corpus-staging.jsonl` (27 → 31 lines, JSON-validated): FBA Lead List modern-sourcing/lead-bank piece,
  Beancount seller chart-of-accounts guide, Seller Snap consolidated 2026 fee map, arXiv 2501.07391
  RAG best-practices ablation.
- 3 failures/skips recorded honestly: SellerAmp blog (thin video-wrapper → queued the video instead),
  BowTiedSlinger (paywall), Lushbinary RAG production guide (JS-rendered, fetch-failed — browser re-fetch
  candidate). Dups skipped: 3 videos already in learning-hub/transcripts + previously ingested URLs.
- No transcripts to ingest (only the known-stuck TBFh9vFBq7k RAW). Manifest 29 → 39 items, digest written,
  `CLAUDE_CODE_HANDOFF.md` refreshed (3 videos now pending pull).

## 2026-07-02 (daily run)
- **9 new items** (within the 10 cap): 2 YouTube queued to `queue/2026-07-02.json` (2026 ungating guide
  IBXT2txZtJE; May-2026 SAS full tutorial rHCB-vSCWcI) + **7 text sources** fetched, saved to
  `text-sources/2026-07-02/`, distilled into `research-insights.md`, and staged in `corpus-staging.jsonl`
  (18 → 25 lines, JSON-validated): Nova DD+7 cash-flow playbook, Tall Oak Keepa-PF hacks, Boxem 2026
  sourcing rules, Seller Assistant meltable policy (we're in the Apr 15–Oct 15 FBA-restricted window NOW),
  Art of Styleframe dashboard patterns, and two RAG papers (eval survey arXiv 2504.14891; R2C uncertainty
  quantification arXiv 2510.11483).
- 1 fetch failure recorded: official Seller Central "FBA product restrictions" (G200140860) is JS-rendered —
  flagged in the manifest for a browser-equipped session to pull.
- No transcripts to ingest (only the known-stuck TBFh9vFBq7k RAW file). Manifest updated (19 → 29 items),
  digest written, `CLAUDE_CODE_HANDOFF.md` refreshed (2 videos now pending pull).

## 2026-07-01 (second run, ~22:19 UTC)
- Second scheduled-task run same day (after the transcript-ingest correction run below). 7 items were
  already logged today (near the 10/day cap), so this run searched a few underrepresented topics
  (SellerAmp SAS advanced, SP-API restrictions docs, Next.js dashboard patterns) and added **2 new text
  sources**: SellerAmp SAS Masterguide 2026 [practitioner] and the SP-API Listings Restrictions API docs
  [policy] — both fetched, saved to `text-sources/2026-07-01/`, distilled into `research-insights.md`, and
  appended to `corpus-staging.jsonl` (16 → 18 lines, JSON-validated).
- Next.js dashboard search only surfaced template-marketing listicles; a follow-up search found more
  substantive Suspense/streaming material but no single authoritative fetchable article worth staging —
  skipped rather than stage something thin.
- `research-inbox/transcripts/` re-checked: nothing new to ingest (only README + the already-documented
  non-recoverable `TBFh9vFBq7k__RAW.json`).
- Updated `research-manifest.json` (both items added, `updated` bumped) and refreshed
  `CLAUDE_CODE_HANDOFF.md`. Day total: **9 new items** (3 YouTube queued + 6 text staged), under the 10/day cap.

## 2026-07-01 (transcript ingest)
- Ingested the 6 successfully-fetched YouTube transcripts sitting in `transcripts/` (queued 2026-06-30/07-01,
  pulled earlier by `fetch_transcripts.py`): OUGc0aiT7l4, pP-zQ4-u370, MAFpI4Wdd4w, TZyBG1_-jLM, HXYMH_l6Ufk,
  V0lMedQJzmQ. Read each full transcript, cross-checked against `learning-hub/playbooks/field-sops.md`,
  `sourcing-playbook.md`, and `ai-brain.json`'s criteria, and confirmed real distilled entries already existed
  under "Amazon FBA / online arbitrage" and "Sourcing & finding products" in `research-insights.md` (2026-07-01
  dated bullets) — no new duplicate entries added. All 6 `.txt` files were already moved to
  `transcripts/processed/`.
- **`corpus-staging.jsonl` count correction:** the file holds **16 lines**, not the 10 the 2026-07-01 log entry
  below claims. The 6 lines beyond that 10 are the real distilled entries for the 6 YouTube transcripts above
  (verified today — full title/url/topic/source_type/summary schema matching the text-source lines, not
  one-line placeholders). No placeholder lines remain; nothing further to replace.
- **TBFh9vFBq7k ("Online Arbitrage Sourcing Using Keepa (ADVANCED TACTICS)") — investigated, not recoverable.**
  Only `transcripts/TBFh9vFBq7k__RAW.json` (~1.2MB) exists. Opened and parsed it: it is actually the **full
  batch response for all 7 queued videos** (confirmed via each element's `id` field), in the same order as the
  queue/manifest. The first 6 elements are the videos above with complete `tracks[].transcript` text (already
  ingested). The 7th element — this video — has empty `id`/`title`/`tracks`, `playabilityStatus.status =
  "LOGIN_REQUIRED"`, `failedReason = "PLAYABILITY_STATUS_NOK"`. This is a genuine upstream fetch failure (the
  source video was inaccessible to the transcript API at fetch time), not a JSON-shape/parsing problem — there
  is no transcript text anywhere in the file to recover. Left as-is; **needs a manual re-fetch** of just this
  videoId (re-run `fetch_transcripts.py` once the access issue clears, or verify the video is still public).
- Updated `research-manifest.json`: the 6 processed videos' status changed from `ingested-staged`/`queued` to
  `transcript-processed`; TBFh9vFBq7k changed from `queued` to `fetch-failed` with a note explaining why and
  what's needed. Refreshed `CLAUDE_CODE_HANDOFF.md`'s "PENDING NOW" section (was stale — still said 7 queued /
  0 ingested).
- Did not touch `knowledge-rag/corpus/` or Supabase — corpus-staging.jsonl remains staged-only pending the
  human-reviewed merge step. Did not touch `scout/`, `scout_pro/`, or `control-center/`.

## 2026-07-01
- Found 7 new items: 3 YouTube (queued in `queue/2026-07-01.json`) + 4 text sources (fetched, distilled, staged).
- Text: 3 [practitioner] OA/finance (Seller Labs restricted-products/ungating; FBA Mogul Keepa Product Finder filters;
  AMZ Prep 2026 fees — confirms the Apr-17 ~3.5% fuel surcharge flagged 6-30) + 1 [practitioner] system-build
  (arXiv 2509.20415 Online-Optimized RAG). Spread across sourcing, ungating, Keepa, finance, build-the-system.
- Transcripts processed: 0 (none dropped). Skipped dups: 3 titles already in `learning-hub/transcripts/`
  (MASTERCLASS 2026; "Storefront Stalking is NOT profitable"; "Ultimate OA Sourcing Guide") + 1 near-dup videoId.
- Staged to `corpus-staging.jsonl` (4 lines → 10 total) + `research-insights.md`; embed/upload still PENDING.
- Ran ~00:00 UTC; used 2026-07-01 as TODAY (prior digest was 6-30). Manifest was truncated by an edit/OneDrive
  collision and rebuilt+validated (17 items). Next: run `python knowledge-rag/fetch_transcripts.py`.

## 2026-06-30
- Found 10 new items: 4 YouTube (queued in `queue/2026-06-30.json`) + 6 text sources (fetched, distilled, staged).
- Text: 2 Amazon [policy] docs (2026 fee update; IP/Report-a-Violation), 1 [practitioner] finance guide
  (Eightx FBA bookkeeping), 3 [practitioner] system-build (Databricks chunking; arXiv 2407.01219; arXiv 2506.00054).
- Transcripts processed: 0 (none dropped). Duplicates skipped: material already in `learning-hub/transcripts/`.
- Staged to `corpus-staging.jsonl` (6 lines) + `research-insights.md`; embedding/upload still PENDING (reviewed step).
- Next: run `python knowledge-rag/fetch_transcripts.py` to pull the 4 queued transcripts for next-run ingest.
