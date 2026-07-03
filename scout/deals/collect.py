"""
scout/deals/collect.py — orchestrates every configured deal source into Supabase `deals`
upserts (Deal Finder Build Plan, Prompt D1). Wired into scout/run_daily.py as a stage in
Prompt D3; callable standalone for manual runs and tests until then.

Posts a short stats embed to Discord's "retail_deals" stream (Cowork Session 23's
discord_router.py) after a real (non-dry-run) collection run — total rows + per-source
breakdown + how many were upserted. No-op when there's nothing to report.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

import db
import discord_router
import redact

from . import brain_config
from .sources import bestbuy, slickdeals

log = logging.getLogger("scout.deals.collect")

SOURCES: Dict[str, Callable[[], List[Dict[str, Any]]]] = {
    "slickdeals": slickdeals.collect,
    "bestbuy": bestbuy.collect,
}


def notify_retail_deals(summary: Dict[str, Any]) -> bool:
    """Post a short stats embed to the "retail_deals" stream. No-op (returns False) when the
    run found nothing — never posts an empty/pointless notification."""
    if not summary.get("total_rows"):
        return False
    lines = [f"• {name}: {n}" for name, n in summary.get("sources", {}).items()]
    embed = {
        "title": "Deal Finder collection run",
        "description": "\n".join(lines) or "no sources ran",
        "color": 0x36D399,
        "fields": [
            {"name": "Total rows", "value": str(summary["total_rows"]), "inline": True},
            {"name": "Upserted", "value": str(summary["upserted"]), "inline": True},
        ],
    }
    return discord_router.send("retail_deals", embed)


def collect_all(sources: Optional[List[str]] = None, dry_run: bool = False,
                notify: bool = True) -> Dict[str, Any]:
    """Run every enabled source connector and upsert results to Supabase.

    Returns {"sources": {name: row_count}, "total_rows": N, "upserted": N}. A source that
    raises is logged and skipped — one bad connector never blocks another (same
    graceful-degrade convention as the rest of the scout). dry_run collects and reports
    counts without writing to Supabase (and never notifies Discord either — a dry run must
    post NOTHING externally). A notify failure is caught and never blocks the summary return.
    """
    names = sources if sources is not None else [
        name for name in SOURCES
        if brain_config.source_config(name).get("enabled", True)
    ]
    summary: Dict[str, Any] = {"sources": {}, "total_rows": 0, "upserted": 0}
    for name in names:
        fn = SOURCES.get(name)
        if fn is None:
            log.warning("unknown deal source %r; skipping", name)
            continue
        try:
            rows = fn()
        except Exception as e:
            log.warning("deal source %s failed: %s", name, redact.redact(str(e)))
            rows = []
        summary["sources"][name] = len(rows)
        summary["total_rows"] += len(rows)
        if not dry_run:
            for row in rows:
                if db.upsert_deal(row) is not None:
                    summary["upserted"] += 1
    if notify and not dry_run:
        try:
            notify_retail_deals(summary)
        except Exception as e:
            log.warning("retail_deals notify failed (non-fatal): %s", redact.redact(str(e)))
    return summary
