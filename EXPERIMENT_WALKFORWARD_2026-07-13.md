# Experiment — walk-forward CV baseline (fba-ml-evaluator + ranker-architect + leakage-auditor)

**Run:** Cowork sandbox, 2026-07-13. LightGBM 4.6, 10,684 backtest_rows (2025-01-02 → 2026-05-13, pre-2025's 252 degenerate all-positive rows dropped). **This is a BASELINE experiment, not promotion evidence.** `scoring.rankingChampion` stays `rule`.

## Method
Expanding-window walk-forward by `simulation_date`, 5 folds, with a **60-day purge/embargo** between train end and test start so a training row's +60d label cannot overlap the test feature window (temporal-leakage guard). Features = the point-in-time `features_snapshot` numeric set + `category` (LightGBM categorical). `class_weight=balanced`, small capacity (num_leaves=15, min_child=40, 300 trees, reg). Metrics vs the base rate: AUC, PR-AUC, lift@top-10%.

## Result
Base rate **0.850** (85% of windows labeled "would have profited").

| fold | train | test | base | AUC | PR-AUC | lift@10% |
|---|---|---|---|---|---|---|
| 0 | 3237 | 1072 | 0.842 | 0.853 | 0.964 | 1.16 |
| 1 | 3955 | 1091 | 0.851 | 0.843 | 0.961 | 1.15 |
| 2 | 4795 | 976 | 0.857 | 0.883 | 0.972 | 1.16 |
| 3 | 6093 | 1140 | 0.839 | 0.829 | 0.943 | 1.12 |
| 4 | 7061 | 1095 | 0.846 | 0.860 | 0.961 | 1.16 |

**Mean AUC 0.854, tight across folds** (stable in time — no temporal overfitting).

## Honest reading
1. **The harness is valid and the model is stable** — walk-forward with purge is the right methodology and it holds up across five time windows.
2. **The 0.85 AUC is flattered by the 85% base rate.** PR-AUC ≈ base rate (a no-skill classifier scores ~0.85 PR-AUC here), and **lift@10% is only ~1.15** — top-decile picks profit ~98% vs the 85% floor. The model barely beats "buy everything."
3. **Signal exists only where the label varies** (pooled out-of-fold AUC):
   - Real discrimination: garden (base 0.32, AUC 0.75), arts_crafts (0.48, 0.79), industrial (0.55, 0.78), grocery (0.90), beauty (0.98), toys (0.85), musical (0.85).
   - Near coin-flip (degenerate label): tools (base 0.97, AUC 0.58), baby (0.93, 0.50), clothing (0.92, 0.54), shoes (0.62), office (0.66), sports (0.71).
4. **Feature importances** (weight_lb, avg_price_90, price, category) confirm the model keys on price/fee mechanics — the fixed-50%-cost labeling assumption — not demand/competition edge.
5. **Overfitting is NOT the issue** — folds are stable; the model is if anything *under-fit to real signal* because the label is near-constant. The ceiling is the label.

## Why this matters / next
The artifact (LEAKAGE_AUDIT_2026-07-13.md) caps the model: it can't learn to separate winners from losers where ~everything is labeled a winner. But the **0.75–0.98 AUC in mixed-label categories proves learnable signal is there** once the label varies. Sequence:
1. Fix the label to the real buy gate (profit ≥ $3 AND ROI ≥ 30%) on **real buy costs from the matcher**, and fix the $8–60 dealfeed price-band filter (labels stop being ~85% positive).
2. Re-run THIS exact walk-forward harness → the real "did the model get better" test. Watch lift@10% and the high-base-rate categories, not raw AUC.
3. Productionize: wire walk-forward CV (per-fold AUC + lift + per-category slice) into `scout/train_ranker.py` so every training run reports the fold distribution, not a single group-by-ASIN split. `rankingChampion` promotes only on consistent multi-fold lift over the champion — never on a single AUC.
