# Keepa throughput + unbiased-collection plan — reach 10k unique ASINs on the Pro plan

**Author:** Cowork (fba-scout-strategist + fba-ml-data-engineer + fba-leakage-auditor + fba-ml-evaluator + fba-ml-guardian), 2026-07-11
**Goal:** raise unique-ASIN/day toward the plan ceiling, get to **10,000 unique ASINs**, keep collection brand-agnostic and maximally broad, with leakage/overfitting/guardrails signed off.
**Status:** DIAGNOSIS + RANKED ACTIONS for Claude Code to execute. No hard gate, model promotion, or purchase is touched. Brain/`config` edits below need Mehmet's approval via `fba-brain-updater`.

---

## 1. The real numbers (measured live 2026-07-11)

- Corpus: **3,578 rows / 537 unique ASINs**, all label tier `backtest`, **87.3% positive** labels.
- Source mix: **456 ASINs `dealfeed`** (brand-agnostic), 81 legacy brand-seed (`null`). Good — collection is already mostly brand-agnostic.
- Brand concentration: Crocs 3.4%, Jellycat 3.4% (was ~15% each pre-de-bias). **Fixed.**
- Category: tools 23% / toys 19% / sports 18% / grocery 15% (top-4 ≈ 75%), 17 categories present.
- **New-ASIN/day is no longer 63.** The 07-10/11 fixes already lifted it: 07-05 **37**, 07-08 **44**, 07-09 **152**, 07-10 **213**, 07-11 **91** (partial). But **07-06 and 07-07 produced zero** — whole days are being lost.

## 2. The ceiling math (why the plan is NOT the first problem)

Keepa **Pro** = 1 token/min = **~1,440 tokens/day**, bank caps at 60. Running the collector hourly captures ~100% of generation (60/hr refill = 60 bank). **You cannot exceed ~1,440 tokens/day without more Keepa capacity** — that part is a hard fact.

Cost to add one **new unique ASIN** to the corpus:
- dealfeed discovery: 5 tokens / up to 150 ASINs ≈ **0.03 tok/ASIN**
- `query_history` pull (builds ~6–7 rows across sim-dates): **1 tok/ASIN**
- ≈ **~1.03 tok/new ASIN → ~6.7 rows**

So the *theoretical* ceiling is **~1,000–1,300 new ASINs/day** if ~90% of the bank goes to dealfeed-discovery + history. We're getting 150–213 on good days and 0 on bad days. **The gap is allocation + reliability + yield, not raw capacity.** 10k is reachable in **~2–4 weeks with zero spend.**

Key architectural facts driving this (from the code):
- **Product Finder is REQUEST_REJECTED on the Pro plan** (`keepa_client.find_candidates`, Session 51). That's why discovery leans on the `/deal` firehose (cheap) and, on the legacy path, a **10-tok/term brand *search*** fallback (expensive + the old bias vector).
- `enrich()` = **4 tok/ASIN** (buy-discovery, Tier 2) vs `query_history()` = **1 tok/ASIN** (training rows, Tier 3). Every token spent enriching is 4× less efficient for the ML corpus.
- `collect_hourly` splits each hour's bank: Tier 1 shadow rechecks (≤25%), Tier 2 hint-led enrich discovery, Tier 3 backtest (≥35% reserve). `corpusAcceleration` (already ON, approved 07-10) skips Tier 2 while a backlog exists — good, keep it.

## 3. Ranked actions (no-cost first)

### A. Fix dispatch reliability — **biggest real-world leak right now**
07-06 and 07-07 collected **nothing**. A missed hour = up to 60 tokens (~55 ASINs) **permanently lost** (bank overflows at 60). GitHub cron is best-effort and drops runs under load.
- Confirm the local dispatcher (`scripts/dispatch_keepa_collect.ps1`, `targetDispatchMinutes:45`) is actually running 24/7, or move the schedule to a reliable trigger. Add a dead-man's-switch alarm (the `HEALTHCHECK_URL` hook already exists in `run_daily.py`) that pings Discord when a day collects < N new ASINs.
- **Expected gain:** removes the zero-days; alone lifts the *average* materially.

### B. Don't pay history tokens for ASINs that yield nothing
Two wasted-token classes, both fixable with **free** pre-checks before the `query_history` batch in `backtest.run_backtest`:
1. **Already-collected ASINs** — filter `todo` against `select asin from backtest_rows` (or the `processed_asins` state). A re-pull costs 1 token and produces 0 new ASINs. State persistence now works, but a DB-side `NOT IN` guard is the belt-and-suspenders.
2. **Too-new listings** — dealfeed "recently changed" products often have < `MIN_HISTORY_DAYS` (90d) of history, so `build_rows_for_asin` emits **0 rows** but you still paid 1 token. Verify the 0-row rate (compare `asins_processed` vs distinct ASINs in `backtest_rows`); if high, add a cheap age/first-tracked pre-screen or bias discovery toward established listings.
- **Expected gain:** raises rows-per-token and new-ASINs-per-token; likely the second-biggest lever after reliability.

