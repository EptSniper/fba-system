# System Blueprint — the working, synced OA loop

**Date:** 2026-07-01 · **Author:** Claude (Cowork), from live web research (all claims cited in the research notes below) · **Executor:** Claude Code for anything that is code; Mehmet for accounts/purchases.
**Companion doc:** `SCOUT_EXPERT_UPGRADE_BRIEF.md` (the scorer/UI expertise prompts). This doc is the layer above it: how every piece connects into one loop, what to buy, and in what order.

---

## 1. The loop we are building

```
        DISCOVERY                    ENRICHMENT               JUDGMENT
  deal feeds ("which store    →   Keepa product data    →   scout gates + scoring
  is hot today") + Keepa          (3 tokens/ASIN gets       + explain-why verdict
  Product Finder + storefront      90-day stats, BB share,   + SP-API "am I allowed"
  stalking + manual finds          fees, OOS%, sales)        + SP-API exact fees
        ↑                                                        ↓
   LEARNING                                                 HUMAN REVIEW
  threshold-tuning report     ←   outcomes recorded    ←   Discord digest + Find page
  (suggestions only, human        (sold price, days,       review queue — Mehmet
  applies via brain update)        realized ROI)            approves/rejects w/ reason
```

Everything reads thresholds from **ai-brain.json** (single source of truth) and everything writes state to **Supabase** (single state store). That's the whole sync story — two canonical stores, everything else is a view.

## 2. The research changed three assumptions — read this before Phase 2

