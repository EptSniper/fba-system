-- 002_g3_spapi_restrictions_cache.sql
--
-- System Blueprint, Prompt G3: cache SP-API Listings Restrictions results per ASIN for 7 days
-- (account-specific and slow-changing, per the prompt's own spec).
--
-- NOT YET APPLIED — same status as migration 001 (blocked by the session's safety guard; a
-- live schema change against the shared production Supabase project needs your explicit
-- review). Apply via the Supabase SQL Editor, or explicitly ask Claude Code to run it via the
-- connected Supabase MCP `apply_migration` tool pointed at project id `cakbzcvtqhdtxfjuxstd`.
--
-- scout/db.py's cache functions degrade gracefully (return None / skip caching) if this table
-- doesn't exist yet — nothing breaks by waiting, restriction checks just always hit the live
-- API (or, since no real SP-API credentials exist yet either, always return NOT_CONFIGURED).

CREATE TABLE IF NOT EXISTS spapi_restrictions_cache (
    asin        TEXT PRIMARY KEY,
    status      TEXT NOT NULL,   -- ALLOWED | APPROVAL_REQUIRED | NOT_ELIGIBLE
    reasons     JSONB,
    links       JSONB,
    checked_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE spapi_restrictions_cache ENABLE ROW LEVEL SECURITY;
-- No anon/public policy — service_role only, matching every other business table.
