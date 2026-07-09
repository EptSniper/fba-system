# ML Doctrine — the single source the ML expert crew obeys

This is the shared backbone for every `fba-ml-*` skill and `fba-scout-strategist`. The ML system's job
is to **learn what to buy** — rank real, sourceable Amazon products by expected profit so a beginner's
limited capital goes to the best candidates. Everything below is non-negotiable unless Mehmet changes it.

**Standing mandate:** any task that touches ML or the command center — data collection, features, training,
serving, evaluation, guardrails, debugging, or the item finder — MUST route through the matching expert in
this crew (see the roster at the bottom). Never hand-roll ML work without the specialist; never let a build
or upgrade skip them. This applies to every current component and every future build/upgrade.

## 1. The pipeline (where ML sits)

`retail deal feeds + Keepa` → **scout item finder** (discovery/sampling) → **hard gates** (rule-based,
`scoring.py` from `ai-brain.json`) → **triage/ranker** (orders survivors) → **Review Queue** (human verdict)
→ `decisions` → realized `outcomes`. The **hard gates stay OUTSIDE ML forever** (eligibility, IP, Amazon-Buy-Box
reject, price band). ML only *orders* what already passed the gates. A model can rank; it can never approve a buy.

## 2. Training data — the real grain (verified 2026-07-08)

- One **`backtest_rows`** row = one **(ASIN × `simulation_date`)** point-in-time sample: `features_snapshot`
  (jsonb, everything knowable as-of that date), the state then vs at `+horizon_days` (~60), and exactly **one
  label** `would_have_profited` (boolean) + a `label_quality` tier.
- One ASIN → **~7 rows** (multiple historical windows). ~1 Keepa history token → ~7 labeled rows.
- **Label tiers, weakest→strongest:** `backtest` (historical simulation — cheap bulk) → `silver` (shadow-outcome
  proxy, matures ~30-60d) → `bronze` (human Review-Queue verdicts) → `gold` (realized purchase outcomes).
  Weight/trust them accordingly; never treat a backtest sim label as equal to a real gold outcome.
- Current corpus (2026-07-08): **~550 rows / 81 ASINs / 67 brands / 4 categories**, class balance ~79% positive.

## 3. BREADTH & anti-bias — Mehmet's explicit rule: collect as much and as varied as possible

The corpus is **skewed today**: Crocs 15.6% + Jellycat 13.9% = ~30% of rows, only **4 categories**. This is
the friendly-brand/hint-led sampling bleeding into training. **Fix and prevent it:**

- The training/sampling universe must be **brand-agnostic and category-diverse** — never restrict collection to
  friendly/hint brands. Hints prioritize *order*, never *membership*. Deliberately sample the long tail.
- Cap any single brand's and single category's share of the corpus; report concentration every training run
  (top-brand %, distinct brands, distinct categories, Gini/HHI). If 2 brands ≥ 25% or categories < ~8, flag it.
- Prefer **stratified sampling** across brand/category/price-band so the model learns generalizable signal, not
  "Crocs = good." Bronze/gold human labels may be scarce and biased — do not let them silently dominate the objective.
- More data always beats clever features here; spend idle tokens on **breadth** (unseen brands/categories), not depth on the same few.

## 4. No leakage — ever

- **Only pre-decision features train.** Outcomes are labels, never inputs. Point-in-time: a row's
  `features_snapshot` may contain nothing knowable only after `simulation_date`.
- Watch temporal seams: the Trends week-boundary bug admitted a weekly bucket whose window crossed the sim date
  (up to 6 days of future search interest) — any windowed/rolling feature must be clipped to strictly-before the sim date.
- **Missing ≠ zero.** Impute missing to **NaN** (LightGBM handles it natively), not 0.0 — a trend ratio of 0 or
  days-to-holiday of 0 are meaningful values. Add explicit `*_stale` / missing flags **as model inputs**, so the
  model can't encode label-tier membership through the mere presence/absence of a feature.
- Never log the scout's own past verdict as its success label (self-confirmation).
- **Train/test split (as-coded 2026-07-09):** a deterministic **group split by ASIN** (`backtest.split_by_asin`)
  — prevents the same ASIN's windows leaking across train↔test (good), but is NOT time-based, so it does not yet
  test temporal generalization; a time-held-out split is a tracked future safeguard.
