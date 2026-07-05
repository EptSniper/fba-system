-- 005: structured decision reasons (Code Review 2026-07-03, Findings #8 and the reason-format
-- design-debt note).
--
-- Why: the Review Queue (control-center /queue, CC1) REQUIRES a reason code on every
-- Approve/Reject/Watch, but until this migration the code was flattened into the free-text
-- decisions.reason column ("thin-margin: too close to breakeven") and, for deal matches,
-- discarded entirely (deal_matches had no human-reason column at all — the only copy lived in
-- the local events.jsonl ledger, which doesn't exist on a deployed instance). Structured
-- reasons are the input to matcher tuning and reject-pattern analysis (fba-data-analyst /
-- propose_updates), so they must be queryable with a WHERE clause, not a string parser.
--
-- decisions.reason stays free text (scout's own log_decision() writes prose there);
-- decisions.reason_code is the new machine-readable field the control-center writes.
-- Additive only — no existing rows or writers are affected.

ALTER TABLE decisions
    ADD COLUMN IF NOT EXISTS reason_code TEXT;  -- ip-risk | price-war | slow-mover | bad-match
                                                -- | gated | thin-margin | other | null (scout-
                                                -- written rows predating / bypassing the queue)

ALTER TABLE deal_matches
    ADD COLUMN IF NOT EXISTS human_reason TEXT; -- same code vocabulary + optional free text;
                                                -- llm_reason stays the MATCHER's explanation,
                                                -- human_reason is the REVIEWER's
