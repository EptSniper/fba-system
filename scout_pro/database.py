"""
database.py — data layer (SQLAlchemy Core).

Implements the schema from the architecture paper: daily snapshots + event tables
+ label windows + analyst feedback + review queue + model registry. Runs on
PostgreSQL in production (set DATABASE_URL) and falls back to SQLite so the whole
system is runnable with zero infrastructure.

Portable upserts branch on the active dialect (Postgres ON CONFLICT vs SQLite
ON CONFLICT). JSON columns map to JSONB on Postgres and TEXT on SQLite.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import (
    JSON, Boolean, Column, Date, DateTime, Float, Integer, MetaData, String,
    Table, create_engine, func, insert, select,
)
from sqlalchemy.engine import Engine

import config

metadata = MetaData()

# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------
asin_snapshot_daily = Table(
    "asin_snapshot_daily", metadata,
    Column("asin", String, primary_key=True),
    Column("marketplace", String, primary_key=True),
    Column("snapshot_date", Date, primary_key=True),
    Column("category_id", String),
    Column("brand", String),
    Column("title", String),
    Column("image_count", Integer),
    Column("bullet_count", Integer),
    Column("buy_box_price", Float),
    Column("price_new_fba", Float),
    Column("price_new_fbm", Float),
    Column("price_amazon", Float),
    Column("sales_rank", Integer),
    Column("offer_count_new", Integer),
    Column("offer_count_used", Integer),
    Column("rating", Float),
    Column("review_count", Integer),
    Column("weight_lb", Float),
    Column("featured_offer_eligible", Boolean),
    Column("est_sales", Integer),
    Column("raw", JSON),
)

asin_offer_event = Table(
    "asin_offer_event", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("asin", String, index=True),
    Column("seller_id", String),
    Column("event_time", DateTime),
    Column("is_fba", Boolean),
    Column("is_featured_offer", Boolean),
    Column("offer_price", Float),
    Column("shipping_price", Float),
    Column("stock_proxy", Integer),
    Column("condition", String),
)

seller_storefront_daily = Table(
    "seller_storefront_daily", metadata,
    Column("seller_id", String, primary_key=True),
    Column("snapshot_date", Date, primary_key=True),
    Column("storefront_asin_count", Integer),
    Column("top_asins", JSON),
    Column("portfolio_category_mix", JSON),
    Column("estimated_buy_box_share", Float),
    Column("avg_price_band", String),
)

ads_keyword_daily = Table(
    "ads_keyword_daily", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("asin", String, index=True),
    Column("campaign_id", String),
    Column("ad_group_id", String),
    Column("keyword", String),
    Column("date", Date),
    Column("impressions", Integer),
    Column("clicks", Integer),
    Column("ctr", Float),
    Column("cpc", Float),
    Column("spend", Float),
    Column("attributed_sales", Float),
    Column("acos", Float),
    Column("roas", Float),
)

inventory_daily = Table(
    "inventory_daily", metadata,
    Column("sku", String, primary_key=True),
    Column("date", Date, primary_key=True),
    Column("on_hand", Integer),
    Column("days_of_cover", Float),
    Column("inbound_units", Integer),
    Column("stockout_flag", Boolean),
    Column("lead_time_days", Integer),
    Column("reorder_point", Integer),
)

product_label_window = Table(
    "product_label_window", metadata,
    Column("asin", String, primary_key=True),
    Column("marketplace", String, primary_key=True),
    Column("label_end_date", Date, primary_key=True),
    Column("horizon_days", Integer, primary_key=True),
    Column("label_version", String, primary_key=True),
    Column("success_proxy", Boolean),     # weak / public
    Column("success_realized", Boolean),  # strong / owned-account
    Column("proxy_score", Float),
    Column("contribution_margin", Float),
    Column("units_sold", Integer),
    Column("return_rate", Float),
    Column("compliance_flag", Boolean),
    Column("censored", Boolean),          # stockout-censored window
    Column("features", JSON),
)

picks = Table(
    "picks", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("asin", String, index=True),
    Column("score", Float),
    Column("proba", Float),
    Column("payload", JSON),
    Column("sent_at", DateTime, server_default=func.now()),
)

review_queue = Table(
    "review_queue", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("asin", String, index=True),
    Column("proba", Float),
    Column("score", Float),
    Column("reason", String),
    Column("status", String, default="pending"),   # pending|approved|rejected|deferred
    Column("created_at", DateTime, server_default=func.now()),
    Column("resolved_at", DateTime),
)

research_feedback = Table(
    "research_feedback", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("asin", String, index=True),
    Column("analyst_id", String),
    Column("decision", String),        # approve|reject|defer|supplier_issue|compliance_issue|margin_issue|false_positive
    Column("reason_code", String),
    Column("confidence", Float),
    Column("supplier_rejected", Boolean),
    Column("notes", String),
    Column("created_at", DateTime, server_default=func.now()),
)

youtube_match = Table(
    "youtube_match", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("topic_id", String),
    Column("video_id", String),
    Column("search_query", String),
    Column("semantic_score", Float),
    Column("credibility_score", Float),
    Column("engagement_score", Float),
    Column("final_rank_score", Float),
    Column("matched_claims", JSON),
)

model_registry = Table(
    "model_registry", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String, index=True),     # classifier|regressor|ranker
    Column("version", String),
    Column("kind", String),                 # algorithm used
    Column("path", String),
    Column("metrics", JSON),
    Column("is_champion", Boolean, default=False),
    Column("created_at", DateTime, server_default=func.now()),
)


# ---------------------------------------------------------------------------
# Engine / init
# ---------------------------------------------------------------------------
_engine: Optional[Engine] = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        kwargs = {"future": True}
        if config.using_sqlite():
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(config.DATABASE_URL, **kwargs)
    return _engine


def init_db() -> None:
    metadata.create_all(get_engine())


def dialect() -> str:
    return get_engine().dialect.name


# ---------------------------------------------------------------------------
# Portable upsert
# ---------------------------------------------------------------------------
def upsert(table: Table, rows: List[Dict[str, Any]], pk_cols: List[str]) -> None:
    if not rows:
        return
    eng = get_engine()
    name = eng.dialect.name
    with eng.begin() as conn:
        if name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = pg_insert(table).values(rows)
            update_cols = {c.name: stmt.excluded[c.name]
                           for c in table.columns if c.name not in pk_cols}
            stmt = stmt.on_conflict_do_update(index_elements=pk_cols, set_=update_cols)
            conn.execute(stmt)
        elif name == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as sl_insert
            for row in rows:  # row-by-row keeps excluded handling simple
                stmt = sl_insert(table).values(row)
                update_cols = {k: stmt.excluded[k] for k in row.keys() if k not in pk_cols}
                stmt = stmt.on_conflict_do_update(index_elements=pk_cols, set_=update_cols)
                conn.execute(stmt)
        else:  # generic fallback: delete-then-insert
            for row in rows:
                where = [table.c[k] == row[k] for k in pk_cols]
                conn.execute(table.delete().where(*where))
                conn.execute(table.insert().values(row))


# ---------------------------------------------------------------------------
# Convenience helpers used across the system
# ---------------------------------------------------------------------------
def insert_rows(table: Table, rows: Iterable[Dict[str, Any]]) -> None:
    rows = list(rows)
    if not rows:
        return
    with get_engine().begin() as conn:
        conn.execute(insert(table), rows)


def already_picked(asin: str) -> bool:
    with get_engine().connect() as conn:
        r = conn.execute(select(picks.c.id).where(picks.c.asin == asin).limit(1)).first()
        return r is not None


def record_pick(asin: str, score: float, proba: Optional[float], payload: Dict[str, Any]) -> None:
    insert_rows(picks, [{"asin": asin, "score": score, "proba": proba, "payload": payload}])


def enqueue_review(asin: str, proba: Optional[float], score: float, reason: str) -> None:
    insert_rows(review_queue, [{"asin": asin, "proba": proba, "score": score,
                                "reason": reason, "status": "pending"}])


def list_review_queue(status: str = "pending", limit: int = 100) -> List[Dict[str, Any]]:
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(review_queue).where(review_queue.c.status == status)
            .order_by(review_queue.c.proba.desc()).limit(limit)
        ).mappings().all()
        return [dict(r) for r in rows]


def add_feedback(asin: str, decision: str, reason_code: str = "", confidence: float = 1.0,
                 supplier_rejected: bool = False, notes: str = "", analyst_id: str = "operator") -> None:
    insert_rows(research_feedback, [{
        "asin": asin, "analyst_id": analyst_id, "decision": decision,
        "reason_code": reason_code, "confidence": confidence,
        "supplier_rejected": supplier_rejected, "notes": notes,
    }])


def upsert_label(row: Dict[str, Any]) -> None:
    upsert(product_label_window, [row],
           ["asin", "marketplace", "label_end_date", "horizon_days", "label_version"])


def registry_add(name: str, version: str, kind: str, path: str,
                 metrics: Dict[str, Any], is_champion: bool = False) -> None:
    insert_rows(model_registry, [{"name": name, "version": version, "kind": kind,
                                  "path": path, "metrics": metrics, "is_champion": is_champion}])


def registry_champion(name: str) -> Optional[Dict[str, Any]]:
    with get_engine().connect() as conn:
        r = conn.execute(
            select(model_registry).where(model_registry.c.name == name,
                                          model_registry.c.is_champion == True)  # noqa: E712
            .order_by(model_registry.c.created_at.desc()).limit(1)
        ).mappings().first()
        return dict(r) if r else None


def registry_promote(name: str, version: str) -> None:
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(model_registry.update()
                     .where(model_registry.c.name == name)
                     .values(is_champion=False))
        conn.execute(model_registry.update()
                     .where(model_registry.c.name == name,
                            model_registry.c.version == version)
                     .values(is_champion=True))


if __name__ == "__main__":
    init_db()
    print(f"Initialised {config.DATABASE_URL} (dialect: {dialect()}). Tables:")
    for t in metadata.sorted_tables:
        print("  -", t.name)
