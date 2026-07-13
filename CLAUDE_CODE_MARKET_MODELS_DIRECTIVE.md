# Claude Code directive — productionize the 3 cost-free market models into a saved harness

Paste the block below into Claude Code. These three models are validated (EXPERIMENT_SAFECOST_QUANTILE_V1.md) — this turns the sandbox experiments into a reproducible, shadow-only pipeline. Guardrails: ALL shadow-only; `scoring.rankingChampion` stays `rule`; nothing promotes or buys; no in-place production `UPDATE`s; brain/migration via the proper skill + Mehmet approval; `fba-code-reviewer` + `fba-qa-tester` before ship; `fba-session-journal` at the end. Route via `fba-ml-lead` + `fba-ranker-architect` + `fba-ml-evaluator`.

## Goal
Build a reproducible training + evaluation harness for three cost-free market models, trained on the existing `backtest_rows`, saved as versioned artifacts, reported to `ranker-report.md`. None feeds a buy decision yet — they run in shadow beside the rule champion.

## Label consistency (do this first — no destructive writes)
Derive the consistent v2 label **at read-time** from the stored `est_profit` + `landed_cost` columns (both 100% populated) — do NOT run an in-place `UPDATE` on `backtest_rows` (that destroys provenance; the permission system correctly blocks it). Optionally add a `label_version` column later via a reviewed migration. `net = est_profit + landed_cost` recovers the actual future Amazon net proceeds independent of the 50% cost assumption.

## The three models (identical rows/folds/features)
Use ONLY pre-decision point-in-time numeric features; exclude brand/category from the model (use category only for evaluation slices). Feature set = core market: `price, weight_lb, sales_rank, est_sales, offers, avg_price_90, avg_offers_90, avg_sales_rank_90, oos_90, amazon_bb_share` (+ `category_trend_ratio, days_to_prime_day` if their point-in-time validity/coverage is confirmed — the calendar/trend/eBay extras did NOT beat core, so keep the set lean). LightGBM params (fixed seed): n_estimators 300–400, num_leaves 15–31, learning_rate 0.03, min_child_samples 40, subsample/colsample 0.8, reg_lambda 1.0.

1. **Safe-cost estimator (LGBMRegressor, objective=quantile, alpha=0.10).** Target `y = min(net − 3, net/(1+r)) / price_T0`, r = 0.30 (0.25 grocery), clipped [−1, 2]. Skip (don't zero) rows where the future window is genuinely censored. **q=0.10** is the deployable conservative bound (validated: overprediction 0.15 ≤ 0.20). Also train a q=0.50 companion for expected-headroom display only.
2. **Price-crash alarm (LGBMClassifier, class_weight=balanced).** Target `price_at_horizon < 0.70 × price_then` (require both present). Validated AUC 0.71 / lift@10% 3.4.
3. **Seller-swarm alarm (LGBMClassifier, class_weight=balanced).** Target `offers_at_horizon ≥ 1.5 × offers_then` (require `offers_then > 0`, both present). Validated AUC 0.76 / lift@10% 3.5.

## Evaluation harness (the reproducible part)
Run every model on THREE split views, always **weighting/bootstrapping by ASIN, not row**:
- ASIN-disjoint holdout (unseen products), purged 60-day walk-forward (time transfer), and a joint future+unseen-ASIN locked test as the conservative verdict. Assign ASIN cohorts before feature/model selection.
- Baselines each model must beat: a constant/prevalence baseline AND a regularized linear/quantile baseline (if linear ties, keep linear). Score the deterministic rule champion inside each fold for the classifiers.
- Metrics — regression: pinball@q (primary), overprediction rate (must be ≤ 0.20 for the conservative bound), coverage, MAE. Classifiers: AUC, average precision, **lift@10% / top-K at review capacity**, Brier/calibration. Report all sliced by category / price band / missingness, with sample counts.
- Fit all imputation/scaling/calibration on the training fold only.

## Save (so it's reproducible — this was the gap Codex flagged)
Per run persist: dataset content hash, fold date boundaries + ASIN membership, out-of-fold predictions, exact params/seed/library versions, per-slice metrics, and the model artifacts → Supabase `models/` bucket (shadow paths, e.g. `market/safecost_q10/<date>/`). Append a run summary to `learning-hub/tracking/ranker-report.md`. Never overwrite the serving champion.

## Guardrails / scope
- All three are SHADOW challengers. `scoring.rankingChampion` stays `rule`; no auto-promotion, no auto-buy, hard gates unchanged.
- These predict market behavior only. A real buy still needs: verified identity + real retail cost + fee/ROI math + eligibility + human approval (V1_ACCEPTANCE_CONTRACT.md).
- Do NOT wire outputs into the live queue ordering or the buy path yet — that waits for the prospective paper cohort to validate them against real costs.
- Reference: EXPERIMENT_SAFECOST_QUANTILE_V1.md (results), CLAUDE_CODE_ML_RIGOR_DIRECTIVE.md (methodology), V1_ACCEPTANCE_CONTRACT.md (the bar for "reliable").

## Exact first step
Build the read-time v2 label + the safe-cost q=0.10 model with the ASIN-disjoint + purged-walk-forward harness and saved artifacts; confirm it reproduces the report's numbers (pinball ~0.024 / overprediction ~0.15 at q0.10) before adding the two alarms. Then journal.
