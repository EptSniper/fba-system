-- 004_search_log.sql
--
-- Scout Agent Build Plan (2026-07-02), Prompt S2 sec 3.3: the brand-growth loop scaffolding —
-- saved Product Finder searches (seeded from winning leads' brands) with a re-run cadence, so
-- the digest can surface "N searches due" instead of the brand-mining habit relying purely on
-- memory. Actual Product Finder EXECUTION stays Keepa-gated (unchanged) — this table only
-- tracks WHAT to search and WHEN it was last run.
--
-- NOT YET APPLIED — same status as migrations 001/002/003 (blocked by the session's safety
-- guard; a live schema change against the shared production Supabase project needs your
-- explicit review). Apply via the Supabase SQL Editor, or explicitly ask Claude Code to run it
-- via the connected Supabase MCP `apply_migration` tool pointed at project id
-- `cakbzcvtqhdtxfjuxstd`. Apply all four pending migrations (001-004) together.
--
-- scout/search_log.py degrades gracefully (empty due-list, no-op enqueue) if this hasn't
-- landed yet — nothing breaks by waiting.
--
-- REVISED 2026-07-02 (Code Review, Finding B3): the unique index below originally targeted
-- `lower(brand)` (an EXPRESSION index) to get case-insensitive dedup. PostgREST's on_conflict=
-- parameter (db.py's queue_brand_search sends on_conflict=brand) can only bind to a PLAIN
-- column index/constraint, never an expression — Postgres 42P10 at runtime, and since this
-- table has NO other unique constraint, the upsert ERRORS outright (no plain-insert fallback
-- rescues it): the brand-growth loop would never queue anything. Fix: db.py now normalizes
-- brand to lowercase BEFORE writing, so a plain index on the stored column achieves the same
-- case-insensitive dedup without an expression index.

CREATE TABLE IF NOT EXISTS search_log (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    brand             TEXT NOT NULL,
    query_params      JSONB,
    last_run_at       TIMESTAMPTZ,
    rerun_after_days  INTEGER NOT NULL DEFAULT 21,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE search_log ENABLE ROW LEVEL SECURITY;
-- No anon/public policy — service_role only, matching every other business table.
CREATE UNIQUE INDEX IF NOT EXISTS search_log_brand_key ON search_log (brand);