- **Known low-frequency caveat:** `brand`/`category`/`weight_lb` are looked up once from the present-day product
  and reused across an ASIN's historical windows — acceptable today because brand/category are only grouping keys,
  NOT model features (`NUMERIC_FEATURES` excludes them); revisit if ever promoted to an actual feature.

## 5. The ranker + promotion

- **Model (as-coded 2026-07-09, ground truth):** `lgb.LGBMClassifier(class_weight="balanced")` predicting
  P(would-profit), used to **rank** candidates by that probability, evaluated by **AUC**. It competes as a
  **challenger** against the deterministic triage formula (the champion) in **shadow**. Promote ONLY when it
  *consistently* beats the champion on held-out AUC across multiple runs AND a human flips
  `scoring.rankingChampion` — never on a single run (one win can be small-sample noise; e.g. as the corpus
  de-biased, run 4 flipped from losing to winning ~0.73 vs ~0.69 on only ~186 val rows — promising, not a promote).
  *(Future upgrade target, NOT current: a true
  learning-to-rank objective — `LGBMRanker` lambdarank/NDCG@k with query groups. Where any `fba-ml` skill
  describes lambdarank/NDCG/groups, treat it as the target; this section + `train_ranker.py` are the truth.)*
- **No auto-promotion.** A challenger is promoted only by a human flipping `scoring.rankingChampion`, and only
  after it beats the champion on the held-out split on the metric that matters (currently **AUC** on the
  group-by-ASIN split). Default is **shadow mode** (the model orders a shadow queue that's logged but not acted on).
- The trainer **refuses** below the minimum — `ai-brain.json` `learning.minLabeledRows` (**currently 30**, a flat
  row count; there is no "groups" concept in the code). 30 is a low floor: the corpus is ~25× over it, but
  `fba-ml-evaluator` must still caution that clearing the floor ≠ enough data for a confident promotion.
- Training output must have a **reader**: the trained artifact is loaded and actually orders the queue, or it's
  dead weight. (This was a real bug — a model trained every cycle that nothing loaded.)

## 6. Honest metrics & evaluation

- Report offline metrics with **small-sample caution** and confidence, and never conflate the offline metric
  (currently **AUC**) with real buy performance — **offline ≠ online**. The truth is realized outcomes, which lag by weeks.
- Every training run emits a report: dataset size + concentration, class balance, feature importances (with the
  dead/constant features named), metric vs champion, and an explicit go/no-go on promotion. Constant-zero features
  usually mean a plumbing break (producer unwired), not a useless signal — investigate before deleting.
- The current classifier's outputs ARE probabilities (P(would-profit)) — **calibrate them** if used as anything
  beyond a within-list ranking. (A future `LGBMRanker`'s scores would be ordinal, not probabilities.)

## 7. Cautionary tales (the failure modes the crew exists to catch)

These already happened here — treat them as the canonical bug library:
- **Dead model artifact** — trained, uploaded, nothing read it. (utilization seam)
- **Batch > token bank** — history-fetch batch of 100 vs a 60-token bank → 0 backtest rows every run. (data starvation)
- **Fingerprint hashed identity not content** — trainer printed "no new data" forever. (silent skip)
- **Telemetry that never worked** — `tokens_consumed` read a nonexistent attribute → budget math never decremented → overdraw + hang. (silent-None)
- **Mislabeled feature** — `ebay_sold_count` actually returned active listings. (fabricated-live-data)
- **Green unit tests, broken machine** — every seam mocked on both sides. Integration/seam tests with REAL components are mandatory.

## 8. The crew (route to the specialist)

`fba-ml-lead` (overseer/orchestrator) · `fba-scout-strategist` (item finder / sampling universe & breadth) ·
`fba-ml-data-engineer` (collection→dataset, dedupe, stratification) · `fba-feature-engineer` (features &
point-in-time snapshots) · `fba-ranker-architect` (model design, serving/utilization, promotion) ·
`fba-ml-trainer` (training runs, cadence, registry) · `fba-leakage-auditor` (leakage of every kind) ·
`fba-ml-evaluator` (metrics, calibration, accuracy, offline-vs-online) · `fba-ml-guardian` (guardrails,
shadow mode, no-auto-promote/buy) · `fba-ml-debugger` (root-cause of ML/pipeline failures & silent bugs).

Chain them: build → `fba-ml-lead` plans → specialists implement → `fba-leakage-auditor` + `fba-ml-evaluator` +
`fba-ml-guardian` sign off before anything is promoted or shipped. Also honor `../references/guardrails.md` and
`../references/stack-map.md`.
