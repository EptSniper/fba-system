-- 003_deals_and_matches.sql
--
-- Deal Finder Build Plan (2026-07-02), Prompt D1: the deal-finder is a SECOND discovery
-- source that feeds the SAME rater as Keepa discovery (learning-hub/ai-system/
-- deal-sourcing-system.md's design). This migration adds the two tables the source
-- connectors (scout/deals/sources/) and the future matcher (Prompt D2) need.
--
-- NOT YET APPLIED — same status as migrations 001/002 (blocked by the session's safety guard;
-- a live schema change against the shared production Supabase project needs your explicit
-- review, not implied consent). Apply via the Supabase SQL Editor (dashboard -> your project
-- -> SQL Editor -> paste -> Run), or explicitly ask Claude Code to run it via the connected
-- Supabase MCP `apply_migration` tool pointed at project id `cakbzcvtqhdtxfjuxstd`. Apply all
-- three pending migrations (001, 002, 003) together while you're in there.
--
-- scout/db.py's upsert_deal() degrades gracefully (falls back to a plain, non-idempotent
-- insert) if this hasn't landed yet — nothing breaks by waiting, you just don't get
-- idempotent re-polling of the same deal until you apply it.
--
-- REVISED 2026-07-02 (Code Review, Finding B3): the unique index below originally used a
-- `WHERE sku IS NOT NULL` partial predicate, which PostgREST's on_conflict= parameter cannot
-- bind to (Postgres 42P10) — every upsert would have silently fallen back to a plain insert.
-- Now a plain (non-partial) unique index; behaviorally identical for NULL skus (Postgres
-- already treats every NULL as distinct for uniqueness) and the application never attempts an
-- upsert without a real sku anyway (see db.py's upsert_deal).
--
-- REVISED 2026-07-03 (applying to prod surfaced a bug the above revision didn't catch):
-- `seen_date` was `GENERATED ALWAYS AS (first_seen::date) STORED`, which Postgres rejects at
-- CREATE TABLE time — 42P17 "generation expression is not immutable" (a timestamptz->date cast
-- implicitly depends on the session's TimeZone setting). Fixed the same way migration 001
-- already fixed keepa_snapshots.snapshot_date (Finding S7): a plain DATE column that
-- scout/db.py's upsert_deal() fills explicitly (today's local date) instead of a generated
-- expression.

-- 1. deals — raw normalized feed rows from every source connector (Slickdeals, Best Buy today;
--    Impact/Walmart.io/Keepa-deal once Prompt D4 lands). Idempotent on (retailer, sku,
--    price_current, day) so re-polling a feed within the same day updates the existing row
--    instead of duplicating it. sku is nullable (Slickdeals rarely has one) — rows without a
--    sku fall back to a plain insert in db.py and may duplicate until matched/discarded.
CREATE TABLE IF NOT EXISTS deals (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    retailer         TEXT NOT NULL,
    source           TEXT NOT NULL,          -- slickdeals | bestbuy | impact | walmart_io | keepa_deal
    sku              TEXT,
    upc              TEXT,
    title_raw        TEXT NOT NULL,
    brand            TEXT,
    price_current    NUMERIC,
    price_original   NUMERIC,
    discount_pct     NUMERIC,
    url              TEXT,
    first_seen       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen        TIMESTAMPTZ NOT NULL DEFAULT now(),
    seen_date        DATE,   -- set explicitly by db.py's upsert_deal(), not generated (see above)
    status           TEXT NOT NULL DEFAULT 'new'   -- new | matched | discarded
);
ALTER TABLE deals ENABLE ROW LEVEL SECURITY;
-- No anon/public policy — service_role only, matching every other business table in this project.
CREATE UNIQUE INDEX IF NOT EXISTS deals_retailer_sku_price_day_key
    ON deals (retailer, sku, price_current, seen_date);

-- 2. deal_matches — one row per candidate ASIN for a deal (a deal can have more than one
--    candidate before a match is confirmed). Written by the matcher (Prompt D2, LLM pairwise
--    verification cascade); human_verdict is filled in by the control-center match-review
--    queue (Prompt D3) and becomes the gold-set labels that measure/improve matcher accuracy.
CREATE TABLE IF NOT EXISTS deal_matches (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    deal_id        BIGINT NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    asin           TEXT,
    confidence     NUMERIC,
    method         TEXT,        -- upc | title | human
    pack_match     BOOLEAN,
    llm_reason     TEXT,
    human_verdict  TEXT,        -- approve | reject | null (not yet reviewed)
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE deal_matches ENABLE ROW LEVEL SECURITY;
-- No anon/public policy — service_role only, matching every other business table.
CREATE INDEX IF NOT EXISTS deal_matches_deal_id_idx ON deal_matches (deal_id);
CREATE INDEX IF NOT EXISTS deal_matches_asin_idx ON deal_matches (asin) WHERE asin IS NOT NULL;
