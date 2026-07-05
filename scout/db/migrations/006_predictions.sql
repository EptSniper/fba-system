-- 006: prediction ledger (Code Review 2026-07-04 ask — "scout/exam.py" prompt item 4).
--
-- Why: the scorer's soft signals (price-spike, price-caution, offers-rising, ip-cliff,
-- velocity) are all implicitly FORECASTS — "this price will revert," "this offer count keeps
-- rising," "this sells ~N/month" — but until now nothing recorded them as falsifiable claims
-- to check later. This table lets scout/predictions.py write one row per predictable signal
-- at scoring time, then score matured predictions against fresh Keepa stats weekly
-- (run_daily.py -> ops-report.md), building an honest hit-rate track record for the scorer's
-- own forward-looking claims — distinct from outcomes (which record REALIZED buy/sell results,
-- not predictions about market behavior).
--
-- Written now, NOT applied automatically (same pattern as migration 005) — needs Mehmet's
-- explicit go-ahead. Additive-only; nothing reads or writes this table until it exists.
-- SCAFFOLD STATUS: scoring predictions requires re-fetching live Keepa stats per ASIN at
-- maturity, which needs a paid KEEPA_KEY (HUMAN_TODO.md item #2) — not configured yet. Until
-- then, predictions.record_predictions_for() can still WRITE rows (pure bookkeeping, no Keepa
-- call), but predictions.score_matured_predictions() honestly reports "unavailable" rather than
-- fabricating a hit rate.

CREATE TABLE IF NOT EXISTS predictions (
    id             BIGSERIAL PRIMARY KEY,
    asin           TEXT NOT NULL,
    lead_id        BIGINT REFERENCES leads(id),
    made_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    claim_type     TEXT NOT NULL,       -- price_reversion | offer_trend | velocity
    threshold      NUMERIC NOT NULL,    -- the predicted value/ceiling the claim is checked against
    horizon_days   INT NOT NULL,        -- days from made_at until the claim matures
    context        JSONB,               -- the signal(s) that produced this claim (e.g. which adjustment fired)
    resolved_at    TIMESTAMPTZ,         -- null until scored
    outcome        TEXT,                -- null | hit | miss (set only at resolution)
    actual_value   NUMERIC              -- the fresh Keepa value the claim was checked against
);

CREATE INDEX IF NOT EXISTS predictions_unresolved_idx
    ON predictions (made_at) WHERE resolved_at IS NULL;
