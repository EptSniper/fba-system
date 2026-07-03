-- 001_g1_runs_and_idempotency.sql
--
-- System Blueprint, Prompt G1: make the scout stateless (Supabase = the single state store)
-- and idempotent (re-running a failed day never duplicates data).
--
-- NOT YET APPLIED. This file was written by Claude Code but the actual migration was BLOCKED
-- by the session's safety guard ("Modify Shared Resources" — a live schema change against the
-- shared production Supabase project needs your explicit review, not implied consent). Apply it
-- yourself via the Supabase SQL Editor (dashboard -> your project -> SQL Editor -> paste -> Run),
-- or explicitly tell Claude Code to run it via the connected Supabase MCP `apply_migration` tool
-- pointed at project id `cakbzcvtqhdtxfjuxstd`.
--
-- Every consumer in scout/db.py is written to degrade gracefully (existing "silent no-op" pattern)
-- if this hasn't been applied yet — nothing breaks by waiting, you just don't get run-tracking /
-- idempotent upserts / lead-linkage columns until you apply it.
--
-- REVISED 2026-07-02 (Code Review, Findings B3 + S7) — before this revision, both unique
-- indexes below used a `WHERE ... IS NOT NULL` partial predicate. PostgREST's on_conflict=
-- parameter (what scout/db.py's upserts send) can only bind to a PLAIN unique index/constraint
-- — Postgres raises 42P10 ("no unique or exclusion constraint matching the ON CONFLICT
-- specification") against a partial index, which silently degraded EVERY upsert to a plain
-- insert, defeating the whole point of this migration. Fix: plain (non-partial) unique
-- indexes. This changes nothing for NULL handling — Postgres already treats every NULL as
-- distinct from every other NULL for uniqueness purposes, so multiple asin=NULL rows remain
-- allowed either way, and the application never attempts an upsert without a real asin.
-- Finding S7: keepa_snapshots.snapshot_date is now a PLAIN date column that scout/db.py fills
-- explicitly with the LOCAL calendar date, not a `captured_at::date` GENERATED column — a
-- generated column derives from captured_at's UTC timestamp, so a run in the late evening
-- local time got bucketed into "tomorrow."

-- 1. runs table — one row per scout cycle (including failures), per the daily-runner spec (G2).
CREATE TABLE IF NOT EXISTS runs (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at       TIMESTAMPTZ,
    status            TEXT NOT NULL DEFAULT 'running',  -- running | success | failed
    asins_scanned     INTEGER DEFAULT 0,
    candidates_gated  INTEGER DEFAULT 0,
    leads_upserted    INTEGER DEFAULT 0,
    tokens_consumed   INTEGER,
    tokens_left_end   INTEGER,
    error_summary     TEXT,
    host              TEXT
);
ALTER TABLE runs ENABLE ROW LEVEL SECURITY;
-- No anon/public policy — service_role only, matching every other business table in this project.

-- 2. leads: lead-linkage columns (Brief 3.1) + idempotent natural key.
ALTER TABLE leads ADD COLUMN IF NOT EXISTS features_snapshot JSONB;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS explanation JSONB;
-- features_snapshot = pre-decision inputs ONLY (leakage-prevention non-negotiable — see
-- scout/labels.py PRE_DECISION_FEATURES). explanation = the scout's own gates/adjustments
-- output, kept for human review only — never treated as a training label; the scout's verdict
-- must never become its own success label.
CREATE UNIQUE INDEX IF NOT EXISTS leads_asin_found_via_key
    ON leads (asin, found_via);

-- 3. keepa_snapshots: idempotent natural key (asin + LOCAL day). captured_at already exists
--    (timestamptz default now()) for the real capture instant; snapshot_date is a plain column
--    that scout/db.py's upsert_keepa_snapshot() sets explicitly to the local calendar date, so
--    ON CONFLICT targets a stable, correctly-bucketed date rather than a timestamp that
--    changes on every call or a UTC-derived date that mis-buckets late-evening local runs.
ALTER TABLE keepa_snapshots ADD COLUMN IF NOT EXISTS snapshot_date DATE;
CREATE UNIQUE INDEX IF NOT EXISTS keepa_snapshots_asin_date_key
    ON keepa_snapshots (asin, snapshot_date);
