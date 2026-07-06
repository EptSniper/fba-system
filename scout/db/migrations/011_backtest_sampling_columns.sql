-- 011_backtest_sampling_columns.sql
--
-- Session 55 (2026-07-05) — the brand-agnostic sampling overhaul (learning-hub/data/ai-brain.json
-- learning.sampling). Adds three columns to backtest_rows so a training row remembers WHICH
-- mechanism sourced its ASIN and whether that ASIN's brand is on the hard avoid-list:
--
--   sample_source  — 'onpolicy' (existing friendly+hint brand-seeded sample, unchanged),
--                    'explore' (brand-agnostic category-keyword search, scout/backtest.py
--                    sample_asins_explore), or 'dealfeed' (the Keepa /deal firehose,
--                    scout/deals_firehose.py). Lets train_ranker.py report onpolicy-vs-explore
--                    performance separately and the daily digest show a sampling-composition
--                    line (X% dealfeed / Y% explore / Z% onpolicy).
--   category       — the row's Amazon category (already reconstructed per-window from Keepa's
--                    categoryTree at enrich/history time — this just persists it instead of
--                    discarding it), for the stratified composition report.
--   ip_risk        — true when the ASIN's brand is on brands.AVOID_BRANDS. Avoid-brand ASINs
--                    are COLLECTED as data (brand-agnostic sampling makes no brand exception) but
--                    this flag is how the composition report and any future filtering can tell
--                    them apart. It does NOT gate anything here — backtest_rows never was a
--                    candidate/lead surface; the hard "never becomes a buy candidate" gate lives
--                    entirely in scoring.oa_hard_reject/brands.is_avoided on the SEPARATE
--                    buy-discovery path (pipeline.py, discovery_hints.py), untouched by this
--                    migration or by the new sampling code (test-asserted:
--                    scout/tests/test_backtest_sampling.py).
--
-- NOT-APPLIED pattern (like 001-010): additive-only; scout/db.py's upsert_backtest_rows/
-- all_backtest_rows retry WITHOUT these columns if the migration hasn't landed yet, so nothing
-- breaks (backtest row collection keeps working exactly as before) until this is applied. Apply
-- via the Supabase SQL editor or MCP when ready.

ALTER TABLE backtest_rows ADD COLUMN IF NOT EXISTS sample_source TEXT;
ALTER TABLE backtest_rows ADD COLUMN IF NOT EXISTS category TEXT;
ALTER TABLE backtest_rows ADD COLUMN IF NOT EXISTS ip_risk BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS backtest_rows_sample_source_idx ON backtest_rows (sample_source);
