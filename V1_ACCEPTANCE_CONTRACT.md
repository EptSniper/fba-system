# v1 acceptance contract — "reliable ML in ~21–28 days, no purchases"

**Author:** Cowork (fba-ml-lead + fba-ml-evaluator + fba-scout-strategist), 2026-07-13, synthesizing Codex's three month-one feasibility audits (journal 2026-07-13) + Cowork's corrected experiments. **Freeze this BEFORE looking at final results.** No numeric gate below may be moved after results are seen.

## 1. The honest claim v1 can make
> On exact, verified deal↔ASIN matches with real T0 retailer costs, inside a supported operating region, v1 ranks opportunities whose price gaps survive current-market paper observation better than the deterministic rule, estimates a conservative maximum safe buy cost, and abstains when uncertain. Purchases still require eligibility + SellerAmp + human approval. **Realized cash profit is not validated without transactions** and must never be claimed.

v1 is a **conservative decision-support ranker + safe-cost estimator**, not a universal winner classifier and not a proof of profit.

## 2. Three separately-validated tasks (each its own metric)
1. **Identity** — is the retailer product exactly the Amazon ASIN (brand/model/pack/size/color/variation)? Metric: audited precision in the accepted band; ambiguous → abstain. A false match invalidates all economics.
2. **Amazon-market durability** — from T0 features only, the distribution of future net proceeds, price retention/drawdown, offer growth, Amazon re-entry, listing survival. Keepa supplies this.
3. **Opportunity ranking** — given verified identity + real T0 cost, is the gap durable vs the model's conservative max-safe-cost? Fee/profit/ROI/eligibility/quantity stay deterministic + human.

## 3. Evidence tiers (report the final claim on the strongest relevant tier; never blend)
identity-gold (hand-verified matches incl. deliberate mismatches) · prospective-paper strong-silver (verified T0 cost frozen before outcome, observed 7/14/21/28d) · historical-market silver (leakage-safe point-in-time Keepa, uniform versioned targets) · assumed-cost backtest weak (the 50%-COGS rows — diagnostics only) · human-verdict bronze (BUY/PASS opinions — telemetry only, never the label) · realized-gold (actual sales — only if Mehmet chooses; never required).

## 4. Frozen T0 fields per paper opportunity (freeze, then never overwrite with a later/better value)
retailer URL · exact product/pack/size/variation · verified ASIN · retailer landed cost (price + tax + ship + prep/inbound est) · source captured-at time · Amazon price + fee estimate + eligibility status · all pre-decision Keepa features · rule score · model score(s) · predicted max-safe-cost + confidence + abstain flag · the frozen BUY/PASS/REVIEW prediction.

## 5. Sampling strata (so evaluation is NOT winner-only)
Stratify the paper cohort across: categories, retailers, brands, price bands, rule pass **and** fail, model high **and** low, plus **random controls**. Include deliberate hard-negative identity traps (wrong count/size/model). Observing only liked candidates makes false-negatives unknowable.

## 6. Checkpoints (multi-horizon, distinct meanings; never relabel a short horizon as a long one)
day 7 (deal decay / price reversal / fast swarm) · day 14 (short sourcing-window stability) · **day 21 = primary acceptance checkpoint** · day 28/30 (corroboration where time permits) · day 60 (later falsification audit; if it contradicts v1, champion reverts or region narrows).

## 7. Acceptance gates — ALL must pass (Mehmet freezes the numbers; suggested starting values in brackets)
1. **Identity safety:** zero critical pack/size/variation mismatch in the accepted band on the audited set; report the binomial lower bound, not just the %. [audit ≥150 pairs; accepted-band precision lower-bound ≥ 98%]
2. **Independent improvement:** challenger **top-K** precision/lift beats the deterministic rule on an untouched **future + unseen-ASIN** set, with an ASIN-clustered interval excluding trivial/negative gain. [K = top 10% of queue; lift ≥ 1.2× rule, CI lower bound > 1.0×]
3. **Downside control:** accepted band's severe-adverse rate (price crash >30%, Amazon dominance, seller swarm, invalid source) stays under a ceiling at day 14/21. [≤ 15%]
4. **Calibration:** higher confidence → measurably lower failure; class-balanced scores calibrated on a time fold or used only for ordering. [monotone reliability curve]
5. **Robustness:** no single category/brand/retailer/repeated-window explains the gain; declare supported slices, abstain elsewhere. [≥3 categories each showing the gain]
6. **Economic truth:** every surfaced opportunity uses verified T0 cost + current fees; min-profit/ROI/worst-case stay deterministic after ML ranking. [$3 profit AND 30% ROI / 25% grocery]
7. **Abstention coverage:** missing identity/cost, out-of-distribution, or safe-cost interval overlapping retail cost → REVIEW. Abstaining is a success, not a failure. [report % abstained; no forced calls]
8. **No leakage:** identical locked opportunities/label/folds for rule vs logistic vs LightGBM; the final prospective cohort is never used for tuning.

