# Data Engine — how the system records training data

**Date:** 2026-07-04 · **Author:** Claude (Cowork). Consolidates the three data-engine prompts previously given only in chat (so they can't get lost like T1 almost did). **Prereq: KEEPA_KEY is live (Session 45) and the key-day checklist has run.**

## Layer 1 — already recording automatically (no action needed)

Once the daily run goes live: every candidate's **pre-decision feature snapshot + explanation** (leads table, G1), **runs telemetry** (tokens, counts, errors), **deals** (950+/day from the Top-100 watch), **deal hints**, and every Review-Queue verdict as a **decision with reason code** (CC1). The prediction-ledger scaffold (S38) starts grading verdict predictions as they mature.

## Layer 2 — build these (paste into Claude Code in this order; V0 first — it underpins the rest)

### Prompt V0 — the raw data lake (record everything, regret nothing, store nothing twice)

```
Read CLAUDE.md, the latest AI_COLLABORATION_JOURNAL.md entries, and DATA_ENGINE_PLAN.md's
Layer-2 intro. Use amazon-fba-oa:fba-architect for a 10-minute design check (the
raw-at-the-boundary vs derived-elsewhere split is the whole design), then fba-coder +
fba-qa-tester.

Principle: archive every EXTERNAL response raw at the moment we receive it (ephemeral
data is unrecoverable; Keepa data is re-fetchable but re-costs tokens), store NOTHING
derivable (features/scores/verdicts stay in Supabase only — the lake stores raw +
provenance pointers so all derived tables are regenerable). One copy of truth per layer.

1. scout/datalake.py: append-only Parquet writer (pyarrow), compression zstd, level from
   env DATALAKE_ZSTD_LEVEL default 12. Root from env DATA_LAKE_DIR — default a local
   path OUTSIDE OneDrive (e.g. C:\fba-data-lake), created on first write; loud warning
   if someone points it inside the OneDrive project folder. Hive partitioning:
   <root>/<source>/date=YYYY-MM-DD/part-*.parquet. Schema per row: source, entity_id
   (asin/sku/url), endpoint, params_hash, fetched_at (UTC), tokens_consumed,
   content_hash (sha256 of payload), payload (raw JSON/text, stored verbatim),
   pipeline_context (run_id, code git-sha, ai-brain.json hash). Batch writes per run
   (one file per source per run, never per row).
2. Dedupe manifest: sqlite or parquet manifest keyed (source, entity_id, endpoint) ->
   last content_hash + last_seen; identical payloads are NOT re-stored — instead the
   manifest's last_seen updates (cheap). Changed payloads append normally.
3. Wire archiving transparently into every external boundary, behind one helper so call
   sites stay one line: keepa_client (every product/finder/seller/deal response),
   deals/sources/* (raw RSS/API payloads BEFORE normalization; for clearance-page HTML
   store the zstd'd body only when extraction_confidence is below a threshold or the
   page changed — env-tunable), spapi.py (every response once live), analyst.py (exact
   input JSON + raw model output), run summaries. Archiving failures must NEVER break
   the pipeline (try/except, counted in telemetry, system_health alert if >N/day).
4. scout/harvest.py — the idle-token harvester: reads ACTUAL refill rate + tokensLeft
   from Keepa response telemetry (never assumes a plan tier); only runs after the daily
   pipeline completes; priority queue for the ASIN universe: (1) active leads,
   (2) hint brands, (3) friendly-brand Product Finder survivors, (4) breadth (watched
   categories); respects a daily harvest token budget (brain key
   learning.harvestTokenShare of observed daily generation, default 0.4, via
   fba-brain-updater); resumable; every response archived via datalake.
5. Ops: daily digest line "lake: +N rows, +X MB, total Y GB, dedupe rate Z%"; weekly
   integrity check (read-back sample of each partition, checksum verify) in the Monday
   branch; CC3's weekly Supabase backup redirects INTO the lake as
   <root>/supabase_backup/date=.../ parquet (replacing jsonl, one backup system not
   two). Document the lake's own backup story honestly in README (local disk = single
   copy; recommend an external-drive or cloud-bucket copy as a HUMAN_TODO item).
6. Tests: round-trip write/read with zstd, dedupe (same payload twice -> one row +
   manifest update), partition layout, archive-failure isolation (writer raises ->
   pipeline continues), harvester budget respect + priority order, OneDrive-path
   warning. pyarrow + zstandard added to requirements (verify Python 3.9 compat).
   Full suite green. Journal entry with first-day size numbers.
```

### Then the training-data engines:

### Prompt V1 — retrieval eval + shadow-outcome tracker

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Use
amazon-fba-oa:fba-qa-tester + fba-coder. Two measurement builds:

1. RAG retrieval eval: learning-hub/evals/retrieval/pairs.jsonl — ~40 question ->
   expected-chunk/document pairs harvested from the exam cases, chart guides, and corpus
   (each pair cites why that chunk is the right answer). knowledge-rag/eval_retrieval.py
   scores recall@5 and MRR through the live retrieval path AND through a plain BM25
   keyword baseline (rank_bm25, local) on the same pairs; report both side by side in
   learning-hub/evals/retrieval-report.md with honest per-category breakdowns. If bge
   loses to BM25 anywhere, flag chunking as the first suspect, not the model.
2. Shadow-outcome tracker: migration (NOT-APPLIED pattern) for shadow_outcomes (asin,
   candidate_run_id, checkpoint_day 30|60, price_then, price_now, offers_then,
   offers_now, would_have_profited bool computed at the ORIGINAL landed cost,
   computed_at). scout/shadow_outcomes.py: after each real discovery run, enqueue every
   gate-survivor (bought or not); a weekly job re-pulls their Keepa stats at day-30/60
   checkpoints (1-token calls, batch 100) and writes proxy labels. labels.py gains a
   label_quality column (gold=realized, silver=shadow, bronze=decision) — models may
   train on silver+gold but calibration reports MUST show performance per quality tier
   separately, with the honest caveat ("shadow labels ignore execution/sell-through")
   in every report using them. Tests: enqueue/dedupe, would_have_profited math at
   original cost, tier separation. Full suite green. Journal entry.
```

### Prompt V2 — backtest engine (the volume source: ~50k rows)

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Use
amazon-fba-oa:fba-architect for a short design check (hindsight-leakage boundary is the
whole game), then fba-coder + fba-qa-tester. Requires KEEPA_KEY.

Build scout/backtest.py — the historical training-data engine:
1. Sampling ON-POLICY: pull candidate ASINs via the SAME Product Finder stack the scout
   uses (discovery.productFinderStack per friendly brand + hint brands), not random
   ASINs. Target 3,000-5,000 unique ASINs, 1 token each batched 100/request, full
   history (days=365).
2. Windowing: per ASIN, simulation dates every ~35 days where sufficient history exists
   both sides; at each date compute the EXACT feature_snapshot the live pipeline
   computes (reuse db.PRE_DECISION_FEATURES and the same functions — no parallel
   reimplementation) using ONLY history strictly before the date. Label at date+60 from
   observed market: would_have_profited at the simulated landed cost (buy-price proxy =
   the deal-discount assumption from the brain), plus price/offer deltas.
3. Leakage tests are the deliverable: a test that plants a poisoned future datapoint
   and asserts the feature builder cannot see it; a test that the same ASIN's windows
   never straddle train/validation splits (split BY ASIN, not by row); a test that
   simulated features match the live pipeline's features on a fixture.
4. Output: rows with label_quality="backtest" (4th tier below silver), never mixed into
   calibration reports without their own tier line. Storage: derived feature rows only,
   never raw histories; report row counts + Supabase size delta.
5. Budget guard: hard cap tokens per backtest run (brain key learning.backtestTokenCap,
   default 10000, via fba-brain-updater); resume-able across days. Full suite green.
   Journal entry with the first honest row counts per tier.
```

### Prompt V3 — LightGBM ranker (train only AFTER V1+V2 have produced rows)

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Use
amazon-fba-oa:fba-architect briefly: inspect scout_pro's existing ranker module and decide
upgrade-in-place vs a new scout/ranker.py following scout_pro's registry/promotion
conventions — do NOT create a third parallel ML loop. Then fba-coder + fba-qa-tester.
Pre-reqs: shadow_outcomes and backtest rows exist (report counts before training; refuse
below 50 groups / 800 rows and say so honestly).

1. Training set: rows from tiers backtest+silver (+gold when present), graded relevance
   {3: gold profitable, 2: shadow/backtest profited with margin >= brain
   minProfitPerUnit, 1: |margin| < that, 0: lost}. Features: PRE_DECISION_FEATURES
   only, re-filtered at read. Groups: run_id (prospective) / simulation_date
   (backtest). Splits: temporal (validation groups strictly after training) AND
   by-ASIN — both test-enforced.
2. LGBMRanker: objective=lambdarank, eval NDCG@10; small-data params (num_leaves <= 31,
   min_data_in_leaf >= 50, feature_fraction ~0.8, early stopping); monotone constraints
   est_profit(+), est_roi(+), offers_rise_ratio(-) from new brain key
   scoring.rankerMonotone (fba-brain-updater, provenance). Log feature importances.
3. Champion/challenger vs the DETERMINISTIC triage formula on held-out future groups:
   NDCG@10 + winners-in-top-10 for both, confidence intervals, explicit verdict line
   ("CHALLENGER LOSES — stays shadow" / "CHALLENGER WINS — promotion requires human
   approval") in learning-hub/tracking/ranker-report.md. NO automatic promotion
   (test-asserted).
4. Shadow wiring: pipeline logs ranker ordering alongside triage ordering
   (ranker_rank on leads); digest line "ranker shadow: agreed on N of top-10".
   Promotion only via brain key scoring.rankingChampion after Mehmet approves; gates
   and thresholds untouched either way (AST-guard).
5. Artifacts versioned in learning-hub/models/ranker/<date>/; retraining
   manual/weekly, never mid-run. lightgbm added to requirements (verify Python 3.9
   compat). Tests: split enforcement, monotone application, refusal-below-minimum,
   shadow no-op, no-promotion guard. Full suite green. Journal entry with first honest
   NDCG numbers.
```

## Layer 3 — the human habit (no prompt can do this)

Decide daily in the Review Queue with a reason code (each verdict = a bronze label). When real sales happen, log outcomes in the Log page (gold labels). Volume forecast at steady state: ~50k backtest rows within a month, 1,500–3,000 shadow labels/month, 300–600 decisions/month, 10–40 gold/month — gold validates, silver trains, bronze bootstraps.
