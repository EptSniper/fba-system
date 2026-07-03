# Deal Finder Build Plan — retail deals → matched ASINs → the scout

**Date:** 2026-07-02 · **Author:** Claude (Cowork), from live web research (citations in the research notes; all pricing verified July 2026 unless flagged) · **Executor:** Claude Code (prompts D1–D4 below); Mehmet for accounts/signups.
**Builds on:** `learning-hub/ai-system/deal-sourcing-system.md` (the 2026-06-20 design — still correct: the deal finder is a SECOND discovery source feeding the SAME rater). This doc supplies what that design left open: where the item-level data actually comes from, how AI does the matching, and the exact build sequence.
**Companions:** `SYSTEM_BLUEPRINT.md` (the loop), `SCOUT_EXPERT_UPGRADE_BRIEF.md` (the rater).

---

## 1. The shape of the problem

A deal finder is three stages, and the middle one is where every commercial tool lives or dies:

```
  GET DEALS                      MATCH TO ASIN                    RATE (already built)
  retailer feeds/APIs      →     retail item → correct Amazon →   scout gates + scoring +
  (title, brand, price,          listing, right variation,        eligibility + explain-why
  sale price, UPC)               right PACK COUNT, + confidence   → review queue → capture
```

Research finding that frames everything: **matching quality is the existential risk.** SourceMogul died with reviewers reporting >80% wrong matches (wrong sizes, different items). No commercial tool publishes accuracy numbers. A wrong match doesn't just waste money — analyzing the wrong ASIN poisons every downstream number. So we build matching with per-match confidence + evidence, and route the gray zone to human review. That is genuinely differentiated: no surveyed tool does LLM pairwise verification.

## 2. Where the deal data comes from (ranked, verified July 2026)

**Tier 1 — start now, $0:**
1. **Best Buy Products API** — the ONLY US big-box with an official, free, open developer API. `onSale=true`, `salePrice`, clearance flags, UPC included. One catch: they reject API-key signups from free email addresses (Gmail) — needs a domain email. Rate limits (~5/s, 50k/day commonly cited) unverified — check on signup.
2. **Slickdeals RSS** — official RSS feeds (frontpage/category), free, ToS-clean to consume. Crowd-visible so margins compress fast; use as signal, expect competition on anything front-paged.
3. **Keepa /deal endpoint** (once the Keepa API key exists) — 5 tokens per request returns up to 150 Amazon-side price-drop deals with filters (category, brand, price range, rank range, Amazon-offer presence). This finds a DIFFERENT flip (Amazon price drops, warehouse deals), and is also useful inverted: detect tanking Buy Boxes to avoid. No retail-store data.

**Tier 2 — free but gated by affiliate approval (start applications now, they take days–weeks):**
4. **Impact.com partner account → Target, Walmart, Home Depot, Best Buy catalogs.** The killer detail: Impact's partner Catalogs API returns `Gtin`, sometimes even `Asin`, plus `CurrentPrice`, `OriginalPrice`, `DiscountPercentage`, `StockAvailability` per item — sale-vs-list delta AND the matching identifiers in one feed. Approval per brand; beginners with no site get auto-rejected → Mehmet needs a modest deals/review blog first (see actions).
5. **Walmart.io Affiliate API** (unlocked by the Walmart affiliate approval) — product lookup by UPC, clearance/rollback filters, 5,000 calls/day.
6. **CJ (Commission Junction)** — Walgreens lives here; Product Search API can return products even from non-joined advertisers. Beginner approval friction is real.

