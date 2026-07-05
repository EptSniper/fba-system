"""
scout/discovery_hints.py — the scout's consumer of the nightly deal watch's "look here first"
signal (TOP100_DEAL_WATCH_PLAN.md T3). The 7:30 AM scout reads FRESH deal_hints and points its
Keepa Product Finder at those brands FIRST, before the normal friendly-brand rotation.

THE CONTRACT (plan §3): hints are DATA consumed at runtime, never rules. This module reads the
deal_hints table and the dealFinder.hints knobs from ai-brain.json; it NEVER writes either. It
honestly returns [] when there are no fresh hints (the scout then does 100% normal discovery —
not an error state).

THE AVOID GATE, second layer (run_watch is the first): even though run_watch already excludes
AVOID brands at hint-creation time, this re-filters against brands.AVOID_BRANDS at consumption
time too — belt and suspenders, so a hint for an avoid-listed brand can never steer discovery
even if a stale row predates an avoid-list change.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import brands
import db
from deals import brain_config

log = logging.getLogger("scout.discovery_hints")

_DEFAULTS = {"minStrength": 2.0, "tokenShare": 0.5, "ttlHours": 72}


def _hints_cfg() -> Dict[str, float]:
    """dealFinder.hints from ai-brain.json, with safe defaults if the block/file is absent."""
    block = brain_config.deal_finder_block().get("hints", {}) or {}
    return {
        "minStrength": float(block.get("minStrength", _DEFAULTS["minStrength"])),
        "tokenShare": float(block.get("tokenShare", _DEFAULTS["tokenShare"])),
        "ttlHours": float(block.get("ttlHours", _DEFAULTS["ttlHours"])),
    }


def min_strength() -> float:
    return _hints_cfg()["minStrength"]


def token_share() -> float:
    """Fraction (0-1) of a discovery run's budget that hint-led queries may take. Clamped to
    [0, 1] so a bad brain value can't hand discovery entirely to hints (which would starve the
    normal rotation) or go negative."""
    return max(0.0, min(1.0, _hints_cfg()["tokenShare"]))


def fresh_hints() -> List[Dict[str, Any]]:
    """Non-expired hints at/above minStrength, strongest first, with AVOID brands re-excluded.
    [] when there are none (honest 'no fresh hints' — the caller falls back to normal
    discovery, never treats this as an error)."""
    avoid_lower = {b.strip().lower() for b in brands.AVOID_BRANDS if b}
    out = []
    for h in db.fresh_deal_hints(min_strength=min_strength()):
        brand = (h.get("brand") or "").strip()
        if not brand:
            continue
        if brand.lower() in avoid_lower:  # the AVOID gate, second layer
            continue
        out.append(h)
    return out


def hinted_brand_seeds(limit: Optional[int] = None) -> List[str]:
    """The distinct brands to seed the FIRST Product Finder pass with — strongest hints first,
    deduped, AVOID-excluded (via fresh_hints). Empty when there are no fresh hints."""
    seen = set()
    seeds: List[str] = []
    for h in fresh_hints():
        brand = (h.get("brand") or "").strip()
        key = brand.lower()
        if brand and key not in seen:
            seen.add(key)
            seeds.append(brand)
    return seeds[:limit] if limit else seeds
