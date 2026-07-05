# Top-100 Deal Watch — daily 9 PM ET, off-PC, $0

**Date:** 2026-07-04 · **Author:** Claude (Cowork), from verified web research · **Executor:** Claude Code (Prompts T1–T3); Mehmet: one GitHub repo secret setup (~10 min, free).
**The registry:** `learning-hub/data/top100-sources.json` — 100 ranked stores in 3 tiers, each with its FREE, ToS-clean detection method, cancel-risk/IP flags, and a dead-list so no scraper slots are wasted. This file is the single source; the deal finder reads it, and edits follow brain-updater conventions.

## 1. How the free detection actually works (no paid tools, ever)

Research verdict: you don't need to scrape 100 stores — three free aggregate signals cover almost everything, topped up with polite official-page checks:

1. **Slickdeals search RSS** (verified pattern: `newsearch.php?...&rss=1&q=<store>`) — one mechanism covers effectively all 100 stores with community-vetted deals. This is the workhorse.
2. **Official clearance/deal pages** — Home Depot's Special Buy of the Day, Chewy deals, B&H Deal Zone, LEGO sales page, Shopify sale collections… ONE polite fetch per day each (robots.txt respected, honest User-Agent, conditional GET). Only for Tier 1 + select Tier 2/3.
3. **Reddit deal-sub RSS + DealNews RSS + Woot's official free API** — cross-source confirmation and closeout signal.
4. Later, free after approval: **Best Buy API** (key pending) and **Impact/CJ affiliate catalogs** (applications pending) upgrade precision (UPC + exact prices) without changing the architecture.

Tier scheduling keeps it polite and fast: Tier 1 checked daily via RSS + clearance pages; Tier 2 daily via RSS only (clearance pages weekly rotation); Tier 3 weekly rotation + RSS mentions. Total runtime target: under 5 minutes.

## 2. Where it runs: GitHub Actions (free, verified July 2026)

- Private repo, **2,000 free Linux minutes/month** — this job uses ~8%. No card, no server.
- Secrets (Supabase key, Discord webhooks) live in encrypted Actions secrets.
- **Exact 9 PM ET year-round:** GitHub cron is UTC-only, so the workflow schedules BOTH `17 1 * * *` and `17 2 * * *` with a first step that exits unless `TZ=America/New_York date +%H` = 21 — one ~10-second wasted run per day, exact 9 PM in both EST and EDT. The `:17` offset dodges the documented top-of-hour delays.
- Two known quirks, both mitigated: best-effort scheduling (±10–30 min jitter — irrelevant for a nightly digest) and the 60-day inactivity auto-disable (defeated by the keepalive-workflow action).
- Your PC stays irrelevant: state lives in Supabase, alerts in Discord, so the 7:30 AM local scout run and the 9 PM cloud deal watch share one brain without ever needing each other online.
- Rejected free options (verified): PythonAnywhere free tier can't reach Discord (outbound whitelist); Render/Railway/Fly have no true free cron anymore; Oracle's free VM reclaims idle instances; Cloudflare's 10ms CPU cap doesn't fit. Runner-up if ever needed: Google Cloud Run Jobs + Scheduler (true $0, native ET timezone, but needs a card on file).

## 3. The flow, end to end

```
9:00 PM ET (GitHub Actions, free)          7:30 AM local (Task Scheduler, existing)
top-100 registry → RSS/page checks         scout run_daily: reads deal_hints FIRST →
→ normalize → dedupe → Supabase deals      Product Finder on hinted brands/categories
→ #retail-deals Discord digest             → falls back to its own discovery stack
→ deal_hints derived (brands/stores/cats   when hints are empty/exhausted → gates →
   seen in quality deals)                   analyst → digest. Control center reads the
                                            same Supabase tables (Deals page, Brief).
```

The "look here first" contract: the deal watch never *edits* the brain or the scout's config — it writes **hints** (data, not rules) to a `deal_hints` table with freshness timestamps. The scout consumes fresh hints as its FIRST discovery pass and reports in the digest which hints it followed; stale/empty hints = normal self-directed discovery, exactly as you asked. Matching deals to ASINs stays the D2/M4 matcher's job — this plan feeds it a nightly stream.

## 4. Prompts

