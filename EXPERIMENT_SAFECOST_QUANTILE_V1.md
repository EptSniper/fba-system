# Safe-Cost Quantile Benchmark v1 — results

**Author:** Cowork, 2026-07-13. Runs Codex's recommended spec (journal 2026-07-13, "LightGBM conservative maximum-safe-cost model"). BASELINE experiment, NOT promotion evidence; `scoring.rankingChampion` stays `rule`.

## Spec (frozen)
- **Dataset:** `backtest_rows`, 2025-01-01+, `price>0` and `est_profit`/`landed_cost` present → 13,408 rows / 2,057 unique ASINs. (Snapshot pulled 2026-07-13.)
- **Target (cost-free):** `net = est_profit + landed_cost` (recovers actual future Amazon net proceeds independent of the 50% cost assumption). `max_safe_cost = min(net − 3, net/(1+r))`, r=0.30 (0.25 grocery). Learning target `y = max_safe_cost / price_at_T0`, clipped [−1, 2].
- **Decision quantile:** q = 0.20 (conservative ceiling — ~80% of true safe ratios should sit at/above the prediction if calibrated).
- **Models on identical rows/folds:** constant q20 (no features) · linear quantile (`QuantileRegressor`, median-impute+scale) · LightGBM quantile q20 (fee / core / full feature sets) · LightGBM q50 companion.
- **Feature sets (numeric, point-in-time; no brand/category in model):** fee = price, weight. core = fee + sales_rank, est_sales, offers, avg_price_90, avg_offers_90, avg_sales_rank_90, oos_90, amazon_bb_share. full = core + calendar/trend/bts/median-active-price.
- **LightGBM params (fixed seed):** objective=quantile, n_estimators=400, num_leaves=31, learning_rate=0.03, min_child_samples=40, subsample/colsample=0.8, reg_lambda=1.0.
- **Splits:** primary = ASIN-disjoint holdout (30% of ASINs, seed 20) = unseen products; secondary = 5-fold purged (60d) walk-forward = time transfer.
- **Metrics:** pinball@20 (primary), overprediction rate (pred > actual = the dangerous error; want ≈0.20), coverage (actual ≥ pred; want ≈0.80), MAE (secondary), top-decile headroom.

## Results — primary (ASIN-disjoint, unseen products)
| model | pinball@20 | overpred | coverage | MAE |
|---|---|---|---|---|
| constant q20 (no features) | 0.0500 | 0.17 | 0.83 | 0.170 |
| linear quantile (full) | 0.0471 | 0.20 | 0.80 | 0.154 |
| LightGBM q20 (fee-only) | 0.0345 | 0.21 | 0.79 | 0.119 |
| LightGBM q20 (core) | **0.0321** | 0.22 | 0.78 | 0.111 |
| LightGBM q20 (full) | 0.0318 | 0.23 | 0.77 | 0.109 |
| LightGBM q50 companion | 0.0435 | 0.48 | 0.52 | 0.087 |

Top-decile by predicted safe-cost: actual median safe-ratio 0.612 vs 0.542 overall.

## Results — secondary (purged 60d walk-forward, LightGBM q20 full)
folds pinball@20: 0.0345 / 0.0336 / 0.0308 / 0.0342 / 0.0374 → **mean 0.0341**; overpred 0.20–0.26; coverage 0.74–0.80. Stable across time.

## Verdict (per Codex's interpretation rules)
- **LightGBM q20 clearly beats the constant and linear baselines** (0.0321 vs 0.0471 vs 0.0500, ~32% lower pinball than linear) on unseen ASINs and holds up forward in time → keep it as the market/safe-cost challenger; the linear model does NOT tie, so the tree model earns its complexity.
- **Core features are the model to keep.** full ≈ core (0.0318 vs 0.0321 = noise); the calendar/trend/eBay features add nothing over core → drop the dead features.
- **Calibration is close but slightly optimistic:** overprediction ~0.22–0.26 vs the 0.20 target — as a *conservative* buy bound it is a hair aggressive. **Fix: apply a frozen safety buffer, or train q=0.15**, before this bound ever informs a real buy.

## Caveats / reproducibility
- Cost is still simulated (net recovered from the 50%-assumption economics); this validates that the safe-cost ceiling is *learnable from Keepa*, not that a specific real deal profits. Buy-grade needs verified real T0 costs + prospective paper outcomes (V1_ACCEPTANCE_CONTRACT.md).
- `est_profit` was computed at ingest under possibly-varying fee math (Codex's residual point) — a full recompute from raw histories would be stronger.
- This report + the frozen spec above make the result reproducible. Productionizing (saved harness in `train_ranker.py` with dataset hash, fold membership, OOF preds, artifact) is CLAUDE_CODE_ML_RIGOR_DIRECTIVE.md items 3 & 6.

## Follow-up runs (2026-07-13, same dataset)

### Quantile calibration (ASIN-disjoint) — pick the conservative bound
| quantile | pinball | overprediction (dangerous) | coverage |
|---|---|---|---|
| q0.10 | 0.0239 | 0.15 | 0.85 |
| q0.15 | 0.0300 | 0.21 | 0.79 |
| q0.20 | 0.0345 | 0.26 | 0.74 |

The model runs slightly optimistic (overprediction > nominal q). **Deploy at q=0.10** (overprediction 0.15 ≤ 0.20 target) as the genuinely conservative safe-cost ceiling, or q0.20 minus a frozen buffer.

### Adverse-event models (ASIN-disjoint, LightGBM classifier, core features)
| target | base rate | AUC | lift@10% | n |
|---|---|---|---|---|
| severe price crash (>30% drop @60d) | 0.04 | 0.712 | 3.38 | 13,785 |
| seller swarm (offers ≥ +50% @60d) | 0.09 | 0.756 | 3.45 | 13,130 |

Both are strong, decision-useful downside filters: top-decile-risk picks are ~3.4× more likely to actually crash / get swarmed than average — the two failure modes Codex prioritized, learnable from Keepa alone, no purchases. Labels require `price_at_horizon`/`offers_at_horizon` present (censored rows skipped, not zeroed).

## Next
1. **Deploy safe-cost at q=0.10** (conservative bound) + pair the two adverse-event alarms as downside gates.
2. Pair all three with real T0 retail costs from the verified-match paper cohort (V1 contract §12) for the buy-grade test.
3. Productionize as a saved harness in `train_ranker.py` (CLAUDE_CODE_ML_RIGOR_DIRECTIVE.md items 3 & 6): dataset hash, fold membership, OOF preds, artifact.
