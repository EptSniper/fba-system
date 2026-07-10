-- 015_ranker_gate_evidence.sql
--
-- ML audit (2026-07-09, 12-lens specialist audit) — three MAJOR findings share one root cause:
-- the promotion gate's decisive evidence lived nowhere durable. ranker_runs (migration 013)
-- recorded only the by-ASIN champion/challenger AUC, so:
--
--   1. The consecutive-wins streak could be PADDED: training is deterministic
--      (random_state=42, hash/sort-based splits), so re-training on an identical dataset
--      reproduces the identical win, and nothing recorded which dataset a win came from.
--      -> content_hash: the training set's fingerprint content hash. promotion_gate() now
--         collapses runs with duplicate hashes — a win only extends the streak when the
--         training set actually changed.
--   2. The time-held-out split (forward generalization — the gate's part 3) was computed and
--      then discarded on cloud runs (ranker-report.md dies with the ephemeral runner).
--      -> time_split_champion_auc / time_split_challenger_auc / time_split_val_rows, and
--         _run_won() now requires recorded time-split evidence for a prior run to count
--         toward the streak.
--   3. The gate verdict itself (ready/reason/consecutive_wins/small_sample) never reached the
--      dashboard or history.
--      -> promotion_gate JSONB: the full gate dict, one per trained run.
--
-- NOT-APPLIED pattern (like 001-014): additive-only. scout/db.py's record_ranker_run() now
-- strips migration-only fields and retries when PostgREST rejects unknown columns, so a
-- pre-015 database loses only these keys, never the whole run row. Apply via the Supabase SQL
-- editor or MCP when ready.

ALTER TABLE ranker_runs ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE ranker_runs ADD COLUMN IF NOT EXISTS time_split_champion_auc NUMERIC;
ALTER TABLE ranker_runs ADD COLUMN IF NOT EXISTS time_split_challenger_auc NUMERIC;
ALTER TABLE ranker_runs ADD COLUMN IF NOT EXISTS time_split_val_rows INTEGER;
ALTER TABLE ranker_runs ADD COLUMN IF NOT EXISTS promotion_gate JSONB;