### Prompt T1 — registry adapters + the nightly deal-watch job

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Read
learning-hub/data/top100-sources.json IN FULL — it is the single source for this feature —
and TOP100_DEAL_WATCH_PLAN.md §1+§3. Use amazon-fba-oa:fba-architect briefly (confirm:
registry-driven adapters, hints-not-rules boundary), then amazon-fba-oa:fba-coder.

1. scout/deals/registry.py: load + validate top100-sources.json (schema check, detect-code
   parser, flag handling: AVOID entries are signal-only and must NEVER become buy
   candidates — hard assert + test).
2. Generic adapters in scout/deals/sources/: (a) slickdeals_search.py — the per-store
   search-RSS pattern with the store's q value, polite 1 req/store/run, batch Tier 1+2
   daily; (b) clearance_page.py — generic polite page fetcher (robots.txt check cached
   per domain, honest UA "FBA-personal-deal-watch/1.0", conditional GET via ETag/
   Last-Modified stored in Supabase, 10s timeout, best-effort title/price extraction
   with an honest extraction_confidence field); (c) reddit_rss.py + dealnews_rss.py +
   woot_api.py for the aggregates (Woot key-gated skip if no key). Every VERIFY-flagged
   URL gets checked on first run: working URLs get verified:true written back to a
   registry-status file (NOT the registry itself — learning-hub/data/top100-status.json
   with last_ok/last_error per source), broken ones reported in the digest, never
   silently dropped.
3. Tier scheduling in the job: Tier1 = sd-rss + clr daily; Tier2 = sd-rss daily, clr on a
   weekly rotation (day-of-week hash); Tier3 = weekly rotation + aggregate mentions.
   Target < 5 min runtime; log per-source timing.
4. Everything lands in the existing deals table via the existing idempotent upserts
   (retailer+sku/url+price+day natural key — extend normalize.py for RSS-shaped items:
   title, url, price-if-present, store, source_signal, extraction_confidence).
5. Derive deal_hints after each run: migration 00N (NOT-APPLIED pattern) for deal_hints
   (brand, store, category, strength = count*quality, first_seen, last_seen, expires_at
   = last_seen + 72h). Hints come from deals matching friendly-list brands or registry
   categories; AVOID-flagged brands NEVER produce hints (test).
6. scout/deals/run_watch.py: standalone entry point (the cloud job) — registry → adapters
   → upserts → hints → ONE batched Discord embed to the retail_deals stream (top finds
   by discount %, per-tier counts, broken-source warnings, hint summary) → heartbeat
   ping (separate HEALTHCHECK_URL_DEALWATCH env, optional). Must run with ONLY:
   SUPABASE_URL, SUPABASE_SERVICE_KEY, DISCORD_WEBHOOK_RETAIL_DEALS, optional woot/
   bestbuy keys — no Keepa, no Anthropic, no local files beyond the registry (bundle it
   into the repo the job runs from).
7. Tests: registry validation, AVOID exclusion, adapter fixtures (RSS payloads, robots
   deny, ETag 304), tier rotation math, hints derivation + expiry, digest with broken
   sources. Full suite green. Journal entry.
```

### Prompt T2 — the free cloud runner (GitHub Actions, 9 PM ET exact)

```
Read CLAUDE.md, the latest AI_COLLABORATION_JOURNAL.md entries, and
TOP100_DEAL_WATCH_PLAN.md §2. Use amazon-fba-oa:fba-coder. Pre-req: T1 merged; the repo
already has git (Session 30).

1. Create deal-watch deployment in the SAME repo: .github/workflows/deal-watch.yml —
   triggers: schedule ["17 1 * * *", "17 2 * * *"] + workflow_dispatch; first step exits
   0 unless TZ=America/New_York date +%H equals 21 (exact 9 PM ET in EST and EDT);
   setup-python with pip cache; pip install -r scout/requirements-dealwatch.txt (create
   it: ONLY what run_watch.py needs — requests/feedparser etc., NOT the full scout
   stack, NOT mcp); run python scout/deals/run_watch.py with secrets from Actions env;
   add the keepalive-workflow marketplace action step (defeats the 60-day auto-disable).
   Concurrency group so overlapping runs can't double-post.