1. **Keepa's stats object is far richer than the scout uses — and it's nearly free.** One product request (1 token, +2 with `buybox=1` → **3 tokens/ASIN**) already includes: 90-day averages (`avg90[]`), 90-day lows (`minInInterval`), offer-count history, **per-seller Buy Box share** (`buyBoxStats` → Amazon's % won), **Amazon out-of-stock percentage** (`outOfStockPercentage90[0]`), sales-rank drops per 30/90/180/365 days, variation family (`parentAsin`), and **fee data**: `fbaFees.pickAndPackFee` + `referralFeePercent` per ASIN. Full 365-day history costs no extra tokens (`history=True`, it's still the 1-token base). Consequence: the Phase 2 detectors in the upgrade brief (penny war, seasonality, in-stock band, all-time cliff) are cheaper than assumed, and Keepa can auto-fill the FBA fee and referral rate on the Find page without SP-API.
2. **SP-API self-authorization is realistic for you.** A solo seller on a Professional plan registers as a **private developer** (Seller Central → Apps and Services → Develop Apps / Solution Provider Portal), self-authorizes, and gets a refresh token — no company required, typically days not months. The two killer endpoints are **Listings Restrictions** (`getListingsRestrictions` — "can *my* account list this ASIN?", 5 req/s) and **Product Fees** (`getMyFeesEstimateForASIN` — Amazon's own fee estimate, 1 req/s). Neither is a restricted role. This is the missing "am I allowed" half of every verdict.
3. **SellerAmp has no API** — its only outbound integration is **Google Sheets export**. So SAS stays the manual verification cockpit; if we ever want its analyses in the loop, we ingest the Sheets export. Don't plan around a SellerAmp API that doesn't exist.

## 3. Tool mastery — the facts that matter (verified July 2026)

**Keepa** (the data backbone)
- Two products: the €19/mo Data subscription (web tools + trickle API) and standalone **API plans: €49/mo = 20 tokens/min** (≈28,800 tokens/day), €129/mo = 60/min. Tokens expire 60 min after generation (max bank ≈ 1,200 on €49) — so the scout must **drip, not burst**: a 2,000-ASIN scan at 3 tokens each = 6,000 tokens ≈ 5h of slow polling with `wait=True`. That's fine for a nightly run.
- Budget check: scan 2,000 ASINs/day (6,000 tokens) + deep-enrich finalists ≈ **~7,500 tokens/day ≈ 26% of the €49 plan's daily generation**. The €49 plan is enough.
- **Product Finder API** (`/query`) replicates the reverse-sourcing stack exactly: `brand`, BSR range (`current_SALES_lte`), `availabilityAmazon` (Amazon OOS), `current_COUNT_NEW_gte` (min offers), and `deltaPercent90_BUY_BOX_SHIPPING` (price vs 90-day avg — the "value buy" sort).
- **Storefront stalking API**: the `/seller` endpoint returns a seller's full ASIN list (1 token base, ~+9 when the storefront list is delivered — verify with one call). This automates the "save winning seller IDs" playbook.
- Python `keepa` lib (v1.4.4, Feb 2026) is maintained — keep using it; log `tokensConsumed`/`tokensLeft` from every response as budget telemetry.
- Gotchas: `offers` and `buybox` don't combine (offers supersedes); prices are integer cents; -1 = no data; a drained key can look like "no results" — alert on `tokensLeft`.

**Amazon SP-API** (the account-truth backbone)
- Register once (free), self-authorize, store LWA client id/secret + refresh token in `API_KEYS.env`/`scout/.env` (server-side only). Access tokens last 1h, refreshed from the refresh token. Client secrets must be rotated periodically — build the renewal into the runner's warning system.
- Pre-buy endpoints, all ordinary roles: Listings Restrictions (5/s), Catalog Items incl. **UPC→ASIN lookup** (2/s), Product Fees (1/s), Product Pricing (0.5–1/s), FBA Inventory (2/s), Finances — **realized** fees per order (0.5/s). At registration tick Product Listing + Pricing + Amazon Fulfillment + Inventory + Finance roles.
- Finances API is the honest ROI source for the learning loop: realized referral + FBA fees per settled order, not estimates.

**SellerAmp / IP Alert** — manual cockpit. SAS $19.95–$49.95/mo; its Google Sheets export is the integration surface. IP Alert ($100/yr) or SellerAmp's built-in IP flags cover complaint-risk brands; the scout's IP-cliff detector is the free approximation.

**Deal feeds** (discovery intelligence, optional): FMTC Solopreneur $95/mo (web UI, no API; API tier ≈ $325/mo — not yet worth it), **LinkMyDeals free tier (25 calls/day)** is the right starting point. Both return merchant-level sales/coupons, not UPC-level products — use them to decide *which store to scan today* (the "source where the deal is TODAY" rule), not as lead lists.

**Commercial benchmark** (what we're replicating vs buying): Tactical Arbitrage $89–129/mo, SourceMogul $97/mo, BuyBotPro $17.95–54.95/mo, OABeans lead lists $108–238/mo. Their scoring stage is nothing beyond our rule engine + Keepa. The one thing NOT worth rebuilding solo is their 1,400-site crawling + UPC-matching infrastructure — our substitutes are Keepa Product Finder, storefront stalking, deal-feed store intelligence, and manual finds through the Find page. If discovery volume ever becomes the bottleneck, buying one month of TA is cheaper than building a crawler.

## 4. The sync architecture (how "everything works together")

Two canonical stores, strict direction of flow:

1. **ai-brain.json = the rules.** Every threshold, guard, brand list, fee table. Written only via the fba-brain-updater conventions. Consumers: `scout/config.py`, control-center (live read locally, bundled `hub-data/` on Vercel), skills. **Sync step:** any brain change re-syncs `control-center/hub-data/` in the same commit — this is already the standing rule; the runner (below) will also verify the two files match and warn on drift.
2. **Supabase = the state.** Knowledge corpus (live: 97 docs / 1,316 chunks) + business tables (`leads`, `keepa_snapshots`, `decisions`, `outcomes`, `storefronts`, plus new `runs`). The scout becomes a **stateless script**: any machine with the `.env` (your PC, later a $5 VPS) produces identical behavior because all state lives in Supabase. Idempotency via natural-key upserts (`asin + snapshot_date`), so re-running a failed day is always safe.
3. **The runner** (one entry point, `scout/run_daily.py`): drip-scan → gate → enrich survivors → score with explain-why → upsert leads + snapshots → write a `runs` row (started/finished/counts/tokens used) → post ONE batched Discord embed digest → ping **healthchecks.io** (free) as a dead-man's switch. If the machine never woke up, healthchecks alerts Discord — a failure webhook alone can't report a machine that's asleep. Windows Task Scheduler with "run when missed" is acceptable to start; move to a ~$5/mo VPS when a missed morning run starts costing real deals.
4. **The dashboard is a view, not a store.** Find page verdicts and the review queue read/write Supabase through same-origin API routes; nothing secret in the browser.
5. **The learning loop closes through capture:** every lead stores the frozen pre-decision feature snapshot + explanation; your approve/reject adds a **reason code** (IP risk / price war / slow mover / bad match / gated / thin margin); realized outcomes come from the Log page and later the Finances API. Research-backed small-data rule: stay rule-based and tune thresholds against reason-code frequencies first; fit a model only past ~several hundred decisions, calibrated with **Platt/sigmoid scaling** (isotonic overfits under ~1,000 samples) — this matches scout_pro's existing design.

## 5. Monthly budget (decision for Mehmet, not Claude Code)

| Tier | What | Cost |
|---|---|---|
| Now (manual + Phase 1) | SellerAmp + Keepa €19 web (you likely have these) | ~$40/mo |
| Automation on (Phase 2) | + **Keepa API €49/mo** | ~$95/mo |
| Hardened (Phase G) | + VPS ~$5/mo + healthchecks free + Supabase free | ~$100/mo |
| Optional later | LinkMyDeals free → FMTC $95 · IP Alert $100/yr · one-off TA month $89 | as needed |

Break-even sanity check: at your $3/unit minimum profit, ~$100/mo of tooling = ~35 units/mo to cover tools. The comparators (TA $89, SourceMogul $97, OABeans $108+) confirm this is the going rate for serious OA, and yours compounds into an owned system.

## 6. Ordered roadmap — the master sequence

Phases 1–3 = `SCOUT_EXPERT_UPGRADE_BRIEF.md` prompts. G-prompts below are new glue work.

| # | What | Needs | Who |
|---|---|---|---|
| 1 | Brief Prompts 1.1 → 1.2 → 1.3 (expert rules + Find-page parity + Save-as-lead) | nothing | Claude Code |
| 2 | **Buy Keepa API €49 plan**; key into `scout/.env` + `API_KEYS.env` | money | Mehmet |
| 3 | Brief Prompt 2.1 + 2.2 — **paste the "Keepa facts" box below together with them** | Keepa key | Claude Code |
| 4 | Prompt G1 — Supabase state store + idempotent runs | nothing | Claude Code |
| 5 | Prompt G2 — daily runner + heartbeat + Discord digest; schedule it | healthchecks.io signup (free) | Claude Code + Mehmet |
| 6 | **Register SP-API private developer** (Seller Central → Apps and Services); self-authorize; keys into `API_KEYS.env` | Professional account (have) | Mehmet |
| 7 | Prompt G3 — Listings Restrictions + getMyFeesEstimate wired into pipeline + Find page | step 6 | Claude Code |
| 8 | Brief Prompt 3.1 — learning loop closure | leads flowing | Claude Code |
| 9 | Prompt G5 — continuous self-improvement loop (auto-proposals, human-applied) | steps 4–5 | Claude Code |
| 10 | Optional: G4 SellerAmp Sheets ingest · LinkMyDeals free feed · VPS move | as desired | mixed |

Run 10–20 real manual analyses through the Find page during steps 1–5 — the loop needs your decisions as fuel, and it validates the UX before automation scales it.

### Keepa facts box (paste along with Brief Prompts 2.1/2.2)

```
Verified Keepa API facts to use (July 2026): base product request = 1 token and INCLUDES full
csv history and the stats object; buybox=1 adds +2 tokens; offers supersedes buybox (never
combine); max 100 ASINs/batch (20 when offers used); tokens expire 60 min after generation so
drip with wait=True, never burst. Prefer the stats object over recomputing from history:
avg90[] (90-day avgs), minInInterval (90-day low), current[11]/avg90[11] (offer counts),
buyBoxStats map sellerId→percentageWon (Amazon share = key ATVPDKIKX0DER),
outOfStockPercentage90[0] (Amazon in-stock band), salesRankDrops30/90/180/365 (sales est),
parentAsin (variation flag), fbaFees.pickAndPackFee (cents, may be null) and
referralFeePercent (per-ASIN referral rate — use to auto-fill fees, fall back to the brain's
category table). Product Finder /query filters: brand, current_SALES_lte (BSR),
availabilityAmazon (Amazon OOS), current_COUNT_NEW_gte, deltaPercent90_BUY_BOX_SHIPPING
(price vs 90-day avg), sort + perPage paging. Seller endpoint /seller with storefront=1
returns a seller's asinList (storefront stalking) at ~1 token (+~9 when list delivered —
verify via tokensConsumed and record actual costs). Log tokensLeft + tokensConsumed from
every response into the runs telemetry; alert when tokensLeft is low because a drained key
silently looks like "no results". Python keepa lib v1.4.4+ is current; use raw=True as the
escape hatch for unwrapped filters.
```

### Prompt G1 — Supabase as the single state store, idempotent runs

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Use
amazon-fba-oa:fba-database-expert for schema/RLS design and amazon-fba-oa:fba-coder for the
Python changes.

Goal: make the scout stateless so any machine with .env runs it identically; Supabase is the
only state store. Existing tables: leads, keepa_snapshots, decisions, outcomes, storefronts.

1. Add a runs table (id, started_at, finished_at, status, asins_scanned, candidates_gated,
   leads_upserted, tokens_consumed, tokens_left_end, error_summary, host). Migration via the
   Supabase MCP/SQL, service key server-side only, RLS consistent with existing business
   tables.
2. Make lead + snapshot writes idempotent: natural-key unique indexes (asin + snapshot_date
   for keepa_snapshots; asin + source for leads' active row) and upsert-on-conflict, so
   re-running a failed day never duplicates. Migrate the SQLite-only state the pipeline
   still keeps (dedupe/seen lists, feedback) into Supabase equivalents, keeping SQLite as a
   read-only fallback when SUPABASE keys are absent (current no-key silent no-op behavior
   preserved).
3. Every run writes exactly one runs row (including failures — wrap the cycle in
   try/finally). Include Keepa token telemetry (tokensConsumed total, tokensLeft at end).
4. Tests: upsert-idempotency (run twice, same row count), runs row on simulated failure,
   no-key fallback still passes existing pipeline-memory tests. Full suite green. Journal
   entry via fba-session-journal.
```

### Prompt G2 — one runner, heartbeat, honest digest

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Use
amazon-fba-oa:fba-coder; check the run/report design with amazon-fba-oa:fba-architect if
anything deviates from this spec.

1. scout/run_daily.py: single entry point — drip-scan discovery (Product Finder stack per
   friendly brand from ai-brain.json discovery.productFinderStack) → hard gates on the cheap
   3-token stats call → enrich survivors → score with explain-why → Supabase upserts (G1) →
   one batched Discord embed digest (top candidates with verdict + top reasons + tokens used
   + link to the Find page; respect webhook limits by sending ONE message) → finally ping a
   HEALTHCHECK_URL (healthchecks.io) on success, and its /fail endpoint on failure. All
   URLs/keys from env; no secrets in code or logs.
2. Drip pacing: use the keepa lib's wait=True token handling; target completing within the
   plan's refill rate; abort gracefully (and say so in the digest + runs row) if tokens run
   out mid-scan.
3. Brain-drift check at startup: warn in the digest if control-center/hub-data/ai-brain.json
   differs from learning-hub/data/ai-brain.json.
4. A Windows Task Scheduler setup note (schtasks command with "run when missed" enabled) in
   scout/README.md, plus the equivalent cron line for a future VPS.
5. Tests: digest formatting with 0 candidates (honest empty message, never fake), heartbeat
   fail-path called on exception, drift-warning logic. Full suite green. Journal entry.
```

### Prompt G3 — SP-API: "am I allowed?" + exact fees in the loop

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Use
amazon-fba-oa:fba-architect to place the module boundary (suggest scout/spapi.py used by both
pipeline and a new control-center route), amazon-fba-oa:fba-coder to implement,
amazon-fba-oa:fba-compliance-checker's vocabulary for verdict wording.

Pre-req (already done by Mehmet): self-authorized private SP-API app; LWA client id/secret +
refresh token in scout/.env (+ API_KEYS.env registry). Server-side only, never in the browser.

1. scout/spapi.py: LWA token refresh (1h cache), then wrappers with per-endpoint rate
   limiting and backoff: getListingsRestrictions(asin, condition=new_new) → ALLOWED /
   APPROVAL_REQUIRED / NOT_ELIGIBLE (+ approval links), getMyFeesEstimateForASIN(asin,
   price) → referral + FBA fee, and Catalog Items UPC→ASIN lookup. Respect limits (5/s, 1/s,
   2/s) with a shared limiter.
2. Pipeline: after hard gates, check restrictions for survivors; NOT_ELIGIBLE → hard reject
   ("account-gated"), APPROVAL_REQUIRED → keep but tag verdict "needs ungating" (the
   explanation must show it). Replace the estimated FBA fee with getMyFeesEstimate when
   available; keep the estimate as fallback and record which source was used per lead
   (honest data flow).
3. Control-center: extend /api/asin-lookup (from Brief 2.2) to include the restriction
   verdict + exact fees, with an honest "SP-API not configured" state. Find page shows an
   eligibility chip: ALLOWED / NEEDS APPROVAL / NOT ELIGIBLE / NOT CHECKED.
4. Never claim eligibility it didn't verify; cache restriction results per ASIN for 7 days
   in Supabase (they're account-specific and slow-changing).
5. Tests with mocked SP-API responses for all three restriction outcomes + fee fallback.
   Full suites green, typecheck + build. Journal entry.
```

### Prompt G4 (optional) — SellerAmp Google Sheets ingest

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Use
amazon-fba-oa:fba-coder. Context: SellerAmp has no API; its Google Sheets export is the only
integration surface. Mehmet has configured SAS to export analyses to a Google Sheet and will
provide read access (service-account or published-CSV URL — prefer the simplest: File > Share
> publish the sheet as CSV and put the URL in scout/.env as SELLERAMP_SHEET_CSV_URL).

Add scout/ingest_selleramp.py: pull the CSV, map SAS columns (ASIN, cost, sell, profit, ROI,
eligibility flags) into leads upserts tagged source="selleramp", dedupe against existing
leads by ASIN, and include them in the next digest under "manually analyzed in SAS". Tests
with a fixture CSV. Journal entry.
```

### Prompt G5 — continuous self-improvement loop (proposals automatic, application human)

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Use
amazon-fba-oa:fba-architect to confirm the boundary (proposals are generated automatically;
ai-brain.json is ONLY changed by a human-approved fba-brain-updater step), then
amazon-fba-oa:fba-coder.

Goal: the tools' intelligence should improve continuously without waiting for someone to
remember to analyze — but no rule change ever applies itself.

1. scout/propose_updates.py, run automatically at the END of every daily runner cycle (G2):
   a. Outcome-driven proposals: run the Prompt 3.1 tuning analysis on whatever
      decisions/outcomes exist so far (works from n=1; states sample size honestly per
      finding, e.g. "2/2 REVIEW leads with offers>20 lost money — sample too small to act").
   b. Data-driven proposals: compare recent run telemetry against the brain — e.g. a friendly
      brand producing 0 gate-survivors for 14 straight days (candidate for review), a brand
      repeatedly IP-cliff-flagged (candidate for the avoid list), observed Keepa token costs
      differing from assumptions, gates that reject 100% or 0% of candidates (dead or
      toothless thresholds).
   c. Knowledge-driven proposals: when the daily research pipeline lands new documents,
      run knowledge-rag/ask.py queries for changed OA rules (fees, thresholds, policy) and
      diff the answers against the brain's current values; differences become proposals with
      the citation attached.
2. Output: learning-hub/tracking/brain-proposals.md — append-only, dated blocks, each
   proposal with {current value, proposed value, evidence + sample size or citation,
   confidence, exact ai-brain.json key}. The daily Discord digest ends with "N new brain
   proposals pending" when any exist. NEVER edit ai-brain.json from this script.
3. Application path (human): Mehmet reviews the file and tells Claude (any session) "apply
   proposal X" — the fba-brain-updater skill then makes the edit with provenance, bumps
   updated, re-syncs hub-data, and marks the proposal applied in brain-proposals.md with the
   date. Add this workflow note to the file header and to scout/README.md.
4. Tests: proposal generation from fixture telemetry (dead gate, cold brand, token-cost
   drift), honest small-sample wording, and a guard test asserting propose_updates.py has no
   code path that writes to ai-brain.json. Full suite green. Journal entry.
```

**Why proposals aren't auto-applied:** ai-brain.json drives every verdict in both tools; a silently wrong threshold corrupts every decision after it. The loop stays fast because applying a proposal is one sentence to Claude — but a human eye stands between statistics and the rules. With small data (your first months), automated tuning would mostly chase noise; the sample-size wording in every proposal keeps that visible.

## 7. What NOT to do (research-backed)

Don't build a retail-site crawler (that's TA's moat — rent it if ever needed). Don't buy FMTC's API tier yet ($325/mo — the free LinkMyDeals tier + manual deal awareness covers "which store today" at your volume). Don't rely on GitHub Actions cron for the daily run (documented delays + silent drops). Don't fit an ML model before several hundred labeled decisions; when you do, sigmoid calibration, not isotonic. Don't combine Keepa `offers` with `buybox`. And nothing auto-buys — the review queue is the product, not a bottleneck.

## 8. Unverified items (check cheaply, don't assume)

Exact Keepa token costs for `offers`/`rating`/Product Finder/storefront delivery (read `tokensConsumed` on first live calls and write the real numbers into the brain); whether self-authorized SP-API refresh tokens hit the 365-day re-auth (if calls ever return Unauthorized, regenerate in console — minutes); Keepa API tier prices came from third-party mirrors of the JS-only pricing page — confirm €49 in your account before paying; SellerAmp price tier current at purchase time.
