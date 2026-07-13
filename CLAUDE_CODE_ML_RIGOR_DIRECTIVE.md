# Claude Code directive — ML rigor fixes from Codex's audit + Cowork's corrected experiment (2026-07-13)

Paste the block below into Claude Code. These are durable methodology fixes that came out of Codex's read-only ML audit (journal, 2026-07-13) and Cowork's corrected walk-forward (EXPERIMENT_WALKFORWARD_CORRECTED_2026-07-13.md). They protect the ML from fooling itself. Guardrails unchanged: shadow-only, no auto-promote (`scoring.rankingChampion` stays `rule`), no auto-buy, brain/migration via the proper skill + Mehmet approval. Route via `fba-ml-lead`; `fba-code-reviewer` + `fba-qa-tester` on changes; journal at the end.

Do these in priority order.

1. **Never train or evaluate on mixed label versions (highest priority).** The live ranker's "READY" (challenger AUC 0.872 vs champion 0.695) is trained on a corpus that mixes the OLD `est_profit>0` label with the NEW `$3 & 30% ROI` gate — so its metric can reflect which rows predate the label change, not sourcing skill. Fix: **backfill the historical `backtest_rows` to the v2 label** — recompute `would_have_profited` from stored economics (`est_profit ≥ 3 AND est_profit/landed_cost ≥ 0.30`, 0.25 grocery) for the ~9,449 pre-fix rows — OR add a `label_version` column and train on one version only. Until then, treat every ranker metric as unreliable. `fba-ml-data-engineer` + `fba-leakage-auditor`.

2. **Fix the promotion-evidence logic.** The ranker's 8 "consecutive wins" are 8 correlated expanding snapshots (same data plus a few rows), not 8 independent validations — so the READY gate is meaningless. Promotion evidence must require: consistent lift over the deterministic champion across **independent, time-separated** holdouts, on a **single consistent label**, ASIN-weighted. Keep `rankingChampion=rule`; do not promote on the current signal. `fba-ml-evaluator` + `fba-ml-guardian`.

3. **Make the walk-forward a real, saved harness in `train_ranker.py` — not a one-off report.** Persist: dataset content hash, fold date boundaries, out-of-fold predictions, ASIN-clustered confidence intervals, per-category sample counts, seed, exact params. Evaluate three splits (ASIN-group holdout / purged walk-forward / joint future+unseen-ASIN), **weight by ASIN not row** (report the row-reuse inflation — Cowork measured it small but real), score the **deterministic champion inside each fold**, and **exclude `category` from the model matrix** (production excludes it; use it only for slices). `fba-ranker-architect` + `fba-ml-evaluator`.

3.5 **Judge by lift@k and PR-AUC, not raw AUC alone, and state prevalence.** (Codex's precision point: AUC is prevalence-invariant; PR-AUC and top-k lift are what move with the winner-rate and matter for a shortlist.)

4. **Redirect collection: volume is no longer the bottleneck.** Cowork's learning curve plateaus by ~500–1,000 ASINs on the current label — collecting toward 10k barely helps. Shift effort from raw count to: (a) real-cost labels (the matcher), (b) feature quality, (c) breadth into genuinely new regions (source diversity is ~0 non-dealfeed today — add explore/onpolicy/storefront). Keep breadth, stop optimizing for sheer volume. `fba-scout-strategist`.

5. **Fix or drop dead features.** eBay inputs are 100% missing, brand-trend values 99.55% missing, avg-offers 42.8% missing. Either fix the producers or remove them from the feature set — they're noise the model must ignore. `fba-feature-engineer`.

6. **Build the cost-free target as the next real experiment.** A regression/quantile model for **maximum safe buy cost** (or safe-cost ratio) from future net proceeds + the $3/30%-ROI constraints — removes the fake 50% cost from the target entirely; a real retailer cost is compared deterministically at decision time. Pair with downside tasks (60-day price drawdown, seller-count growth). `fba-ranker-architect` + `fba-ml-evaluator`.

7. **Keep shadow + real-cost matched leads as UNTOUCHED external validation** when they mature (178 shadow rows pending). No model is buy-grade until it survives forward shadow outcomes + calibration + abstention on unfamiliar products + eventually realized outcomes.

## Notes for the record
- Cowork's corrected experiment (consistent label): base rate 0.606 (0.475 in-band); walk-forward AUC ~0.816 / lift ~1.49; unseen-ASIN AUC 0.833; full beats fee-only (0.791→0.833) so there IS market edge; learning curve flat past ~1k ASINs.
- Codex was right that the first (mixed-label) 0.854 was not trustworthy. It also correctly flagged Cowork's earlier "gate leak" framing as wrong — price-band/offers are soft-by-design, not hard gates (Claude Code S65 independently confirmed). No hard-gate change from that.
