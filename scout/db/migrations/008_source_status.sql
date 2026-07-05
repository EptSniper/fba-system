-- 008_source_status.sql
--
-- TOP100_DEAL_WATCH_PLAN.md follow-up (2026-07-04): per-clearance-URL health state so the deal
-- watch can retire chronically-forbidden clr pages to "sd-rss-only" WITHOUT losing coverage
-- (the store's Slickdeals per-store feed still covers it), and so it stops re-listing those
-- known-dead ones in the digest every night.
--
-- MUST live in Supabase (not a local file): the deal watch's home is the ephemeral GitHub
-- Actions runner (fresh checkout each run), so "403 on 2 CONSECUTIVE runs" can only be tracked
-- across runs in a shared store. Same reason source_http_cache (migration 007) lives here.
--
-- Transition logic (scout/deals/source_status.py, NOT this migration):
--   - clr returns 403 (forbidden): consecutive_403 += 1; at >= 2, and ONLY if the store also
--     has a sd-rss fallback, mode -> 'sd-rss-only' (future runs skip the clr fetch entirely).
--   - clr succeeds (ok/empty/not_modified): consecutive_403 -> 0.
--   - clr returns 429 (rate_limited): TRANSIENT — no counter change, not retired, re-tried next
--     run (Chewy's nightly 429 is backoff, not breakage).
--
-- Additive-only; every helper degrades to a no-op/empty if this hasn't landed yet.

CREATE TABLE IF NOT EXISTS source_status (
    url               TEXT PRIMARY KEY,   -- the clearance URL this status is about
    mode              TEXT NOT NULL DEFAULT 'active',   -- active | sd-rss-only
    consecutive_403   INT NOT NULL DEFAULT 0,
    last_status       TEXT,               -- ok | empty | not_modified | forbidden | rate_limited | error
    last_status_code  INT,
    last_checked      TIMESTAMPTZ NOT NULL DEFAULT now(),
    retired_at        TIMESTAMPTZ         -- when it became sd-rss-only (null while active)
);
ALTER TABLE source_status ENABLE ROW LEVEL SECURITY;
-- service_role only, matching every other business table.
