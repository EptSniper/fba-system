# Leakage / labeling audit — the 91% positive-rate jump (fba-leakage-auditor)

**Run:** Cowork, 2026-07-13, live queries against `backtest_rows` (9,449 rows).
**Trigger:** positive rate rose 87.3% → 91% as collection scaled; sports/tools/office at 95–97%. Claude Code flagged it (Session 63) as needing a check before per-category importances are trusted. This is that check.

## Verdict

**No strict leakage** (the point-in-time boundary is sound — see below). But there is a **severe label-validity problem** that makes the 91% positive rate — and every per-category feature importance — **untrustworthy right now.** It has the same root cause as the price-band filter bug Claude Code already flagged. **Do not trust or promote the ranker on this corpus until both are fixed.** `scoring.rankingChampion` must stay `rule`.

## Evidence

**1. The corpus is training on the wrong price distribution.** Average `price_then` by category: office **$100**, sports **$104**, tools **$118** — the OA buy gate is **$8–$60**. The high-win categories are almost entirely products the buy pipeline would hard-reject on price. This is the `$8–$60` secondary-axis dealfeed filter bug (25/27 combos dry) surfacing as a data-composition problem: with the in-band filter silently returning nothing, collection is dominated by out-of-band $100+ items. **The model is learning on a distribution it will never serve.**

**2. The 91% is a labeling-assumption artifact, not signal.**
- `landed_cost` is a fixed **50% of `price_then`** in every category (confirmed: `landed_cost_frac_of_price = 0.500` across the board). It's an assumption, not a real cost.
- Prices barely move over the 60-day horizon (`price_at_horizon / price_then` = 1.01–1.04), and only **62–69%** of windows actually held or rose in price — yet the win rate is **95–97%**.
- The gap is the fixed-margin cushion: with net proceeds ≈ 70% of price and a landed cost pinned at 50% of price, a product can fall ~28% and still label "profitable." So the label mostly encodes **"did the price not crash"** plus a **generous fixed COGS** — not learnable sourcing edge.
- Result: the label is **near-constant** (91% positive, 97% within tools). A near-constant label carries almost no signal; any AUC the challenger posts is largely exploiting **price-level / category proxies** that track the labeling assumption, which is exactly why the per-category importances look strong and are not to be trusted.
- Marginal wins (profit $0–1.50) are only 0.2–1.2% in the high-win categories: wins aren't close calls, they're baked in by the assumption.

**3. No strict train/test or temporal leakage.** The feature boundary is code-enforced (`backtest.py`: strict `< as_of`, split-by-ASIN, shared `PRE_DECISION_FEATURES`, horizon censoring). The problem is upstream of the split, in **how the label is constructed and what got collected** — not in feature timing.

## Fixes (hand to Claude Code, route via fba-ml-data-engineer + fba-ml-evaluator; brain edits via fba-brain-updater)

1. **Fix the dealfeed price-band filter (priority — it's also the breadth bug).** The `currentRange` (cents) secondary-axis filter isn't constraining to `$8–60`. Run the controlled live test Claude Code scoped (per-band ASIN counts) to confirm Keepa's convention, then keep collection inside the real buy band. Re-check `avg(price_then)` lands in $8–60 afterward.
2. **Make the label reflect the real buy gate, not a fixed 50% COGS.** `would_have_profited = profit > 0` at a fixed half-price cost is too easy. Move to the actual gate — **profit ≥ $3 AND ROI ≥ 30%** (the same thresholds the buy pipeline uses) — and/or vary/stress the landed cost. This restores label variance so the model has something real to learn and the positive rate becomes meaningful.
3. **Re-slice after both fixes.** Positive rate by category, marginal-win %, and AUC with a paired-bootstrap CI, time-held-out — `fba-ml-evaluator`. Only then are per-category importances worth reading.
4. **Data-quality pass** on the `backtest_rows.category` case-mismatch Claude Code flagged (e.g. `electronics_accessories` vs display forms) so category slices are clean.

## Bottom line
The collection engine is working and the volume is real, but **the current labels overstate how often a buy "profits,"** because the cost assumption is generous and the sampled prices are out-of-band. This doesn't threaten the guardrails (shadow-only, no auto-promote, hard gates outside ML — all intact) — it means the ranker's apparent skill is not yet real. Fix the price band and the label definition, then re-evaluate.
