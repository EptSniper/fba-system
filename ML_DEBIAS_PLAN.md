# ML de-bias plan — widen the training corpus (top ML priority)

Owned by `fba-scout-strategist` (collection universe) + `fba-ml-data-engineer` (dataset assembly), monitored by
`fba-ml-evaluator`, re-checked by `fba-leakage-auditor`. Governed by `amazon-fba-oa/references/ml-doctrine.md` §3.
Guardrails unchanged: hard gates stay outside ML; the caps below are **collection/sampling config**, not buy
thresholds; propose them via `fba-brain-updater` for Mehmet's OK.

## The problem, measured (Supabase `backtest_rows`, 2026-07-09)

- **Category:** toys **82.5%**, shoes 15.7%, clothing 0.8%, none 0.9% — effectively ONE category.
- **Brand:** 67 brands, but top-5 = **37%**, Crocs 15.6% + Jellycat 13.9% = **~30%**.
- ~750 rows / ~90 ASINs. A ranker trained on this learns "toys / Crocs / Jellycat," not generalizable profit signal.

## Targets (what "balanced enough" means)

- **No single category > 30%** of the corpus (toys is 82.5% today).
- **No single brand > 6%**, and **top-5 brands < 20%** combined (Crocs alone is 15.6% today).
- **≥ 10 major Amazon categories** represented with a real number of ASINs each.
- Grow distinct brands steadily; measure concentration (HHI) trending down every training run.

## Lever A — collection universe (`fba-scout-strategist`)

Make successive collector runs explore *different* market regions instead of re-scanning the same toys brands.

1. **Category rotation cursor.** Add an ordered list of major OA categories and advance a cursor each hourly/daily
   collector run so each run's Product Finder pass targets the next categories, not whatever the hints surface.
   Seed list (tune later): Toys & Games, Home & Kitchen, Grocery & Gourmet, Health & Household, Beauty & Personal
   Care, Office Products, Sports & Outdoors, Tools & Home Improvement, Pet Supplies, Baby, Arts/Crafts & Sewing,
   Automotive, Patio/Lawn & Garden, Musical Instruments, Industrial & Scientific, Electronics accessories.
2. **Keepa Product Finder recipe per category** (same gates as `ai-brain.json`, just varied region):
   Sales Rank 0–200k (top band), Amazon out-of-stock, New offer count 3–25, price $8–$60, then **rotate a
   secondary axis** across runs — rank sub-bands (0–30k / 30k–90k / 90k–200k), price bands ($8–20 / $20–40 /
   $40–60), and 90-day drop% buckets — so you sweep the whole surface, not one corner.
3. **Hints order, never gate.** Deal hints / friendly brands may reorder *within* a run's candidates, but must
   never restrict which categories/brands are eligible. Explicitly allow brands never seen before.
4. **Breadth-first token spend (Pro trickle).** Backtest/history tokens go to **unseen** brands/categories first
   (1 history token ≈ 7 labeled rows). Do NOT re-backtest the ~90 toys ASINs already in the corpus; point the
   backtest sampler at categories currently at ~0 rows.

## Lever B — dataset assembly caps (`fba-ml-data-engineer`)

Even with broader collection, enforce balance when building the training set so no cell dominates the objective:

1. **Per-brand cap:** when a brand exceeds ~6% of assembled rows, subsample its windows (keep the most
   informative / most recent per ASIN) instead of dropping ASINs; never let one brand's label pattern dominate.
2. **Per-category cap:** cap any category at ~30%; if toys exceeds it, downsample toys rows to the cap for the
   training set (keep the raw rows in the lake — cap the *training assembly*, not the archive).
3. **Class balance:** report and, if needed, weight the ~79%-positive imbalance (ranking-aware, not naive accuracy).
4. **Fill the gaps:** each build emits the under-represented brand/category cells; feed that list back to
   `fba-scout-strategist` as the next collection priority (a closed loop toward balance).

## Config to propose via `fba-brain-updater` (Mehmet's OK)

Add a `learning.sampling` block to `ai-brain.json` (single source; scout reads it):

```json
"learning": {
  "sampling": {
    "categoryRotation": ["toys","home_kitchen","grocery","health_household","beauty","office","sports_outdoors","tools","pet","baby","arts_crafts","automotive","garden","musical_instruments","industrial","electronics_accessories"],
    "maxBrandCorpusShare": 0.06,
    "maxCategoryCorpusShare": 0.30,
    "top5BrandShareAlarm": 0.20,
    "breadthFirstBacktest": true,
    "source": "ML de-bias plan 2026-07-09 — collection/sampling config, not buy gates"
  }
}
```

## Monitoring (`fba-ml-evaluator`) + safety

- Every training run + the daily digest must print concentration: top-brand %, top-5 %, distinct brands, distinct
  categories, category shares, HHI — and **alarm to Discord** if any category > 30% or two brands > 25%.
- Report **per-category and per-brand metric slices** so a model that only works on toys/Crocs is caught before promotion.
- `fba-leakage-auditor` re-confirms features stay point-in-time after any sampling change (sampling shouldn't touch
  features, but verify). No hard-gate changes; no auto-promotion; no auto-buy.

---

## Paste-ready prompt for Claude Code

```
Read amazon-fba-oa/references/ml-doctrine.md and ML_DEBIAS_PLAN.md. This is the top ML priority: the training
corpus is skewed (toys 82.5%, Crocs+Jellycat ~30%). Use the ML crew — fba-ml-lead to coordinate,
fba-scout-strategist for the collection universe, fba-ml-data-engineer for the dataset caps, fba-ml-evaluator
for monitoring, fba-leakage-auditor to re-verify.

Do:
1. fba-scout-strategist + fba-ml-data-engineer: implement Lever A (category-rotation cursor + varied Product
   Finder recipe + breadth-first backtest token spend on UNSEEN categories, not the ~90 toys ASINs) and Lever B
   (per-brand ~6% and per-category ~30% caps at TRAINING-ASSEMBLY time only; raw lake keeps everything).
2. fba-brain-updater: propose the learning.sampling block in ai-brain.json (caps + categoryRotation + alarms) and
   STOP for Mehmet's OK before writing it — it changes what the model sees.
3. fba-ml-evaluator: add concentration reporting (top-brand %, top-5 %, distinct brands/categories, HHI, category
   shares) + per-brand/category metric slices to every training run and the daily digest; Discord-alarm if any
   category >30% or two brands >25%.
4. fba-leakage-auditor: sign off that features remain point-in-time after the sampling changes.
5. Seam/regression tests for the caps (a brand/category over its cap is actually subsampled at assembly). Full
   suite green. Journal a Session entry. No auto-promotion, no auto-buy, no secrets printed.

Report back: new category/brand distribution after the first debiased collection pass, and the concentration
trend vs today (toys 82.5%, top-5 37%).
```
