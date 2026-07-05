"""
scout/deals/schedule.py — which registry entries get fetched, by which method, on a given day
(TOP100_DEAL_WATCH_PLAN.md T1 step 3). Keeps the nightly run under ~5 min by fetching the deep
tiers on a weekly rotation instead of all 100 stores every night:

  - Tier 1 (top 25): sd-rss daily + clr daily — the highest-value stores, checked every run.
  - Tier 2: sd-rss daily; clr on a weekly rotation (~1/7 of Tier 2's clr URLs per day).
  - Tier 3: sd-rss AND clr on a weekly rotation; the rest of Tier 3 is covered by the aggregate
    feeds (Slickdeals frontpage / Reddit / DealNews) via retailer-guessing, no per-store fetch.

Rotation day is a DETERMINISTIC hash of the entry name (hashlib, NOT Python's built-in hash()
— that is per-process randomized via PYTHONHASHSEED, which would shuffle every store to a
different day on every run and defeat the whole point of a stable weekly rotation).
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List

from . import registry


def _rotation_day(name: str) -> int:
    """Stable 0-6 day-of-week bucket for an entry, same on every run (deterministic hash)."""
    digest = hashlib.md5((name or "").encode("utf-8")).hexdigest()
    return int(digest, 16) % 7


def _has(entry: Dict[str, Any], code: str) -> bool:
    return bool(registry.detect_args(entry, code))


def entries_due(reg: Dict[str, Any], weekday: int) -> Dict[str, List[Dict[str, Any]]]:
    """weekday: 0=Mon .. 6=Sun (Python's date.weekday()). Returns {"sd_rss": [...], "clr":
    [...]} — the entries to fetch via each method today. AVOID entries ARE included (their
    deals are collected as market signal; the AVOID gate is applied later, at hint derivation,
    never at collection)."""
    sd_rss: List[Dict[str, Any]] = []
    clr: List[Dict[str, Any]] = []

    for e in reg.get("tier1", []) or []:
        if _has(e, "sd-rss"):
            sd_rss.append(e)
        if _has(e, "clr"):
            clr.append(e)

    for e in reg.get("tier2", []) or []:
        if _has(e, "sd-rss"):
            sd_rss.append(e)
        if _has(e, "clr") and _rotation_day(e.get("name", "")) == weekday:
            clr.append(e)

    for e in reg.get("tier3", []) or []:
        on_rotation = _rotation_day(e.get("name", "")) == weekday
        if _has(e, "sd-rss") and on_rotation:
            sd_rss.append(e)
        if _has(e, "clr") and on_rotation:
            clr.append(e)

    return {"sd_rss": sd_rss, "clr": clr}
