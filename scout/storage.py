"""
storage.py — SQLite persistence for the Product Scout.

Three tables:
    candidates -> everything the scout has ever seen (one row per ASIN, upserted)
    picks      -> what was actually sent to Discord (dedupe source)
    outcomes   -> user-supplied labels: did this product turn out good (1) or bad (0)

The `outcomes` table is the heart of the feedback loop. You add a label after you
learn how a pick actually performed; train.py then fits the model on the join of
candidates + outcomes so scoring shifts toward features that correlate with real
winners. Dedup is by ASIN so the same product is never re-sent to Discord.
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
    asin           TEXT PRIMARY KEY,
    title          TEXT,
    price          REAL,
    est_sales      INTEGER,
    reviews        INTEGER,
    rating         REAL,
    weight_lb      REAL,
    offers         INTEGER,
    margin_est     REAL,
    rule_score     REAL,
    blended_score  REAL,
    reason         TEXT,
    raw            TEXT,
    first_seen     REAL,
    last_seen      REAL
);

CREATE TABLE IF NOT EXISTS picks (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    asin      TEXT,
    score     REAL,
    payload   TEXT,
    sent_at   REAL
);
CREATE INDEX IF NOT EXISTS idx_picks_asin ON picks(asin);

CREATE TABLE IF NOT EXISTS outcomes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    asin       TEXT,
    label      INTEGER,           -- 1 = good pick, 0 = bad pick
    notes      TEXT,
    created_at REAL
);
CREATE INDEX IF NOT EXISTS idx_outcomes_asin ON outcomes(asin);
"""


def connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


# ----------------------------------------------------------------------------
# candidates
# ----------------------------------------------------------------------------
def upsert_candidate(c: Dict[str, Any], db_path: Optional[str] = None) -> None:
    """Insert or update a candidate keyed by ASIN."""
    now = time.time()
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO candidates
                (asin,title,price,est_sales,reviews,rating,weight_lb,offers,
                 margin_est,rule_score,blended_score,reason,raw,first_seen,last_seen)
            VALUES
                (:asin,:title,:price,:est_sales,:reviews,:rating,:weight_lb,:offers,
                 :margin_est,:rule_score,:blended_score,:reason,:raw,:now,:now)
            ON CONFLICT(asin) DO UPDATE SET
                title=excluded.title, price=excluded.price, est_sales=excluded.est_sales,
                reviews=excluded.reviews, rating=excluded.rating, weight_lb=excluded.weight_lb,
                offers=excluded.offers, margin_est=excluded.margin_est,
                rule_score=excluded.rule_score, blended_score=excluded.blended_score,
                reason=excluded.reason, raw=excluded.raw, last_seen=:now
            """,
            {
                "asin": c.get("asin"),
                "title": c.get("title"),
                "price": c.get("price"),
                "est_sales": c.get("est_sales"),
                "reviews": c.get("reviews"),
                "rating": c.get("rating"),
                "weight_lb": c.get("weight_lb"),
                "offers": c.get("offers"),
                "margin_est": c.get("margin_est"),
                "rule_score": c.get("rule_score"),
                "blended_score": c.get("blended_score"),
                "reason": c.get("reason"),
                "raw": json.dumps(c.get("raw", {}), default=str),
                "now": now,
            },
        )
        conn.commit()


def get_candidate(asin: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM candidates WHERE asin=?", (asin,)).fetchone()
        return dict(row) if row else None


# ----------------------------------------------------------------------------
# picks (with ASIN dedupe)
# ----------------------------------------------------------------------------
def already_picked(asin: str, db_path: Optional[str] = None) -> bool:
    with connect(db_path) as conn:
        row = conn.execute("SELECT 1 FROM picks WHERE asin=? LIMIT 1", (asin,)).fetchone()
        return row is not None


def record_pick(asin: str, score: float, payload: Dict[str, Any],
                db_path: Optional[str] = None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO picks (asin,score,payload,sent_at) VALUES (?,?,?,?)",
            (asin, score, json.dumps(payload, default=str), time.time()),
        )
        conn.commit()


def list_picks(limit: int = 100, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM picks ORDER BY sent_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def unlabeled_picks(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Picks that don't yet have an outcome label — i.e. waiting for your feedback."""
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT p.asin, p.score, p.sent_at, c.title
            FROM picks p
            LEFT JOIN candidates c ON c.asin = p.asin
            WHERE p.asin NOT IN (SELECT asin FROM outcomes)
            GROUP BY p.asin
            ORDER BY p.sent_at DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


# ----------------------------------------------------------------------------
# outcomes (the labels that make the model learn)
# ----------------------------------------------------------------------------
def add_outcome(asin: str, label: int, notes: str = "",
                db_path: Optional[str] = None) -> None:
    label = 1 if int(label) == 1 else 0
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO outcomes (asin,label,notes,created_at) VALUES (?,?,?,?)",
            (asin, label, notes, time.time()),
        )
        conn.commit()


def label_count(db_path: Optional[str] = None) -> int:
    with connect(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]


def training_rows(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Join candidates + outcomes into labeled feature rows for model.train().
    If an ASIN has multiple outcomes, the most recent label wins.
    """
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT c.asin, c.price, c.est_sales, c.reviews, c.rating, c.weight_lb,
                   c.offers, c.margin_est, c.rule_score, o.label
            FROM outcomes o
            JOIN candidates c ON c.asin = o.asin
            WHERE o.id IN (
                SELECT MAX(id) FROM outcomes GROUP BY asin
            )
            """
        ).fetchall()
        return [dict(r) for r in rows]


if __name__ == "__main__":
    init_db()
    print(f"Initialised DB at {config.DB_PATH} "
          f"({label_count()} labels, {len(list_picks())} picks so far).")
