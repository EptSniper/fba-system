-- 014_ranker_concentration.sql
--
-- ML de-bias audit (2026-07-09, ML_DEBIAS_PLAN.md) -- every training run now measures and caps
-- brand/category concentration (scout/train_ranker.py's corpus_concentration()/
-- apply_corpus_caps()). This column is the durable, queryable record of that measurement
-- (before-cap AND after-cap composition, HHI, top-brand/top-5 shares, distinct counts) so the
-- control-center's Scout Intelligence dashboard can chart concentration trending down over time,
-- not just today's snapshot printed to a log/Discord post.
--
-- NOT-APPLIED pattern (like 001-013): additive-only; scout/db.py's record_ranker_run() already
-- accepts arbitrary **fields and simply won't include this key until the column exists -- no
-- caller breaks in the meantime. Apply via the Supabase SQL editor or MCP when ready.

ALTER TABLE ranker_runs ADD COLUMN IF NOT EXISTS concentration JSONB;
