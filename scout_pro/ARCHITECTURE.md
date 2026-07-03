# Architecture — paper → implementation map

This maps *"Designing a Continuously Learning Amazon FBA Product Discovery System"*
onto the code in `scout_pro/`. It records design choices, what is implemented, what
is stubbed, and what is intentionally left as optional infrastructure.

## 1. Source hierarchy (truth vs proxy vs enrichment)
The paper: prefer official Amazon/Ads data for truth, Keepa for public-marketplace
history, third-party tools as enrichment; MWS is sunset — don't use it.

- **Keepa (public history)** → `ingest_keepa.py` writes `asin_snapshot_daily` and
  `seller_storefront_daily`. Used for discovery + weak labels. *(implemented)*
- **SP-API / Ads (owned-account truth)** → `connectors.py` (`SPAPISource`,
  `AdsSource`). Source of **strong realized labels**. *(documented stubs — wire OAuth)*
- **Enrichment** (Google Trends, Jungle Scout, Helium 10) → not bundled; add as
  feature sources behind `features.py`. *(optional)*

## 2. Schema
The paper's daily-snapshot + event-table design is in `database.py` / `db/schema.sql`:
`asin_snapshot_daily`, `asin_offer_event`, `seller_storefront_daily`,
`ads_keyword_daily`, `inventory_daily`, `product_label_window`, `picks`,
`review_queue`, `research_feedback`, `youtube_match`, `model_registry`. Runs on
**PostgreSQL** (`DATABASE_URL`) or **SQLite** fallback. Raw history is also written to
**Parquet** (`lake.py`). pgvector embedding columns are noted but commented out.

## 3. Labels — two parallel truth systems
Per the paper, weak and strong labels are kept separate (`labels.py`):

- **Weak public-proxy** (`weak_label`): `w1·rank_stability + w2·price_resilience +
  w3·buybox_continuity + w4·review_velocity_health − w5·offer_crowding −
  w6·compliance_risk`, thresholded by `WEAK_SUCCESS_THRESHOLD`. Drives discovery only.
- **Strong realized** (`strong_label`): success iff contribution margin ≥, units ≥,
  featured-offer share ≥, and return rate ≤ business thresholds. From SP-API/Ads
  (when wired) or analyst decisions today.
- **Three labeling rules enforced:** stockout windows are `censored` (excluded),
  pre-launch features never include post-launch PPC (`features.py` is pre-launch
  only), and compliance-blocked products are `compliance_flag`-excluded/negative.
- `training_rows()` prefers strong over weak and weights strong labels 3×.

## 4. Model stack (recommended initial pipeline)
`models.py` implements rules → classifier → regressor → ranker → calibration, with
**LightGBM primary, scikit-learn fallback**:

1. **Hard gates** (`gates.py`) — compliance/margin/crowding/oversize; reject before ML.
2. **Calibrated viability classifier** — LGBMClassifier (or sklearn), wrapped in
   `CalibratedClassifierCV` (isotonic ≥200 rows, else sigmoid). Hyperparameters seeded
   from the paper, `min_data_in_leaf` scaled to data size.
3. **Quantile regressors** — `objective=quantile` (α=0.5/0.8) for units/margin.
4. **LambdaMART ranker** — `objective=lambdarank` orders the alert queue
   (falls back to ranking by calibrated probability without LightGBM).
5. **Blended score** = `(1−w)·rule_score + w·100·P(success)` (`MODEL_BLEND_WEIGHT`).
6. **Uncertainty routing** (`pipeline.py` + `review_queue.py`) — ambiguous
   probabilities go to a human queue, not an auto-alert.

## 5. Governance — gated continuous learning
The paper's central rule: **no uncontrolled online learning.** `registry.py` +
`retrain.py`:

- Every retrain produces a **versioned challenger**, saved to `model_registry/` and
  recorded in the `model_registry` table with metrics.
- **Champion/challenger gate:** promote only if challenger PR-AUC beats champion by
  `PROMOTION_MIN_GAIN`; first model auto-promotes; ties keep the incumbent.
- **Triggers:** scheduled (loop interval) **and** drift-based (`monitoring.feature_drift`
  PSI ≥ `DRIFT_PSI_THRESHOLD`).
- **Audit trail:** all versions, metrics, labels, and picks are retained.

## 6. Evaluation & monitoring
`evaluation.py`: PR-AUC (rare positives), precision/recall@k, NDCG@k (ranking),
calibration error (we threshold to alert), and PSI (drift). `monitoring.py` profiles
data quality (null rates) and computes per-feature drift between the labeled baseline
and the latest snapshots.

## 7. YouTube / Discord
- **Discord** (`discord_notify.py`): webhook embeds with score, reason, projected
  margin, competition summary, compliance status, **calibrated confidence**, model
  version, deep links; parses 429 and backs off. *(implemented)*
- **YouTube** corroboration (search.list → videos.list/channels.list → rerank by
  semantic + credibility + engagement + diversity, cache by query family) — schema
  table `youtube_match` exists; the reranker itself is **not bundled here** (the
  tracker site already does the search-link/Data-API matching). *(optional v2)*

## 8. What is intentionally NOT bundled (optional infra)
Feast (feature store), MLflow (registry/serving), Airflow (orchestration), dbt
(transforms), Evidently/whylogs (monitoring dashboards), TFT (forecasting), bandits
(exploration). The **in-process equivalents** are implemented (feature builder,
file+DB registry, cron-style loop, PSI drift). Swap them for these tools at scale —
the module boundaries are designed for that.

## 9. Roadmap (paper's milestones; first five = realistic v1)
Foundation → MVP analytics → baseline intelligence → website experience → YouTube
corroboration → monitoring/retraining → advanced ranking → forecasting/bandits.
`scout_pro` covers Foundation, MVP analytics, baseline intelligence, and
monitoring/retraining; the dashboard + YouTube reranker + forecasting/bandits are the
documented next steps.