If any gate fails at day 28 → **v1 is "not ready," with the exact bottleneck named** (match quality / target quality / missing features / category instability / insufficient lift). The deadline cannot convert weak evidence into reliability.

## 8. Split & benchmark rules
Future + unseen-ASIN evaluation, 60-day purge for 60-day targets, one-ASIN-cluster bootstrap, no same-product leakage. Count **~2,000 unique ASINs as the independence scale, not 13,000+ overlapping rows.** Keep one permanent untouched benchmark + rolling paper cohorts; never tune on the permanent test set. Append-only raw snapshots (source, retrieval time, code/brain/schema version, content hash); recompute derived targets from raw.

## 9. Evidence already in hand (historical-market half — promising)
Cowork's cost-free experiments (13,408 rows / 2,057 ASINs, unseen-ASIN + purged folds):
- Consistent-label ranker: walk-forward AUC ~0.82, lift@10% ~1.5, generalizes to unseen ASINs, market features beat fee-only (real edge). Learning curve flat past ~1k ASINs (volume is NOT the bottleneck).
- **Max-safe-cost model (the cost-free target):** actual safe-ratio mean 0.52 but **a flat 50% buy is unsafe 39% of the time**; model predicts the ratio on unseen products (MAE 0.096, beats flat baseline ~27%, top-decile headroom 0.66 vs 0.51), and predicts "is a 50% buy safe here?" at **AUC 0.83**. Pure Keepa, no purchases.
This establishes the market-durability + safe-cost tasks are learnable now; it is NOT buy-grade until paired with verified T0 costs + prospective paper outcomes.

## 10. The 21–28 day schedule
- **Days 1–3:** freeze this contract + a versioned corpus/benchmark; drop the mixed 50%-COGS binary label from the primary benchmark; derive uniform market targets (net proceeds, 7/14/21/30d price retention, drawdown, offer growth, max-safe-cost) from point-in-time Keepa; set rule/prevalence/logistic/LightGBM baselines.
- **Days 4–7:** pick the simplest market model that beats the rule at top-of-queue; **start the paper cohort** (verified matches + frozen T0 predictions, stratified incl. rejects/controls); build the audited identity match set.
- **Days 8–14:** score day-7 outcomes; measure survival/drawdown/calibration; reject models that don't survive slice/one-window-per-ASIN.
- **Days 15–21:** score day-14/21; define the high-confidence operating region.
- **Days 22–28:** corroborate; ONE locked final eval on the untouched set + paper cohort; pass → approve a shadow/conservative shortlist workflow (`rankingChampion` stays human, no auto-buy); fail → report the exact bottleneck.

## 11. What must NOT be done to hit the deadline
No inflating volume via overlapping windows or cost grids counted as independent products · no in-place relabel without version/provenance · no training on the rule's own BUY/PASS or expert opinion as truth · no lowering identity standards to "match" 9,798 title-only rows · no neural nets / broad tuning (logistic + constrained LightGBM suffice) · no promoting a whole-catalog claim from one good slice · never call a paper outcome realized profit.

## 12. Start the clock (the one time-critical action)
Calendar time is the binding constraint — day 21 evidence needs the cohort frozen ~now. **This week:** manually verify a stratified ~150–300 deal↔ASIN matches from the existing 9,798 deals (review links/identities only — no buying), freeze each one's T0 cost + prediction, schedule 7/14/21-day rechecks. The historical-market model work (§9) runs in parallel and does the heavy statistical lifting.