**Not worth it / not possible (researched, so we stop wondering):** Target RedSky (unofficial, now aggressively blocked, ToS-dirty); BrickSeek (no API, ToS forbids scripting); Slickdeals official API (partnership-gated); cashback/gift-card rate APIs (don't exist — Rakuten/TopCashback/CardCash have no public developer APIs). Discount stacking therefore stays a **manual table**: retailer → typical cashback % + typical gift-card discount %, refreshed weekly by hand, applied as a landed-cost multiplier. FMTC API ($325/mo) remains deferred until volume justifies it.

**ToS note (from the existing design doc, confirmed by research):** affiliate feeds license you to *promote* the retailer; pure sourcing use is a gray area. Mitigation: actually run the deals blog the affiliate account is registered for — it costs nothing extra and makes the account legitimate.

## 3. How the AI does the matching (the research-backed pipeline)

Five steps, cheap-to-expensive cascade. Realistic expectation from the entity-matching literature (WDC benchmarks): 80–90+ F1 on hard pairs from an LLM judge, better here because we usually also have brand, price, and often UPC. Never 100% — the review queue is part of the design, not a failure of it.

1. **Normalize first (the highest-ROI trick).** Extract structured attributes from BOTH sides before comparing: `{brand, core_title, pack_count, size_value, size_unit, variant}`. Regex handles "2-pack", "pack of 3", "3ct", "16.9 fl oz"; Claude Haiku (structured output) handles the long tail. Pack-count mismatch (retail 1-pack matched to Amazon 2-pack) is the #1 documented OA matching killer — this step defuses it deterministically. LLM attribute extraction benchmarks at F1 ~86–91.
2. **UPC path (when the feed has a UPC).** Keepa code query (1 token, batch 100) primary; SP-API `searchCatalogItems` by identifier (free, 20/request) cross-check. Amazon itself documents that UPC↔ASIN is NOT 1:1 (multipacks, parent-ASIN-returned bug) — so a UPC hit is a *candidate generator*, not a verdict: still compare extracted pack/size against the ASIN's package-quantity attributes.
3. **Title path (no UPC, or UPC disagreement).** SP-API keyword search (brand + core title) for Amazon-side candidates → embed both sides with the already-local bge-base-en-v1.5 → pgvector top-5 by cosine. Cosine RANKS candidates; it is not calibrated truth — never auto-accept on cosine alone.
4. **LLM verification (the accuracy engine).** Claude Haiku pairwise "same product?" per candidate: both records serialized field-by-field, a crisp rubric (brand + item + size + pack count must all match; variation-exact), 3–5 few-shot trap examples (1-pack vs 2-pack, 16oz vs 24oz, color variants), forced JSON `{match, pack_match, confidence, reason}`. Prompt-cache the static rubric (90% off) and use the Batch API for nightly runs (50% off). **Cost: ~$1.50–4 per 1,000 deals all-in** — LLM spend is negligible; Keepa tokens and human review time are the real constraints.
5. **Composite confidence + routing (ER-standard three bands).** UPC-verified + attributes agree ≈ 0.95; LLM-yes + pack-match + sane price ratio ≈ 0.85; flags lower it. **≥0.90 → straight to the scout's rater; 0.60–0.90 → human review queue (show both listings + the LLM's reason); <0.60 → discard.** Price-sanity check: if the Amazon price is ~N× retail, suspect an N-pack mismatch (practitioner heuristic — tune thresholds on our own data). Escalate only gray-zone pairs to Sonnet, optionally with the two product images as a vision tie-break. Every human verdict is logged and recalibrates the thresholds — same learning loop as everything else.

