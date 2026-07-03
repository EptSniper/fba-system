"""
scout/search_log.py — the brand-growth loop scaffolding (Scout Agent Build Plan, Prompt S2
sec 3.3): every winning brand becomes a saved search that's periodically due for a Product
Finder re-run, instead of relying purely on memory of "which brands are we mining." A brand is
queued automatically when a human records a BUY decision (db.log_decision(..., brand=...)).

Actual Product Finder EXECUTION stays Keepa-gated (unchanged) — this module only tracks WHAT
to search and WHEN it was last run, and degrades to "nothing due" if Supabase or the
search_log table (migration 004) aren't available yet.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional

import db

DEFAULT_RERUN_AFTER_DAYS = 21


def queue_brand_if_new(brand: Optional[str], query_params: Optional[Dict[str, Any]] = None) -> Optional[int]:
    """Queue a brand for periodic re-mining. No-op for a falsy brand; idempotent for an
    already-queued one (see db.queue_brand_search)."""
    if not brand:
        return None
    return db.queue_brand_search(brand, query_params)


def _is_due(row: Dict[str, Any], now: _dt.datetime) -> bool:
    last_run = row.get("last_run_at")
    if not last_run:
        return True  # never run -> due immediately
    try:
        last_dt = _dt.datetime.fromisoformat(str(last_run).replace("Z", "+00:00"))
    except ValueError:
        return True  # unparseable timestamp -> treat as due rather than silently skip it
    rerun_after = row.get("rerun_after_days") or DEFAULT_RERUN_AFTER_DAYS
    return (now - last_dt) >= _dt.timedelta(days=rerun_after)


def due_searches(now: Optional[_dt.datetime] = None) -> List[Dict[str, Any]]:
    """Every search_log row whose rerun_after_days cadence has elapsed (or that's never been
    run). [] if Supabase/the table are unavailable — the runner reads that as "nothing due",
    never as an error."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    return [row for row in db.all_search_log_rows() if _is_due(row, now)]


def mark_run(search_id: Optional[int]) -> None:
    db.mark_search_run(search_id)
