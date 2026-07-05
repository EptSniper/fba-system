-- 007_deal_hints.sql
--
-- TOP100_DEAL_WATCH_PLAN.md Prompts T1 + T3: the nightly Top-100 deal watch writes DATA (not
-- rules) that steers the 7:30 AM scout toward where quality deals are showing up. Three
-- additive changes, all degrading gracefully in scout/db.py until applied:
--
-- 1. deal_hints — the "look here first" contract. One row per (brand, store, category) seen in
--    quality deals from a NON-AVOID source, with an expiry so stale signal self-clears. The
--    scout reads FRESH hints as its first discovery pass (scout/discovery_hints.py); the deal
--    watch writes them (scout/deals/run_watch.py). hint_key is a normalized
--    "brand|store|category" string filled by db.py's upsert_deal_hint() so the upsert has a
--    single non-null natural key (avoids NULL-in-unique-index footguns, same reason search_log
--    uses a plain lowercased brand column). AVOID-listed brands NEVER produce a row here — that
--    gate lives in run_watch/registry, but even so this table only ever holds signal, never a
--    buy authorization.
--
-- 2. source_http_cache — cross-run ETag/Last-Modified validators for the polite clearance-page
--    fetcher (clearance_page.py's conditional GET). MUST live in Supabase, not a local file:
--    the deal watch's primary home is an ephemeral GitHub Actions runner (fresh checkout every
--    run), so a local cache file would never persist between runs.
--
-- 3. deals.source_signal / deals.extraction_confidence — two columns for RSS/page-scraped
--    rows: which registry detect method produced the row, and an honest 0-1 confidence for
--    best-effort clearance-page title/price extraction (never faked — a low number is the
--    truth about a noisy parse, surfaced rather than hidden).
--
-- Additive-only. scout/db.py's upsert_deal() strips source_signal/extraction_confidence on a
-- pre-migration insert (migration_only_fields), and every deal_hints/source_http_cache helper
-- degrades to a no-op/empty if the table is absent — nothing breaks by waiting to apply.

CREATE TABLE IF NOT EXISTS deal_hints (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hint_key      TEXT NOT NULL,   -- normalized "brand|store|category"; the upsert natural key
    brand         TEXT,
    store         TEXT,
    category      TEXT,
    strength      NUMERIC NOT NULL DEFAULT 0,   -- count of quality deals, discount-weighted
    first_seen    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen     TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL          -- set explicitly by db.py (last_seen + TTL)
);
ALTER TABLE deal_hints ENABLE ROW LEVEL SECURITY;
-- service_role only, matching every other business table (no anon/public policy).
CREATE UNIQUE INDEX IF NOT EXISTS deal_hints_key_idx ON deal_hints (hint_key);
CREATE INDEX IF NOT EXISTS deal_hints_expiry_idx ON deal_hints (expires_at);

CREATE TABLE IF NOT EXISTS source_http_cache (
    source_key    TEXT PRIMARY KEY,   -- domain or clearance URL the validators belong to
    etag          TEXT,
    last_modified TEXT,
    last_fetched  TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE source_http_cache ENABLE ROW LEVEL SECURITY;

ALTER TABLE deals ADD COLUMN IF NOT EXISTS source_signal TEXT;          -- sd-rss | clr | reddit | dealnews | woot
ALTER TABLE deals ADD COLUMN IF NOT EXISTS extraction_confidence NUMERIC;  -- 0-1, honest best-effort parse confidence
