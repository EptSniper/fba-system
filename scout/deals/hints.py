"""
scout/deals/hints.py — derive "look here first" hints from a run's collected deals
(TOP100_DEAL_WATCH_PLAN.md T1 step 5 + the §3 hints-not-rules contract).

A hint is DATA, not a rule: it says "quality deals for brand X (at store Y, category Z) are
showing up right now" so the scout's 7:30 AM discovery can point Keepa's Product Finder there
FIRST. It never edits ai-brain.json or the scout's config.

Hints are BRAND-ANCHORED because the scout acts on them via a brand-seeded Product Finder — a
brand is the unit it can actually search. store + category ride along as context. A deal with
no identifiable brand produces no hint (rather than a brand=None row nothing can consume).

THE GATE (enforced HERE, the second of two layers — registry.non_avoid_entries is the first):
an AVOID-listed brand (ai-brain.json brands.avoid, e.g. Nike) NEVER produces a hint, even
though its deals were collected as market signal. That is the whole point of "signal-only,
never sourced."
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# A deal only contributes to a hint if we actually parsed a price (a real, actionable deal —
# not just a headline) and are reasonably sure of the parse.
_MIN_CONFIDENCE = 0.5
_GOOD_DISCOUNT_PCT = 25.0


def _match_friendly_brand(row: Dict[str, Any], friendly_lower: Dict[str, str]) -> Optional[str]:
    """The friendly-list brand for this deal: the row's own brand field if it's on the list,
    else a friendly brand name found as a whole word in the title. Returns the CANONICAL
    (original-cased) brand name so hints group cleanly. None if no friendly brand matches."""
    brand = (row.get("brand") or "").strip().lower()
    if brand and brand in friendly_lower:
        return friendly_lower[brand]
    title = (row.get("title_raw") or "").lower()
    for fb_lower, fb_canonical in friendly_lower.items():
        if re.search(r"\b" + re.escape(fb_lower) + r"\b", title):
            return fb_canonical
    return None


def derive_hints(deal_rows: List[Dict[str, Any]], friendly_brands: List[str],
                 avoid_brands: List[str]) -> List[Dict[str, Any]]:
    """Aggregate quality deals into brand-anchored hints. Returns a list of
    {brand, store, category, strength} dicts (strength = discount-weighted count of quality
    deals for that brand+store). AVOID brands are excluded before aggregation — belt to the
    registry's suspenders."""
    friendly_lower = {b.strip().lower(): b for b in friendly_brands if b}
    avoid_lower = {b.strip().lower() for b in avoid_brands if b}

    # (brand, store) -> {"category": <most-recent non-empty>, "strength": float}
    agg: Dict[tuple, Dict[str, Any]] = {}
    for row in deal_rows:
        if row.get("price_current") is None:
            continue
        if (row.get("extraction_confidence") or 0) < _MIN_CONFIDENCE:
            continue
        brand = _match_friendly_brand(row, friendly_lower)
        if not brand:
            continue
        if brand.strip().lower() in avoid_lower:  # the AVOID gate — never a hint
            continue
        store = row.get("retailer") if row.get("retailer") not in (None, "unknown") else None
        key = (brand, store)
        weight = 1.0
        disc = row.get("discount_pct")
        if isinstance(disc, (int, float)) and disc >= _GOOD_DISCOUNT_PCT:
            weight += 0.5
        bucket = agg.setdefault(key, {"category": None, "strength": 0.0})
        bucket["strength"] += weight

    hints: List[Dict[str, Any]] = []
    for (brand, store), bucket in agg.items():
        hints.append({
            "brand": brand, "store": store, "category": bucket["category"],
            "strength": round(bucket["strength"], 2),
        })
    hints.sort(key=lambda h: h["strength"], reverse=True)
    return hints