2. Document the one-time human setup in HUMAN_TODO.md (~10 min): create the PRIVATE
   GitHub repo (if the local git repo has no remote yet — git remote add + push; verify
   `git ls-files` still contains no env files BEFORE the first push and say so in the
   journal), then add Actions secrets: SUPABASE_URL, SUPABASE_SERVICE_KEY,
   DISCORD_WEBHOOK_RETAIL_DEALS, DISCORD_WEBHOOK_SYSTEM_HEALTH (failure alerts),
   optional WOOT/BESTBUY keys. Exact click path included.
3. Failure path: if run_watch.py exits nonzero, a final always() step posts a short
   failure embed to the system_health webhook (redacted message, no secrets in logs —
   verify Actions log output prints no secret values; rely on Actions' masking AND
   redact.py).
4. Local parity: the same run_watch.py stays runnable from Task Scheduler as a fallback;
   document both in scout/README.md.
5. Verify end-to-end: one workflow_dispatch run from the Actions tab (Mehmet clicks, or
   gh CLI if authenticated) producing a real digest in #retail-deals and a runs-row/
   status update in Supabase. Journal entry with the run link (no secrets).
```

### Prompt T3 — the scout looks where the deals are FIRST

```
Read CLAUDE.md, the latest AI_COLLABORATION_JOURNAL.md entries, and
TOP100_DEAL_WATCH_PLAN.md §3 (the hints-not-rules contract). Use
amazon-fba-oa:fba-architect for the boundary check (hints are DATA consumed at runtime;
ai-brain.json and config stay untouched by the deal watch), then amazon-fba-oa:fba-coder.

1. scout/discovery_hints.py: read fresh deal_hints from Supabase (not expired, strength
   >= threshold from ai-brain.json dealFinder.hints.minStrength — add via
   fba-brain-updater with provenance: TOP100_DEAL_WATCH_PLAN research 2026-07-04,
   default 2). Returns ranked {brand, store, category, strength} hints, honestly empty
   when none.
2. pipeline discovery ordering (Keepa-gated but built now): when KEEPA_KEY exists, the
   discovery stage runs hint-led Product Finder queries FIRST (hinted brands ∩ NOT
   avoid-list, using the existing discovery.productFinderStack filters), then the normal
   friendly-brand rotation for the remaining budget. Token budgeting: hints get at most
   50% of the run's discovery token budget (brain key dealFinder.hints.tokenShare, 0.5).
   Every candidate found via a hint records found_via="deal-hint:<store>" — the
   learning loop can later measure whether hint-led candidates outperform (add that
   comparison to ops_report when outcomes exist).
3. Fallback is explicit: zero fresh hints → 100% normal discovery, and the digest says
   "no fresh deal hints — self-directed discovery" (never an error state).
4. Digest + Morning Brief: a "deal-led discovery" line (hints followed, candidates found
   per hint); control-center Deals page gains a small hints panel (fresh hints + ages)
   via the existing /api/ops read layer.
5. Tests: hint ranking/expiry, avoid-list exclusion at BOTH layers (hints creation and
   consumption — belt and suspenders), token-share cap, honest empty fallback, digest
   lines. Full suite green (Keepa calls mocked). typecheck+build for the panel. Journal
   entry.
```

## 5. Order + costs + honesty

Order: **T1** (works today — Slickdeals/Reddit adapters run immediately, the current local dress-rehearsal cycle exercises them) → **T2** (~10 min of your clicking for repo secrets; then it runs nightly forever, PC off) → **T3** (built now, fully activates when the Keepa key lands next week — perfect timing).

Cost: $0/month, verified — GitHub Actions free tier at ~8% utilization, all signals free, upgrades (Best Buy API, affiliate catalogs) also free when their approvals land.

Honest limits: RSS/page signals give title+price, not UPCs — match quality depends on the D2 matcher's title path until the affiliate catalogs (with UPC/ASIN fields) get approved, so expect more review-queue items than auto-accepts at first. Clearance-page extraction is best-effort by design (confidence field, never faked). Slickdeals-sourced deals are crowd-visible — speed matters, which is exactly why the watch runs nightly and hints expire in 72h. And the AVOID-brand rule is enforced twice: Nike/adidas deals can appear in your Discord digest as market signal, but they can never become hints, candidates, or buys.
