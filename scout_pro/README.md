# FBA Scout Pro — continuously-learning product discovery

A production-structured implementation of the architecture in *"Designing a
Continuously Learning Amazon FBA Product Discovery System."* It ingests public
marketplace history from **Keepa**, engineers windowed features, applies **hard
compliance/margin gates first**, scores candidates with a **calibrated viability
classifier** (blended with a transparent rule score), ranks them, **routes
ambiguous ones to human review**, alerts the best to **Discord**, and improves
through **gated champion/challenger retraining** on labeled outcomes.

> It is a **hybrid decision system**, not an autonomous self-trainer — exactly what
> the paper recommends. The model only improves when you feed it honest labels, and
> hard gates always override the model. It never auto-sources or moves money.
> A **paid Keepa key** is required for live ingestion; you must be **18+** to sell.

This supersedes the simpler `../scout/` project; that one is a good minimal starting
point, this is the full stack.

---

## Architecture at a glance

```
 Keepa (public history) ─┐
 SP-API / Ads (owned)*  ─┼─> ingest ─> asin_snapshot_daily (+ Parquet lake)
                         │                     │
                         │              feature engineering (windowed, pre-launch)
                         │                     │
                  HARD GATES (compliance, margin floor, crowding, oversize)
                         │                     │ (passed only)
        rule score ──────┼──> blended ◄── calibrated classifier  P(success)
                         │                     │
                         │              quantile regressor (units)  +  LambdaMART ranker
                         │                     │
                 uncertainty routing ─> review_queue ─(analyst)─> labels (strong)
                         │                     │
                   dedupe by ASIN ─> top-N ─> Discord alert
                                              │
            gated champion/challenger retrain <─ labels + drift (PSI)
```
`*` SP-API/Ads connectors are documented stubs until you wire OAuth (see below).

| Module | Role |
|---|---|
| `config.py` | All env-driven settings (DB, criteria, gates, label thresholds, model). |
| `database.py` / `db/schema.sql` | SQLAlchemy schema (snapshots, events, labels, queue, registry); Postgres or SQLite. |
| `ingest_keepa.py` | Keepa Product Finder / category pulls → daily snapshots + storefront proxies. |
| `connectors.py` | SP-API + Ads **stubs** (owned-account strong labels) — graceful until wired. |
| `lake.py` | Parquet raw-history lake (optional pyarrow). |
| `features.py` | Pre-launch windowed/relative/portfolio features (`FEATURE_COLUMNS`). |
| `labels.py` | **Weak** public-proxy + **strong** realized labels; censoring; compliance exclusion. |
| `gates.py` | Rules-first hard gates (compliance/margin/crowding/oversize). |
| `models.py` | Calibrated classifier + quantile regressor + LambdaMART ranker (LightGBM→sklearn fallback). |
| `registry.py` | Versioning + **champion/challenger** gated promotion. |
| `evaluation.py` | PR-AUC, precision/recall@k, NDCG@k, calibration error, PSI drift. |
| `monitoring.py` | Feature drift + data-quality profiles → retrain triggers. |
| `pipeline.py` | Discovery orchestration. |
| `retrain.py` | Scheduled + drift-triggered gated retraining. |
| `review_queue.py` | Human-in-the-loop resolve → labels. |
| `discord_notify.py` | Rich alerts (calibrated confidence, compliance, deep link, backoff). |
| `run_scout.py` / `train.py` / `backfill.py` | CLIs. |

---

## Setup

```bash
cd scout_pro
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # then edit
```

Minimum to run live: set **`KEEPA_KEY`** (paid) and optionally **`DISCORD_WEBHOOK_URL`**.
Defaults use SQLite + scikit-learn so nothing else is required. For Postgres, set
`DATABASE_URL` and `pip install "psycopg[binary]"`. LightGBM and pyarrow are
recommended but optional (the code falls back to sklearn and skips Parquet).

### Run

```bash
python backfill.py --finder            # build snapshot history (run daily — features need history)
python run_scout.py --once --dry-run   # score + print, post nothing
python run_scout.py --once             # alert top-N to Discord
python run_scout.py --loop --interval 360 --retrain   # every 6h, gated retrain each cycle
```

### Inspect / resolve the human-review queue

```bash
python -c "import review_queue,json; print(json.dumps(review_queue.pending(),default=str,indent=2))"
python -c "import review_queue; print(review_queue.approve('B0XXXXXXXX','looks strong'))"
```

---

## The learning loop (honest, gated)

1. Each discovery run logs picks and writes **weak proxy labels** (public signal) for training.
2. Candidates whose **calibrated probability is ambiguous** (`UNCERTAINTY_LOW..HIGH`) are
   **routed to the review queue** instead of being auto-alerted.
3. You resolve queue items (or label outcomes directly) — these become **strong labels**:

   ```bash
   python train.py --label B0XXXXXXXX --decision approve --notes "sold ~300/mo @30%"
   python train.py --label B0YYYYYYYY --decision reject  --notes "fees ate margin"
   # or realized account data:
   python train.py --realized B0XXXX --margin 0.31 --units 420 --fo 0.8 --returns 0.05
   python train.py --status
   ```

4. `train.py`/`retrain.py` trains a **challenger** and **only promotes it if it beats the
   champion's PR-AUC** by `PROMOTION_MIN_GAIN`. Drift (PSI) is another retrain trigger.
5. With **zero labels** the pipeline runs on the transparent **rule score**. Strong labels
   (your realized outcomes) outrank weak ones and drive buying decisions. More honest
   labels → a better, calibrated model. No magic, no uncontrolled self-training.

---

## What's implemented vs. stubbed vs. optional

- **Implemented & runnable now:** Keepa ingestion, Parquet lake, feature engineering,
  hard gates, weak/strong labels, calibrated classifier + quantile regressor + ranker
  (LightGBM or sklearn), champion/challenger registry, PR-AUC/NDCG/calibration/PSI,
  uncertainty routing, review queue, Discord alerts, all CLIs, SQLite **or** Postgres.
- **Stubs (need your OAuth):** `connectors.py` SP-API + Ads — the source of strong
  *realized* labels. Until wired, strong labels come from your analyst decisions.
- **Optional infra (documented, not bundled):** the paper's Feast / MLflow / Airflow /
  dbt / Evidently / TFT layer. The hooks (feature store, model registry, drift,
  scheduling) are implemented in-process; swap them for those tools at scale.

See `ARCHITECTURE.md` for the full paper→implementation map and `../04_limitations.md`
for the project-wide "what this does NOT do."
