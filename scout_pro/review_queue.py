"""
review_queue.py — human-in-the-loop uncertainty routing.

Candidates whose calibrated probability falls in the ambiguous band
[UNCERTAINTY_LOW, UNCERTAINTY_HIGH] are NOT auto-alerted; they are queued for an
analyst. Resolving a queue item records an outcome (a strong label) via labels.py,
which is what feeds the next gated retrain. This is the loop that makes the system
learn from real decisions instead of guessing.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List

from sqlalchemy import select, update

import database as db
import labels


def pending(limit: int = 100) -> List[Dict[str, Any]]:
    return db.list_review_queue("pending", limit=limit)


def resolve(asin: str, decision: str, notes: str = "", analyst_id: str = "operator") -> Dict[str, Any]:
    """Resolve the newest pending queue item for an ASIN and record a label."""
    db.init_db()
    q = db.review_queue
    with db.get_engine().begin() as conn:
        row = conn.execute(
            select(q.c.id).where(q.c.asin == asin, q.c.status == "pending")
            .order_by(q.c.created_at.desc()).limit(1)
        ).first()
        status = {"approve": "approved", "reject": "rejected", "defer": "deferred"}.get(decision, "rejected")
        if row:
            conn.execute(update(q).where(q.c.id == row[0])
                         .values(status=status, resolved_at=dt.datetime.utcnow()))
    label_result = labels.record_outcome(asin, decision=decision, notes=notes, analyst_id=analyst_id)
    return {"asin": asin, "queue_status": status, **label_result}


def approve(asin: str, notes: str = "") -> Dict[str, Any]:
    return resolve(asin, "approve", notes)


def reject(asin: str, notes: str = "") -> Dict[str, Any]:
    return resolve(asin, "reject", notes)


def defer(asin: str, notes: str = "") -> Dict[str, Any]:
    return resolve(asin, "defer", notes)
