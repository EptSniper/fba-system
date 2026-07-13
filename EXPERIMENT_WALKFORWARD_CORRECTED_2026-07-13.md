# Walk-forward — CORRECTED run (supersedes the earlier same-day report)

**Author:** Cowork, 2026-07-13. Prompted by Codex's read-only audit, which correctly found the first walk-forward mixed two label definitions (~9,197 rows old `est_profit>0` + ~1,487 rows new `$3 & 30% ROI` gate), so its 0.854 AUC could reflect the label-version cohort, not sourcing skill. This run fixes that. Still a BASELINE experiment, NOT promotion evidence; `scoring.rankingChampion` stays `rule`.

## Fixes applied vs the first run
- **One consistent label** recomputed from stored economics for every row: `y = est_profit ≥ $3 AND est_profit/landed_cost ≥ 0.30` (0.25 for grocery). No mixed label-versions.
- **`category` excluded from the model** (production excludes it) — used only for slices.
- **ASIN-disjoint holdout** added (unseen products), plus one-window-per-ASIN to expose row-reuse inflation.
- **Feature ablation** (fee-only vs core vs full) to test "real edge vs re-deriving the cost formula."
- **Learning curve** vs a fixed recent time holdout, to answer "is collecting toward 10k still buying signal?"
- 13,408 labelable rows (2025+), 2,057 unique ASINs.

## Results
**Base rate (one consistent label): 0.606 overall, 0.475 in the $8–60 band** — confirms the old 0.85 was inflated; the label now genuinely varies.

**1. Purged walk-forward (60d), full features:** folds 0.815 / 0.797 / 0.847 / 0.804 / 0.818 → **mean AUC 0.816, lift@10% ~1.49**, stable across time.

**2. ASIN-disjoint holdout (unseen products):** all-windows **AUC 0.833 / lift 1.54**; one-window-per-ASIN **0.807 / 1.53**. It generalizes to products never seen in training — learning patterns, not memorizing. Row-reuse inflation is small (~0.026).

**3. Feature ablation (does full beat fee-only?):** fee-only (price, weight) 0.791 → core-market 0.825 → full 0.833 (lift 1.37 → 1.52 → 1.54). Market features (offers, rank, demand, competition, trends) add real value beyond the fee mechanics — the model is NOT merely re-deriving the cost formula.

**4. Learning curve (fixed recent holdout):** 250 ASINs 0.786 → 500 0.810 → 1,000 0.814 → 1,500 0.816. **Plateaus by ~500–1,000 ASINs.** More raw volume toward 10k barely helps on this label.

## What it means
- The honest label unlocks real, trustworthy signal: ~0.82 AUC, lift ~1.5, generalizing to unseen products, with market features contributing beyond price/weight. That's a genuinely useful ranker-in-waiting.
- **Volume is no longer the bottleneck — label and feature quality are.** Collecting toward 10,000 ASINs will not materially improve this. Effort should shift to: real-cost labels (matcher), better features, and breadth into *new regions* (not more of the same).

## Honest caveats
- Cost is still simulated at 50% of price, so this is "rank given simulated economics," not buy-grade. Real matched costs (+ paper-traded/realized outcomes) are what make it buy-grade.
- `est_profit` was computed at ingest under possibly-varying fee math; this run applies one consistent *threshold* but not a full recompute from raw histories (Codex's residual point — needs archived payloads).
- Baselines were prevalence + fee-only, not the exact deterministic champion (not easily reproduced in the sandbox). Productionizing should score the real champion inside each fold.