Rejected approaches (researched): browser/computer-use agents for bulk discovery (orders of magnitude costlier than feed rows, no credible OA usage at scale found); CLIP image index (overkill — a vision LLM call on the gray zone does the job); building a multi-site crawler (Tactical Arbitrage's moat — rent it for $89/one month if ever needed).

## 4. Integration with the scout (one rater, one loop)

The deal finder produces exactly what the Keepa discovery path produces — an ASIN plus a landed cost — so from the gates onward the systems are IDENTICAL:

- New Supabase tables: `deals` (raw normalized feed rows, idempotent on retailer+sku+seen_date) and `deal_matches` (deal_id, asin, confidence, method, llm_reason, human_verdict). Matched deals with confidence ≥0.90 flow into the **existing** pipeline as candidates with `source="deal-finder"` and `landed_cost = deal price × discount-stack multiplier`; the scout applies its normal gates, scoring, explain-why, eligibility, and Supabase lead logging. No second scorer, no second brain.
- The runner (Blueprint G2) gains a deal-finder stage before discovery; the Discord digest gains a "retail deals" section; the review queue gains match-verification items (a different question than buy/no-buy: "is this the same product?").
- The control-center **Deals module** finally goes live off `deals`/`deal_matches` instead of the honest-empty `deals.json`; a match-review card shows both product titles/images, attributes, LLM reason, and approve/reject buttons that write labels.
- ai-brain.json gains a `dealFinder` block (sources, confidence bands, discount-stack table, price-sanity thresholds) — brain-updater conventions, both tools read it, G5 proposals can tune it.

## 5. What Mehmet does (no code)

1. **Get a domain email** (any $10/yr domain or an existing one) → **Best Buy API key** — this unlocks Tier 1 today.
2. **Stand up a minimal deals blog** (a weekend, or ask Claude Code for a one-page Next.js site — it can live in this repo) → then **apply on Impact.com** to Target, Walmart, Home Depot, Best Buy programs, and CJ for Walgreens. Applications need specific, honest answers; approvals take days–2 weeks. Start now so Tier 2 is ready when D4 is.
3. **Anthropic API key** (for Haiku matching) into `API_KEYS.env` — spend is single-digit dollars/month at our volume.
4. Maintain the **discount-stack table** weekly (5 minutes: check Rakuten/TopCashback rates + cardbear for your target retailers).
5. Keep the existing rule: every purchase decision stays human.

## 6. Claude Code prompts

### Prompt D1 — deals foundation: schema, normalizer, first two free sources

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Read
learning-hub/ai-system/deal-sourcing-system.md and the dealFinder/dealSourcing sections of
learning-hub/data/ai-brain.json. Use amazon-fba-oa:fba-database-expert for the schema and
amazon-fba-oa:fba-coder for implementation.

1. Supabase migration: deals table (id, retailer, source, sku, upc, title_raw, brand,
   price_current, price_original, discount_pct, url, first_seen, last_seen, status) with a
   unique natural key (retailer + sku + price_current per day) for idempotent upserts; and
   deal_matches (deal_id, asin, confidence, method [upc|title|human], pack_match,
   llm_reason, human_verdict, created_at). RLS consistent with existing business tables.
2. scout/deals/normalize.py: attribute extractor producing {brand, core_title, pack_count,
   size_value, size_unit, variant} from a raw title — regex first (2-pack, pack of N, Nct,
   fl oz, ml, lb, count), with a pluggable LLM fallback stub (wired in D2). Unit tests with
   at least 20 messy real-world title fixtures including multipack traps.
3. scout/deals/sources/slickdeals.py: consume the official Slickdeals RSS feeds (frontpage +
   configurable category feeds from ai-brain.json), normalize into deals upserts. Respect
   polite polling (config interval, default 6h), set a honest User-Agent.
4. scout/deals/sources/bestbuy.py: Best Buy Products API connector (key from env
   BESTBUY_API_KEY; absent → skip with honest log, never fake): query onSale=true items in
   configured categories, capture salePrice/regularPrice/UPC. Discover and respect the
   actual rate limits; record them in the code comments and README once observed.
5. Add a dealFinder block to ai-brain.json via fba-brain-updater conventions: sources
   config, confidence bands {autoAccept: 0.90, review: 0.60}, priceSanity defaults, and the
   manual discountStack table (retailer → cashbackPct, giftCardPct, source: 'manual weekly
   table — no API exists for cashback/GC rates, verified 2026-07'). Re-sync hub-data.
6. Tests green (normalizer, upsert idempotency, both connectors with fixture payloads).
   Journal entry via fba-session-journal.
```

### Prompt D2 — the AI matcher

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Use
amazon-fba-oa:fba-architect to confirm module boundaries, then amazon-fba-oa:fba-coder.
Requires: ANTHROPIC_API_KEY and KEEPA_KEY in scout/.env; SP-API creds optional (skip the
cross-check gracefully if absent).

Build scout/deals/matcher.py implementing the verified cascade:
1. Normalize the deal (D1's extractor; add the Claude Haiku structured-output fallback for
   titles regex can't parse — batch these, cache the static prompt prefix).
2. UPC path: Keepa code query (batch up to 100; 1 token each) → candidates; optional SP-API
   searchCatalogItems identifier cross-check. A UPC hit is a CANDIDATE, not a match:
   compare extracted pack/size vs the ASIN's packageQuantity/title. Handle the documented
   parent-ASIN-returned case.
3. Title path: SP-API keyword search when creds exist (else Keepa Product Finder
   title+brand search) → top candidates → embed both sides with the local
   BAAI/bge-base-en-v1.5 (same model as the RAG corpus — reuse knowledge-rag's embedding
   helper, do NOT introduce a second embedding model) → rank top-5 by cosine in pgvector or
   in-process. Cosine ranks only; floor ~0.75 to prune, tune later.
4. LLM verification: Claude Haiku pairwise same-product check, JSON schema
   {match: yes|no|unsure, pack_match: bool, confidence: 0-1, reason: str}, rubric + 5
   few-shot trap examples (multipack, size, color-variant, bundle, wrong-product-same-brand).
   Use the Batch API when processing >50 pairs. Treat LLM confidence as ordinal, not
   calibrated.
5. Composite confidence per ai-brain.json dealFinder bands + price-sanity ratio check
   (flag when amazon_price/retail_price suggests pack mismatch). Route: >=0.90 auto,
   0.60-0.90 review (write deal_matches row with status review), <0.60 discard (keep the
   row for negative-example learning).
6. Telemetry: per-run counts by route + LLM cost estimate + escalation rate (alert in
   digest if escalation rate jumps — documented cascade failure mode).
7. Build a gold-set harness: fixtures/gold_matches.jsonl (start with 30 hand-checked pairs;
   grows from human review verdicts) and a script that reports precision/recall against it
   on demand. Tests green. Journal entry.
```

### Prompt D3 — wire into the loop + Deals UI

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Use
amazon-fba-oa:fba-coder; amazon-fba-oa:fba-designer for the Deals module layout.

1. Runner integration: add the deal-finder stage to scout/run_daily.py BEFORE Keepa
   discovery — pull sources → normalize → match → auto-accepted matches become pipeline
   candidates with source="deal-finder" and landed_cost = price_current × (1 -
   discountStack multiplier for that retailer). They then flow through the EXISTING gates/
   scoring/explain-why/lead-logging unchanged. Digest gains a "Retail deals" section:
   matched count, review-queue count, top 3 by ROI with explain-why one-liners.
2. Control-center Deals module: replace the empty-state page with live data from
   deals/deal_matches via a same-origin API route — (a) today's matched deals with verdicts
   and confidence, (b) a match-review queue card: both titles, attributes side-by-side,
   prices, LLM reason, Approve / Reject buttons writing human_verdict (these are labels for
   the gold set), honest empty and SP-API/keys-missing states.
3. The match-review verdicts append to fixtures/gold_matches.jsonl (D2) so matcher accuracy
   is measurable and improving. Show current gold-set precision/recall on the Deals page —
   honest numbers, "n too small" under 50 labels.
4. typecheck + build + tests green; 375px no overflow; journal entry.
```

### Prompt D4 — Tier 2 sources (run after affiliate approvals land)

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Use
amazon-fba-oa:fba-coder. Pre-req: Impact.com partner account approved for at least one of
Target / Walmart / Home Depot; credentials (AccountSID + auth token) in scout/.env;
optionally Walmart.io API key.

1. scout/deals/sources/impact.py: Catalogs API consumer — list joined catalogs, pull items,
   map Gtin/Asin/CurrentPrice/OriginalPrice/DiscountPercentage/StockAvailability into deals
   upserts. When the catalog row already carries an Asin, feed it to the matcher as a
   0.90-base candidate (still pack-check it — never blind-trust). Handle >1GB catalogs via
   the FTP/file path with streaming, filter to discounted items only.
2. scout/deals/sources/walmart_io.py: Product Lookup by UPC + Catalog API clearance/rollback
   filters, 5,000 calls/day budget enforced in code.
3. Keepa /deal scanner (5 tokens/150 deals): a separate weekly job surfacing Amazon-side
   price-drop opportunities (warehouse flips) AND feeding the pennyWar/tanking-price
   avoid-list. Filters from ai-brain.json.
4. Connector health in the digest (rows pulled per source, stale-source warnings).
   Tests with fixture payloads. Journal entry.
```

## 7. Build order and the honest bottom line

Sequence: **D1 (today, $0)** → Mehmet's Best Buy key + Anthropic key → **D2** → **D3** → [affiliate approvals arrive] → **D4**.

Status check (2026-07-02): Brief Phase 1 AND Blueprint G1/G2/G3/G5 are already implemented (journal Sessions 18–19), so D1 can start immediately — `run_daily.py` and the Supabase state layer it plugs into already exist. Note for D1: Claude Code must add the deals/deal_matches migration as `scout/db/migrations/003_...sql` following the established NOT-APPLIED-until-human-review pattern from migrations 001/002, and Mehmet applies all three together in the Supabase SQL Editor.

What this will and won't do: it will surface dozens of matched, confidence-scored, gate-checked retail arbitrage candidates daily from free sources, with every match explainable and every mistake feeding the gold set. It will NOT match everything (gray zone goes to you), won't see stores without feeds, and won't know a deal is shelf-clearance-only. The manual "where's the best sale today" habit from the original design doc stays valuable — the deal finder automates the grind, not the judgment.