### C. During the collection sprint, route ~all tokens to 1-tok history
- Keep `corpusAcceleration.enabled=true`, `skipTier2WhilePending=true`, `minPendingAsins=1` (already set). This pauses the 4-tok brand-seeded enrich discovery while a backlog exists — you're collecting data, not buying, so this is the right trade for now.
- Consider temporarily lowering `TIER1_RESERVE_FRACTION` (0.25) so shadow rechecks (4-tok enrich) don't skim a quarter of every hour — **but** don't zero it; shadow validation is how the ranker eventually earns promotion. Suggest 0.15 during the sprint, revisit after.
- Keep a *small* dealfeed backlog primed (a few pages) so `sampling_skipped` stays true and ~100% of each run's cap converts to history rows.

### D. Add storefront stalking (`seller_query`) as a second cheap breadth source
`seller_asins()` already exists (guarded). One `seller_query` returns a whole storefront's ASIN list (**hundreds of ASINs**) for ~10 tokens — brand-agnostic if you **rotate diverse sellers**, and it reaches beyond "currently on-deal" products, which is exactly what sustains new-ASIN yield as the dealfeed's day-to-day overlap grows. Wire a rotating seller cursor (same persisted-cursor pattern as `dealfeed_cursor.json`) feeding ASINs into the backtest backlog tagged `sample_source="storefront"`.
- **Expected gain:** keeps the marginal new-ASIN/token high once the easy deals are exhausted; the single best *new* source to add on the Pro plan.

### E. Keep the discovery surface wide (already built — just verify it's firing)
18 categories × 3 price bands × 3 rank sub-bands × drop% axis rotation is implemented with persisted cursors. Confirm the secondary-axis range filters (`isRangeEnabled`/`isFilterEnabled`) are actually taking effect live (per-band yields > 0) — they were flagged UNVERIFIED. If a band is persistently dry it self-widens, but verify from `dealfeed_yield_stats.json`.

## 4. When the plan upgrade *is* the answer

Only if you want **sustained > ~1,400 new ASINs/day**, or you want the cleanest structural fix:
- **Keepa API add-on / higher tier** raises tokens/min **and unlocks Product Finder** (10 tokens → up to 10,000 ASINs = **~0.001 tok/ASIN**, the cheapest, broadest, least-biased discovery there is). This single upgrade both multiplies throughput and removes the last brand-seed dependency.
- **A second Keepa Pro key** ≈ doubles tokens/min for ~$19–35/mo (cheaper than API tier) — but check Keepa ToS on multiple keys before relying on it.
- **Verdict:** *not required* for 10k. Do A–E first (free, gets you to 10k in ~2–4 weeks). Treat the upgrade as an accelerant for going past the Pro ceiling, not a prerequisite.

## 5. Expert sign-offs

**Bias / randomization (fba-scout-strategist + fba-ml-data-engineer): PASS, with watch-items.**
Collection is brand-agnostic by construction (dealfeed/explore never consult brand lists; buy-discovery seeding is a separate path; avoid-listed brands are still *collected* and flagged `ip_risk`, never silently blended). De-biased from ~30% two-brand to 3.4% each. Watch: category top-4 ≈ 75% — keep **collection maximally broad**, and apply `maxBrandCorpusShare`/`maxCategoryCorpusShare` at **training-assembly** time (down-sample over-represented cells) rather than throttling collection. Storefront (action D) broadens past deal-selection bias.

**Leakage (fba-leakage-auditor): PASS by construction.**
Backtest is strict `< as_of`, split-by-ASIN, reuses `PRE_DECISION_FEATURES` via `db.feature_snapshot`, and censors OOS-at-horizon + stopped-tracking windows (honest skips, not fabricated labels). **Scaling volume 20× introduces no new leakage** — each row is point-in-time regardless of corpus size. Action: confirm the poisoned-future regression test landed (was the one open gap).

**Overfitting / accuracy (fba-ml-evaluator): CAUTION — volume helps variance, not the label skew.**
87.3% positive, all weakest `backtest` tier. More ASINs shrink variance but do **not** fix the positive skew (censoring drops OOS-at-horizon losers, which pushes positives up). Rules: judge only by **AUC + precision/lift@top vs base rate + time-held-out + per-brand/category slices + bootstrap CI** — never raw accuracy (information-free at 87% positive). Track positive-rate drift as the corpus grows; consider retaining honest hard negatives.

**Guardrails (fba-ml-guardian): intact and unaffected.**
Hard gates stay outside ML; ranker is shadow-only and orders nothing that buys; `scoring.rankingChampion` stays `rule` (no promotion) until consistent multi-run time-split wins + a human flip; Keepa overdraw guard holds. Growing the corpus touches none of this.

## 6. Suggested execution order for Claude Code
1. **A** (reliability + alarm) — stop losing whole days.
2. **B** (skip already-collected + 0-row ASINs) — raise yield/token; measure the 0-row rate first.
3. **C** (tier reallocation during sprint) — via `fba-brain-updater`, Mehmet-approved.
4. **D** (storefront source) — biggest new-breadth add; build behind the same cursor pattern.
5. Re-measure new-ASINs/day for 3–4 days; if sustained < ~400/day after A–D, revisit §4.
